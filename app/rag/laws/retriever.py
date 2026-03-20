"""Retriever: búsqueda híbrida (Vector + BM25) con reranking para consultas legales."""
import logging
import time
from qdrant_client import QdrantClient
import openai
from anthropic import Anthropic
from rank_bm25 import BM25Okapi
from app.config import get_settings

logger = logging.getLogger(__name__)

_qclient: QdrantClient | None = None
_oai_client = None
_anthropic_client: Anthropic | None = None

# BM25 index (se construye una vez en memoria)
_bm25_index: BM25Okapi | None = None
_bm25_corpus: list[dict] | None = None


def get_qdrant() -> QdrantClient:
    global _qclient
    if _qclient is None:
        settings = get_settings()
        _qclient = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    return _qclient


def get_openai():
    global _oai_client
    if _oai_client is None:
        settings = get_settings()
        _oai_client = openai.OpenAI(api_key=settings.openai_api_key)
    return _oai_client


def _get_anthropic() -> Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        settings = get_settings()
        _anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


# ─── Fase 2: BM25 Index ──────────────────────────────────────

def _build_bm25_index() -> None:
    """Carga corpus completo de Qdrant y construye índice BM25 en memoria."""
    global _bm25_index, _bm25_corpus

    try:
        qclient = get_qdrant()

        # Scroll all points from collection
        all_points = []
        offset = None
        while True:
            result, next_offset = qclient.scroll(
                collection_name="chilean_laws",
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            all_points.extend(result)
            if next_offset is None:
                break
            offset = next_offset

        if not all_points:
            logger.warning("BM25: No se encontraron documentos en Qdrant")
            return

        # Construir corpus
        _bm25_corpus = []
        tokenized_corpus = []
        for point in all_points:
            doc = {
                "id": point.id,
                "text": point.payload.get("text", ""),
                "law_name": point.payload.get("law_name", ""),
                "article": point.payload.get("article", ""),
                "area": point.payload.get("area", ""),
                "url": point.payload.get("url", ""),
            }
            _bm25_corpus.append(doc)
            # Tokenizar: lowercase + split
            tokenized_corpus.append(doc["text"].lower().split())

        _bm25_index = BM25Okapi(tokenized_corpus)
        logger.info(f"BM25: Índice construido con {len(_bm25_corpus)} documentos")

    except Exception as e:
        logger.error(f"Error construyendo índice BM25: {e}")


def _bm25_search(query: str, top_k: int = 8) -> list[dict]:
    """Búsqueda keyword con BM25."""
    global _bm25_index, _bm25_corpus

    if _bm25_index is None or _bm25_corpus is None:
        _build_bm25_index()

    if _bm25_index is None or _bm25_corpus is None:
        return []

    tokenized_query = query.lower().split()
    scores = _bm25_index.get_scores(tokenized_query)

    # Obtener top_k resultados con score > 0
    scored_docs = [(i, s) for i, s in enumerate(scores) if s > 0]
    scored_docs.sort(key=lambda x: x[1], reverse=True)

    results = []
    for idx, score in scored_docs[:top_k]:
        doc = _bm25_corpus[idx].copy()
        doc["bm25_score"] = float(score)
        results.append(doc)

    return results


# ─── Fase 2: Reciprocal Rank Fusion ──────────────────────────

def _reciprocal_rank_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """Combina resultados de vector search y BM25 usando RRF.

    RRF score = Σ 1/(k + rank_i) para cada sistema que lo rankea.
    """
    doc_scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    # Score from vector search
    for rank, doc in enumerate(vector_results):
        key = f"{doc.get('law_name', '')}_{doc.get('article', '')}"
        doc_scores[key] = doc_scores.get(key, 0) + 1.0 / (k + rank + 1)
        doc_map[key] = doc

    # Score from BM25
    for rank, doc in enumerate(bm25_results):
        key = f"{doc.get('law_name', '')}_{doc.get('article', '')}"
        doc_scores[key] = doc_scores.get(key, 0) + 1.0 / (k + rank + 1)
        if key not in doc_map:
            doc_map[key] = doc

    # Sort by RRF score
    sorted_keys = sorted(doc_scores.keys(), key=lambda x: doc_scores[x], reverse=True)

    fused = []
    for key in sorted_keys:
        doc = doc_map[key].copy()
        doc["rrf_score"] = doc_scores[key]
        # Limpiar scores intermedios
        doc.pop("bm25_score", None)
        fused.append(doc)

    return fused


# ─── Fase 3: Reranker con Claude Haiku ───────────────────────

async def _rerank_articles(query: str, articles: list[dict], top_k: int = 5) -> list[dict]:
    """Reordena artículos por relevancia legal usando Claude Haiku."""
    if len(articles) <= top_k:
        return articles

    try:
        client = _get_anthropic()

        # Preparar candidatos para reranking
        candidates = ""
        for i, art in enumerate(articles[:8]):  # Máximo 8 candidatos
            candidates += (
                f"[{i}] {art.get('law_name', '')} Art. {art.get('article', '')}: "
                f"{art.get('text', '')[:300]}\n\n"
            )

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=(
                "Eres un asistente legal. Dada una consulta y artículos legales candidatos, "
                "ordénalos por relevancia para responder la consulta. "
                "Responde SOLO con los índices ordenados, separados por comas. "
                "Ejemplo: 2,0,4,1,3"
            ),
            messages=[{
                "role": "user",
                "content": f"Consulta: {query}\n\nArtículos candidatos:\n{candidates}\n\n"
                           f"Ordena los {min(len(articles), 8)} artículos por relevancia (índices separados por comas):",
            }],
        )

        # Parsear orden
        raw = response.content[0].text.strip()
        indices = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]

        reranked = []
        seen = set()
        for idx in indices[:top_k]:
            if 0 <= idx < len(articles) and idx not in seen:
                reranked.append(articles[idx])
                seen.add(idx)

        # Agregar artículos faltantes si el reranker no devolvió suficientes
        for i, art in enumerate(articles):
            if len(reranked) >= top_k:
                break
            if i not in seen:
                reranked.append(art)

        logger.info(f"Reranker: reordenó {len(articles)} → top {len(reranked)} artículos")
        return reranked

    except Exception as e:
        logger.warning(f"Reranker falló, usando orden RRF: {e}")
        return articles[:top_k]


