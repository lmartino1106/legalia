"""Ingesta rápida: scraping directo de artículos clave → embeddings → Qdrant."""
import re
import json
import hashlib
import logging
import time
from pathlib import Path
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Artículos más consultados del Código del Trabajo
CT_ARTICLES = [
    1, 2, 3, 4, 5, 7, 8, 9, 10, 12,
    22, 25, 30, 31, 32, 34, 35, 38,
    41, 42, 44, 45, 54, 55, 56,
    62, 63, 67, 73, 74, 76,
    159, 160, 161, 162, 163, 168, 169, 171, 172, 173, 174, 177,
    184, 195, 201, 202, 203,
    211, 220, 243, 289, 292, 294,
    305, 306, 314, 315,
    453, 459, 485, 486, 502, 505, 506, 507,
]

# Ley del Consumidor
LC_ARTICLES = [1, 2, 3, 12, 13, 14, 15, 16, 20, 21, 23, 24, 25, 26, 37, 41, 50, 58]

FIRECRAWL_API_KEY = None


def get_firecrawl_key() -> str:
    """Lee la API key de firecrawl."""
    global FIRECRAWL_API_KEY
    if FIRECRAWL_API_KEY:
        return FIRECRAWL_API_KEY

    import os, sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from app.config import get_settings
    settings = get_settings()
    if settings.firecrawl_api_key:
        FIRECRAWL_API_KEY = settings.firecrawl_api_key
        return FIRECRAWL_API_KEY

    key = os.environ.get("FIRECRAWL_API_KEY", "")
    if key:
        FIRECRAWL_API_KEY = key
        return key

    raise ValueError("No se encontró FIRECRAWL_API_KEY en .env")


