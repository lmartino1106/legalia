import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from app.config import get_settings
from app.db import get_or_create_user, save_message, get_conversation_history
from app.agents.orchestrator import LegalOrchestrator, format_response_telegram

logger = logging.getLogger(__name__)

# Instancia global del orquestador
_orchestrator: LegalOrchestrator | None = None


def get_orchestrator() -> LegalOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = LegalOrchestrator()
    return _orchestrator


# ─── Handlers ────────────────────────────────────────────────

async def start_command(update: Update, context) -> None:
    """Handler para /start."""
    user = update.effective_user
    await get_or_create_user(
        channel="telegram",
        channel_user_id=str(user.id),
        display_name=user.first_name or "",
    )

    welcome = (
        f"👋 *Hola {_esc(user.first_name or 'ahí')}\\!* Soy *LegalIA*\\.\n\n"
        "Soy un orientador legal con inteligencia artificial "
        "especializado en *legislación chilena*\\.\n\n"
        "Puedo ayudarte con *cualquier área del derecho*:\n"
        "laboral, familia, penal, consumidor, arriendos, "
        "tributario, migratorio, comercial, y más\\.\n\n"
        "Simplemente *escribe tu caso o pregunta* y te oriento\\.\n\n"
        "⚠️ _Esta orientación no reemplaza asesoría profesional\\._"
    )
    await update.message.reply_text(welcome, parse_mode="MarkdownV2")


async def help_command(update: Update, context) -> None:
    """Handler para /help."""
    text = (
        "📋 *Cómo usar LegalIA:*\n\n"
        "Escribe tu situación legal y te oriento\\.\n\n"
        "*Ejemplos de consultas:*\n"
        "• _Me despidieron sin aviso, ¿qué hago?_\n"
        "• _Compré algo defectuoso y no me quieren devolver la plata_\n"
        "• _Mi arrendador no me devuelve la garantía_\n"
        "• _¿Cómo funciona la pensión alimenticia?_\n"
        "• _Me chocaron y el otro conductor se fugó_\n\n"
        "*Comandos:*\n"
        "/start \\- Reiniciar conversación\n"
        "/help \\- Esta ayuda\n"
        "/nuevo \\- Nueva consulta \\(limpia contexto\\)\n"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def nuevo_command(update: Update, context) -> None:
    """Limpia el contexto de conversación."""
    context.user_data.clear()
    await update.message.reply_text(
        "🔄 Contexto limpiado\\. Escribe tu nueva consulta\\.",
        parse_mode="MarkdownV2",
    )


async def handle_message(update: Update, context) -> None:
    """Handler principal — procesa consultas legales con Claude."""
    user = update.effective_user
    text = update.message.text

    # Guardar usuario
    db_user = await get_or_create_user(
        channel="telegram",
        channel_user_id=str(user.id),
        display_name=user.first_name or "",
    )

    # Guardar mensaje del usuario
    await save_message(
        user_id=db_user["id"],
        role="user",
        content=text,
        channel="telegram",
    )

    # Indicador de "escribiendo..."
    await update.message.chat.send_action("typing")

    # Obtener historial para contexto
    history = await get_conversation_history(db_user["id"], limit=6)

    # Procesar con el orquestador (Claude)
    settings = get_settings()
    if not settings.anthropic_api_key:
        await update.message.reply_text(
            "⚙️ El sistema está en configuración\\. Pronto podré responder consultas legales\\.",
            parse_mode="MarkdownV2",
        )
        return

    orchestrator = get_orchestrator()
    result = await orchestrator.process_query(query=text, conversation_history=history)

    # Formatear respuesta para Telegram
    try:
        response_text = format_response_telegram(result)
        sent = await update.message.reply_text(response_text, parse_mode="MarkdownV2")
    except Exception as e:
        # Fallback sin markdown si falla el escape
        logger.warning(f"Error con MarkdownV2, usando plain text: {e}")
        plain = result.get("respuesta", "Error procesando la consulta.")
        area = result.get("area_legal", "")
        leyes = result.get("leyes_relevantes", [])

        fallback = f"⚖️ {area.upper()}\n\n{plain}"
        if leyes:
            fallback += "\n\n📌 Normativa:\n" + "\n".join(f"  • {l}" for l in leyes)
        fallback += "\n\n⚠️ Esta orientación no reemplaza asesoría profesional."

        sent = await update.message.reply_text(fallback)

    # Guardar respuesta en DB
    await save_message(
        user_id=db_user["id"],
        role="assistant",
        content=result.get("respuesta", ""),
        channel="telegram",
        area_detected=result.get("area_legal"),
        confidence_score=0.0,
        citations=[{"ley": l} for l in result.get("leyes_relevantes", [])],
    )

    # Botones de feedback
    keyboard = [
        [
            InlineKeyboardButton("👍 Útil", callback_data=f"fb_pos_{sent.message_id}"),
            InlineKeyboardButton("👎 No útil", callback_data=f"fb_neg_{sent.message_id}"),
        ],
    ]

    # Si necesita abogado, agregar botón
    if result.get("necesita_abogado"):
        keyboard.append([
            InlineKeyboardButton("👨‍⚖️ Conectar con abogado", callback_data="referral"),
        ])

    await sent.reply_text(
        "¿Te fue útil?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_callback(update: Update, context) -> None:
    """Handler para botones inline."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("fb_pos_"):
        await query.edit_message_text("✅ ¡Gracias! Tu feedback nos ayuda a mejorar.")
        # TODO: save_feedback(positive)
    elif data.startswith("fb_neg_"):
        await query.edit_message_text(
            "📝 Gracias por avisarnos. ¿Qué estuvo mal?\n"
            "Escribe tu comentario y lo usaremos para mejorar."
        )
        # TODO: save_feedback(negative) + flag for review
    elif data == "referral":
        await query.edit_message_text(
            "👨‍⚖️ Derivación a abogado\n\n"
            "Pronto implementaremos la conexión con abogados "
            "especializados en tu área. Por ahora, te recomendamos "
            "buscar en el registro de abogados del Colegio de Abogados "
            "o consultar en tu CAJ (Corporación de Asistencia Judicial) más cercana."
        )


def _esc(text: str) -> str:
    """Escapa caracteres para Telegram MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    for ch in special:
        text = text.replace(ch, f"\\{ch}")
    return text


# ─── Bot Setup ───────────────────────────────────────────────

def create_bot() -> Application:
    """Crea y configura la aplicación del bot."""
    settings = get_settings()
    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("nuevo", nuevo_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot de Telegram configurado: @legalia_cl_bot")
    return app
