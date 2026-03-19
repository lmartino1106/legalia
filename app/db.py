"""Database operations via Supabase."""
import logging
from supabase import create_client, Client
from app.config import get_settings

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_supabase() -> Client:
    """Get or create Supabase client."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(settings.supabase_url, settings.supabase_anon_key)
    return _client


async def get_or_create_user(
    channel: str,
    channel_user_id: str,
    display_name: str = "",
    phone: str = "",
) -> dict:
    """Find existing user or create new one."""
    db = get_supabase()

    # Usamos channel:channel_user_id como phone para Telegram
    # Para WhatsApp usaremos el teléfono real
    identifier = phone if phone else f"{channel}:{channel_user_id}"

    # Buscar usuario existente
    result = db.table("users").select("*").eq("phone", identifier).execute()

    if result.data:
        # Actualizar last_active
        db.table("users").update({"last_active_at": "now()"}).eq("id", result.data[0]["id"]).execute()
        return result.data[0]

    # Crear nuevo usuario
    new_user = {
        "phone": identifier,
        "display_name": display_name,
        "metadata": {"channel": channel, "channel_user_id": channel_user_id},
    }
    result = db.table("users").insert(new_user).execute()
    logger.info(f"Nuevo usuario creado: {display_name} ({channel})")
    return result.data[0]


async def save_message(
    user_id: str,
    role: str,
    content: str,
    channel: str,
    conversation_id: str | None = None,
    rag_sources: list | None = None,
    citations: list | None = None,
    area_detected: str | None = None,
    confidence_score: float | None = None,
) -> dict:
    """Save a message to the database."""
    db = get_supabase()

    # Si no hay conversación activa, crear una
    if not conversation_id:
        conversation_id = await get_or_create_conversation(user_id)

    msg = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "role": role,
        "content": content,
    }

    if rag_sources:
        msg["rag_sources"] = rag_sources
    if citations:
        msg["citations"] = citations
    if area_detected:
        msg["area_detected"] = area_detected
    if confidence_score:
        msg["confidence_score"] = confidence_score

    result = db.table("messages").insert(msg).execute()
    return result.data[0]


async def get_or_create_conversation(user_id: str) -> str:
    """Get active conversation or create new one."""
    db = get_supabase()

    # Buscar conversación activa
    result = (
        db.table("conversations")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("last_message_at", desc=True)
        .limit(1)
        .execute()
    )

    if result.data:
        conv_id = result.data[0]["id"]
        db.table("conversations").update({"last_message_at": "now()"}).eq("id", conv_id).execute()
        return conv_id

    # Crear nueva conversación
    result = db.table("conversations").insert({"user_id": user_id}).execute()
    return result.data[0]["id"]


async def get_conversation_history(user_id: str, limit: int = 6) -> list[dict]:
    """Get recent messages for conversation context."""
    db = get_supabase()

    # Buscar conversación activa
    conv_result = (
        db.table("conversations")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("last_message_at", desc=True)
        .limit(1)
        .execute()
    )

    if not conv_result.data:
        return []

    conv_id = conv_result.data[0]["id"]

    # Obtener últimos mensajes
    msg_result = (
        db.table("messages")
        .select("role, content")
        .eq("conversation_id", conv_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    # Invertir para orden cronológico
    return list(reversed(msg_result.data)) if msg_result.data else []


async def save_feedback(
    message_id: str,
    user_id: str,
    conversation_id: str,
    rating: str,
    question: str,
    answer: str,
    area_legal: str | None = None,
) -> dict:
    """Save user feedback on a response."""
    db = get_supabase()
    feedback = {
        "message_id": message_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "rating": rating,
        "question": question,
        "answer": answer,
        "area_legal": area_legal,
    }
    result = db.table("feedback").insert(feedback).execute()
    return result.data[0]
