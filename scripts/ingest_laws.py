"""Ingesta de leyes chilenas: parsea crawl de leyes-cl.com, embede y sube a Qdrant."""
import re
import json
import hashlib
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ─── 1. PARSER ───────────────────────────────────────────────

def parse_crawl_json(filepath: str, law_name: str, law_id: str) -> list[dict]:
    """Parsea el JSON de crawl de leyes-cl.com y extrae artículos."""
    data = json.loads(Path(filepath).read_text(encoding="utf-8"))

    pages = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(pages, dict) and "data" in pages:
        pages = pages["data"]

    chunks = []

    for page in pages:
        markdown = page.get("markdown", "")
        url = page.get("metadata", {}).get("url", page.get("url", ""))

        if not markdown or not url:
            continue

        # Solo páginas de artículos individuales (ej: /codigo_del_trabajo/161.htm)
        art_url_match = re.search(r'/(\d+[\w_]*?)\.htm', url)
        if not art_url_match:
            continue

        art_slug = art_url_match.group(1)

        # Extraer texto del artículo
        art_text = extract_article_text(markdown)
        if not art_text or len(art_text) < 30:
            continue

        # Extraer número de artículo del texto
        art_num_match = re.search(r'Artículo\s+(\d+[\w\s]*?(?:BIS|TER|QUÁTER|QUINQUIES)?)\s*\.', art_text, re.IGNORECASE)
        art_num = art_num_match.group(1).strip() if art_num_match else art_slug.replace("_", " ").upper()

        chunk_text = f"Artículo {art_num} del {law_name}: {art_text}"

        # Limitar a ~1500 tokens (~6000 chars)
        if len(chunk_text) > 6000:
            chunk_text = chunk_text[:6000] + "..."

        chunk = {
            "id": hashlib.md5(f"{law_id}_art_{art_num}".encode()).hexdigest(),
            "text": chunk_text,
            "metadata": {
                "law_name": law_name,
                "law_id": law_id,
                "article": art_num,
                "url": url,
                "source": "leyes-cl.com",
                "type": "law",
                "area": detect_area(art_text, law_name),
            }
        }
        chunks.append(chunk)

    logger.info(f"Parseados {len(chunks)} artículos de {law_name}")
    return chunks


def extract_article_text(markdown: str) -> str:
    """Extrae el texto limpio del artículo desde el markdown de leyes-cl.com."""
    # Buscar el contenido del artículo (después del heading #)
    match = re.search(r'#\s*.*?Artículo\s+\d+.*?\.\s*\n(.*?)(?:\nChile\s+Art\.|Artículo\s*\n\[)', markdown, re.DOTALL | re.IGNORECASE)
    if match:
        text = match.group(1)
    else:
        # Fallback: buscar después de "Artículo N."
        match = re.search(r'(?:Artículo\s+\d+[\w\s]*\.)\s*(.*?)(?:Chile\s+Art\.|Artículo\s*\n\[|\Z)', markdown, re.DOTALL | re.IGNORECASE)
        if match:
            text = match.group(1)
        else:
            return ""

    # Limpiar
    text = re.sub(r'L\.\s*[\d\.]+\s*', '', text)
    text = re.sub(r'LEY\s+\d+\s*', '', text)
    text = re.sub(r'D\.O\.\s*[\d\.\-]+\s*', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)  # Remove markdown links
    text = re.sub(r'\|.*?\|', '', text)  # Remove table rows
    text = re.sub(r'---+', '', text)
    text = re.sub(r'buscar\s*\|', '', text)
    text = re.sub(r'Imprimir\s*', '', text)
    text = re.sub(r'Iniciar sesión\s*', '', text)
    text = re.sub(r'Registrarse\s*', '', text)
    text = re.sub(r'Vigente.*?actualización.*?\n', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)
    text = text.strip()

    return text


