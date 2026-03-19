"""Retriever: busca artículos relevantes en Qdrant para una consulta legal."""
import logging
from qdrant_client import QdrantClient
import openai
from app.config import get_settings

logger = logging.getLogger(__name__)

_qclient: QdrantClient | None = None
_oai_client = None


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


async def search_laws(query: str, area: str | None = None, top_k: int = 5) -> list[dict]:
    """Busca artículos relevantes para una consulta legal.

    Args:
        query: Pregunta del usuario
        area: Área legal para filtrar (opcional)
        top_k: Número de resultados

    Returns:
        Lista de artículos con texto, metadata y score
    """
    settings = get_settings()

    if not settings.qdrant_url or not settings.openai_api_key:
        logger.warning("RAG no configurado (falta QDRANT_URL o OPENAI_API_KEY)")
        return []

    try:
        # Generar embedding de la consulta
        oai = get_openai()
        emb_result = oai.embeddings.create(input=[query], model="text-embedding-3-small")
        query_vector = emb_result.data[0].embedding

        # Buscar en Qdrant
        qclient = get_qdrant()

        # Filtro por área si se especifica
        query_filter = None
        if area:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            query_filter = Filter(
                must=[FieldCondition(key="area", match=MatchValue(value=area))]
            )

        results = qclient.search(
            collection_name="chilean_laws",
            query_vector=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )

        articles = []
        for hit in results:
            articles.append({
                "text": hit.payload.get("text", ""),
                "law_name": hit.payload.get("law_name", ""),
                "article": hit.payload.get("article", ""),
                "area": hit.payload.get("area", ""),
                "url": hit.payload.get("url", ""),
                "score": hit.score,
            })

        logger.info(f"RAG: {len(articles)} artículos encontrados para '{query[:50]}...' (area={area})")
        return articles

    except Exception as e:
        logger.error(f"Error en RAG search: {e}")
        return []


def format_context_for_llm(articles: list[dict]) -> str:
    """Formatea artículos recuperados como contexto para el LLM."""
    if not articles:
        return ""

    parts = ["LEGISLACIÓN CHILENA RELEVANTE (extraída de fuentes oficiales):\n"]

    for i, art in enumerate(articles, 1):
        parts.append(f"---\nFuente {i} (relevancia: {art['score']:.2f}):")
        parts.append(f"  {art['law_name']} - Artículo {art['article']}")
        parts.append(f"  {art['text'][:1500]}")
        if art.get("url"):
            parts.append(f"  Referencia: {art['url']}")

    parts.append("---\n")
    parts.append("IMPORTANTE: Basa tu respuesta en estos artículos específicos. Cita los números de artículo exactos.")

    return "\n".join(parts)