def scrape_url(url: str, cache_dir: Path = Path(".firecrawl/cache")) -> str:
    """Scraping con cache local — no re-descarga artículos ya obtenidos."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / (hashlib.md5(url.encode()).hexdigest() + ".md")

    # Cache hit
    if cache_file.exists() and cache_file.stat().st_size > 100:
        return cache_file.read_text(encoding="utf-8")

    api_key = get_firecrawl_key()

    for attempt in range(3):
        try:
            resp = httpx.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
                timeout=30,
            )

            if resp.status_code == 200:
                markdown = resp.json().get("data", {}).get("markdown", "")
                if markdown:
                    cache_file.write_text(markdown, encoding="utf-8")
                return markdown
            elif resp.status_code == 429:
                logger.warning(f"  Rate limited, esperando 5s...")
                time.sleep(5)
            else:
                logger.warning(f"  Scrape failed ({resp.status_code}): {url}")
                return ""
        except Exception as e:
            logger.warning(f"  Error (intento {attempt+1}): {e}")
            time.sleep(2)

    return ""


def extract_article_text(markdown: str) -> str:
    """Extrae texto limpio del artículo desde markdown."""
    # Buscar contenido después del heading
    match = re.search(
        r'Artículo\s+\d+[\w\s]*?\.\s*\n(.*?)(?:Chile\s+Art\.|Artículo\s*\n\[|\Z)',
        markdown, re.DOTALL | re.IGNORECASE
    )
    text = match.group(1) if match else ""

    if not text or len(text) < 20:
        # Fallback: todo después del primer heading
        match = re.search(r'#[^#].*?\n(.*)', markdown, re.DOTALL)
        text = match.group(1) if match else markdown

    # Limpiar
    text = re.sub(r'L\.\s*[\d\.]+\s*', '', text)
    text = re.sub(r'LEY\s+\d+\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'D\.O\.\s*[\d\.\-/]+\s*', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\|.*?\|', '', text)
    text = re.sub(r'---+', '', text)
    text = re.sub(r'(?:buscar|Imprimir|Iniciar sesión|Registrarse).*?\n', '', text)
    text = re.sub(r'Vigente.*?actualización.*?\n', '', text)
    text = re.sub(r'< (?:Código|Ley).*?\n', '', text)
    text = re.sub(r'Chile\s+Art\..*', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def detect_area(text: str, law_name: str) -> str:
    text_lower = (text + " " + law_name).lower()
    areas = {
        "laboral": ["trabajador", "empleador", "contrato de trabajo", "despido", "jornada", "remuneración", "sindicat", "código del trabajo"],
        "familia": ["matrimonio", "divorcio", "pensión alimenticia", "custodia", "filiación"],
        "penal": ["delito", "pena", "prisión", "reclusión", "imputado"],
        "civil": ["obligación", "contrato", "propiedad", "posesión", "herencia"],
        "consumidor": ["consumidor", "proveedor", "garantía", "sernac", "protección al consumidor"],
        "tributario": ["impuesto", "contribuyente", "sii", "renta"],
        "comercial": ["sociedad", "comerciante", "quiebra", "insolvencia"],
    }
    for area, keywords in areas.items():
        if any(kw in text_lower for kw in keywords):
            return area
    return "general"


def scrape_law_articles(law_slug: str, law_name: str, law_id: str, articles: list[int]) -> list[dict]:
    """Scrapea artículos de una ley y retorna chunks."""
    chunks = []
    for i, art_num in enumerate(articles):
        url = f"https://leyes-cl.com/{law_slug}/{art_num}.htm"
        markdown = scrape_url(url)

        if not markdown:
            continue

        text = extract_article_text(markdown)
        if len(text) < 30:
            logger.warning(f"  Art. {art_num}: texto muy corto")
            continue

        chunk_text = f"Artículo {art_num} de {law_name}: {text}"
        if len(chunk_text) > 6000:
            chunk_text = chunk_text[:6000] + "..."

        chunks.append({
            "id": hashlib.md5(f"{law_id}_art_{art_num}".encode()).hexdigest(),
            "text": chunk_text,
            "metadata": {
                "law_name": law_name,
                "law_id": law_id,
                "article": str(art_num),
                "url": url,
                "source": "leyes-cl.com",
                "type": "law",
                "area": detect_area(text, law_name),
            }
        })

        if (i + 1) % 10 == 0:
            logger.info(f"  {law_name}: {i+1}/{len(articles)} artículos")

        time.sleep(0.3)  # Rate limiting

    logger.info(f"  ✓ {law_name}: {len(chunks)} artículos extraídos")
    return chunks


def main():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from app.config import get_settings
    settings = get_settings()

    all_chunks = []

    # Código del Trabajo
    logger.info(f"=== Código del Trabajo ({len(CT_ARTICLES)} artículos) ===")
    all_chunks.extend(scrape_law_articles(
        "codigo_del_trabajo", "Código del Trabajo", "DFL-1-2003", CT_ARTICLES
    ))

    # Ley del Consumidor
    logger.info(f"\n=== Ley del Consumidor ({len(LC_ARTICLES)} artículos) ===")
    all_chunks.extend(scrape_law_articles(
        "ley_de_proteccion_al_consumidor", "Ley de Protección al Consumidor", "19496", LC_ARTICLES
    ))

    logger.info(f"\n✓ Total chunks: {len(all_chunks)}")

    if not all_chunks:
        logger.error("No se extrajeron artículos")
        return

    # Guardar chunks
    output_dir = Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "chunks.json", "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in c.items() if k != "embedding"} for c in all_chunks], f, ensure_ascii=False, indent=2)
    logger.info(f"Chunks guardados en data/processed/chunks.json")

    # Embeddings
    logger.info("\nGenerando embeddings con OpenAI...")
    import openai
    client = openai.OpenAI(api_key=settings.openai_api_key)

    batch_size = 50
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i+batch_size]
        texts = [c["text"][:8000] for c in batch]
        result = client.embeddings.create(input=texts, model="text-embedding-3-small")
        for j, emb in enumerate(result.data):
            all_chunks[i+j]["embedding"] = emb.embedding
        logger.info(f"  Embeddings: {min(i+batch_size, len(all_chunks))}/{len(all_chunks)}")

    # Upload a Qdrant
    logger.info("\nSubiendo a Qdrant Cloud...")
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct

    qclient = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    vector_size = len(all_chunks[0]["embedding"])

    collections = [c.name for c in qclient.get_collections().collections]
    if "chilean_laws" not in collections:
        qclient.create_collection(
            collection_name="chilean_laws",
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        logger.info(f"Collection 'chilean_laws' creada ({vector_size}d)")

    points = [
        PointStruct(id=i, vector=c["embedding"], payload={"text": c["text"], **c["metadata"]})
        for i, c in enumerate(all_chunks) if "embedding" in c
    ]

    for i in range(0, len(points), 100):
        qclient.upsert(collection_name="chilean_laws", points=points[i:i+100])
        logger.info(f"  Upload: {min(i+100, len(points))}/{len(points)}")

    logger.info(f"\n{'='*50}")
    logger.info(f"✓ PIPELINE COMPLETO")
    logger.info(f"  Artículos indexados: {len(points)}")
    logger.info(f"  Collection: chilean_laws")
    logger.info(f"  Dimensiones: {vector_size}")
    logger.info(f"{'='*50}")


if __name__ == "__main__":
    main()