# ─── Search principal (híbrido) ──────────────────────────────

async def search_laws(query: str, area: str | None = None, top_k: int = 5) -> list[dict]:
    """Búsqueda híbrida: Vector + BM25 → RRF → Rerank.

    Args:
        query: Pregunta del usuario
        area: Área legal para filtrar (opcional)
        top_k: Número de resultados finales

    Returns:
        Lista de artículos con texto, metadata y score
    """
    settings = get_settings()
    start_time = time.time()

    if not settings.qdrant_url or not settings.openai_api_key:
        logger.warning("RAG no configurado (falta QDRANT_URL o OPENAI_API_KEY)")
        return []

    try:
        # ── Vector search ──
        oai = get_openai()
        emb_result = oai.embeddings.create(input=[query], model="text-embedding-3-small")
        query_vector = emb_result.data[0].embedding

        qclient = get_qdrant()

        query_filter = None
        if area:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            query_filter = Filter(
                must=[FieldCondition(key="area", match=MatchValue(value=area))]
            )

        from qdrant_client.models import models

        vector_results_raw = qclient.query_points(
            collection_name="chilean_laws",
            query=query_vector,
            query_filter=query_filter,
            limit=top_k + 3,  # Más candidatos para fusión
            with_payload=True,
        )

        vector_results = []
        for hit in vector_results_raw.points:
            vector_results.append({
                "text": hit.payload.get("text", ""),
                "law_name": hit.payload.get("law_name", ""),
                "article": hit.payload.get("article", ""),
                "area": hit.payload.get("area", ""),
                "url": hit.payload.get("url", ""),
                "score": hit.score,
            })

        # ── BM25 search ──
        bm25_results = _bm25_search(query, top_k=top_k + 3)

        # ── RRF Fusion ──
        fused = _reciprocal_rank_fusion(vector_results, bm25_results)
        logger.info(
            f"RAG hybrid: {len(vector_results)} vector + {len(bm25_results)} BM25 "
            f"→ {len(fused)} fusionados"
        )

        # ── Rerank con Haiku ──
        if len(fused) > top_k and settings.anthropic_api_key:
            reranked = await _rerank_articles(query, fused, top_k=top_k)
        else:
            reranked = fused[:top_k]

        # Asegurar que cada artículo tenga un score
        for art in reranked:
            if "score" not in art:
                art["score"] = art.get("rrf_score", 0.0)

        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"RAG: {len(reranked)} artículos finales para '{query[:50]}...' "
            f"(area={area}, latency={elapsed_ms}ms)"
        )

        return reranked

    except Exception as e:
        logger.error(f"Error en RAG search: {e}")
        return []


def format_context_for_llm(articles: list[dict]) -> str:
    """Formatea artículos recuperados como contexto para el LLM."""
    if not articles:
        return ""

    parts = ["LEGISLACIÓN CHILENA RELEVANTE (extraída de fuentes oficiales):\n"]

    for i, art in enumerate(articles, 1):
        score = art.get('score', art.get('rrf_score', 0))
        parts.append(f"---\nFuente {i} (relevancia: {score:.2f}):")
        parts.append(f"  {art['law_name']} - Artículo {art['article']}")
        parts.append(f"  {art['text'][:1500]}")
        if art.get("url"):
            parts.append(f"  Referencia: {art['url']}")

    parts.append("---\n")
    parts.append("IMPORTANTE: Basa tu respuesta en estos artículos específicos. Cita los números de artículo exactos.")

    return "\n".join(parts)