def detect_area(text: str, law_name: str) -> str:
    """Detecta el área legal."""
    text_lower = (text + " " + law_name).lower()
    areas = {
        "laboral": ["trabajador", "empleador", "contrato de trabajo", "despido", "jornada", "remuneración", "sindicat", "código del trabajo"],
        "familia": ["matrimonio", "divorcio", "pensión alimenticia", "custodia", "filiación", "adopción"],
        "penal": ["delito", "pena", "prisión", "reclusión", "imputado", "código penal"],
        "civil": ["obligación", "contrato", "propiedad", "posesión", "herencia", "código civil"],
        "consumidor": ["consumidor", "proveedor", "garantía", "sernac"],
        "tributario": ["impuesto", "contribuyente", "sii", "renta"],
        "comercial": ["sociedad", "comerciante", "quiebra", "insolvencia"],
    }
    for area, keywords in areas.items():
        if any(kw in text_lower for kw in keywords):
            return area
    return "general"


# ─── 2. EMBEDDINGS (OpenAI) ─────────────────────────────────

def generate_embeddings(chunks: list[dict], api_key: str) -> list[dict]:
    """Genera embeddings con OpenAI text-embedding-3-small."""
    import openai
    client = openai.OpenAI(api_key=api_key)

    batch_size = 100  # OpenAI permite hasta 2048
    total = len(chunks)

    for i in range(0, total, batch_size):
        batch = chunks[i:i+batch_size]
        texts = [c["text"][:8000] for c in batch]  # Limit per text

        result = client.embeddings.create(input=texts, model="text-embedding-3-small")

        for j, emb in enumerate(result.data):
            chunks[i+j]["embedding"] = emb.embedding

        done = min(i + batch_size, total)
        logger.info(f"  Embeddings: {done}/{total}")

    logger.info(f"✓ {total} embeddings generados (dim={len(chunks[0]['embedding'])})")
    return chunks


# ─── 3. QDRANT ───────────────────────────────────────────────

def upload_to_qdrant(chunks: list[dict], qdrant_url: str, qdrant_api_key: str, collection: str = "chilean_laws"):
    """Sube chunks a Qdrant."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key or None)

    vector_size = len(chunks[0]["embedding"])

    # Crear collection si no existe
    collections = [c.name for c in client.get_collections().collections]
    if collection not in collections:
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        logger.info(f"Collection '{collection}' creada ({vector_size}d)")
    else:
        logger.info(f"Collection '{collection}' ya existe")

    # Subir puntos
    points = []
    for i, chunk in enumerate(chunks):
        points.append(PointStruct(
            id=i,
            vector=chunk["embedding"],
            payload={
                "text": chunk["text"],
                **chunk["metadata"],
            }
        ))

    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i:i+batch_size]
        client.upsert(collection_name=collection, points=batch)
        logger.info(f"  Upload: {min(i+batch_size, len(points))}/{len(points)}")

    logger.info(f"✓ {len(points)} chunks subidos a '{collection}'")


# ─── 4. MAIN ─────────────────────────────────────────────────

def main():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from app.config import get_settings
    settings = get_settings()

    crawl_file = Path(__file__).parent.parent / ".firecrawl" / "ct-crawl.json"

    if not crawl_file.exists():
        logger.error(f"Archivo de crawl no encontrado: {crawl_file}")
        logger.info("Ejecuta primero: firecrawl crawl 'https://leyes-cl.com/codigo_del_trabajo.htm' --limit 600 --include-paths '/codigo_del_trabajo/' -o .firecrawl/ct-crawl.json --json")
        return

    # 1. Parsear
    chunks = parse_crawl_json(str(crawl_file), "Código del Trabajo", "DFL-1-2003")

    if not chunks:
        logger.error("No se extrajeron artículos")
        return

    # Guardar chunks parseados
    output_dir = Path(__file__).parent.parent / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "chunks_ct.json", "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in c.items() if k != "embedding"} for c in chunks], f, ensure_ascii=False, indent=2)
    logger.info(f"Chunks guardados en data/processed/chunks_ct.json")

    # 2. Embeddings
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY no configurada — solo se guardaron chunks sin embeddings")
        return

    chunks = generate_embeddings(chunks, settings.openai_api_key)

    # 3. Subir a Qdrant
    if not settings.qdrant_url or settings.qdrant_url == "http://localhost:6333":
        logger.warning("QDRANT_URL no configurada — embeddings generados pero no subidos")
        logger.info("Configura QDRANT_URL y QDRANT_API_KEY en .env")
        return

    upload_to_qdrant(chunks, settings.qdrant_url, settings.qdrant_api_key)
    logger.info("✓ Pipeline completo!")


if __name__ == "__main__":
    main()
