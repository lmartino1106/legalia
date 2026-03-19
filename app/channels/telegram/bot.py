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
from app.db import get_or_create_user, save_message

logger = logging.getLogger(__name__)

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
        f"👋 *Hola {user.first_name}\\!* Soy *LegalIA*, tu orientador legal con IA\\.\n\n"
        "Puedo ayudarte con consultas sobre legislación chilena:\n\n"
        "⚖️ Derecho Laboral\n"
        "🏠 Arriendos y Vivienda\n"
        "👨‍👩‍👧 Derecho de Familia\n"
        "📄 Contratos y Civil\n"
        "🏢 Derecho Comercial\n\n"
        "Simplemente *escribe tu pregunta* y te respondo\\.\n\n"
        "⚠️ _Esta orientación no reemplaza asesoría profesional\\._"
    )
    await update.message.reply_text(welcome, parse_mode="MarkdownV2")


async def help_command(update: Update, context) -> None:
    """Handler para /help."""
    text = (
        "📋 *Comandos disponibles:*\n\n"
        "/start \\- Iniciar conversación\n"
        "/help \\- Ver esta ayuda\n"
        "/areas \\- Ver áreas legales cubiertas\n"
        "/plan \\- Ver tu plan actual\n\n"
        "O simplemente escribe tu consulta legal\\."
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def areas_command(update: Update, context) -> None:
    """Handler para /areas."""
    keyboard = [
        [InlineKeyboardButton("⚖️ Laboral", callback_data="area_laboral")],
        [InlineKeyboardButton("🏠 Vivienda", callback_data="area_vivienda")],
        [InlineKeyboardButton("👨‍👩‍👧 Familia", callback_data="area_familia")],
        [InlineKeyboardButton("📄 Civil/Contratos", callback_data="area_civil")],
        [InlineKeyboardButton("🏢 Comercial", callback_data="area_comercial")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "¿Sobre qué área necesitas orientación?",
        reply_markup=reply_markup,
    )


async def handle_message(update: Update, context) -> None:
    """Handler para mensajes de texto (consultas legales)."""
    user = update.effective_user
    text = update.message.text

    # Guardar usuario y mensaje
    db_user = await get_or_create_user(
        channel="telegram",
        channel_user_id=str(user.id),
        display_name=user.first_name or "",
    )

    await save_message(
        user_id=db_user["id"],
        role="user",
        content=text,
        channel="telegram",
    )

    # TODO: Aquí va el orquestador → RAG pipeline
    # Por ahora, echo con formato legal
    response_text = (
        f"📩 Recibí tu consulta:\n\n"
        f"_{escape_md(text)}_\n\n"
        "🔄 *Procesando\\.\\.\\.*\n\n"
        "⚠️ _El sistema RAG aún no está conectado\\. "
        "Pronto podré responder con legislación chilena\\._"
    )

    # Enviar respuesta
    sent = await update.message.reply_text(response_text, parse_mode="MarkdownV2")

    # Guardar respuesta del bot
    await save_message(
        user_id=db_user["id"],
        role="assistant",
        content=response_text,
        channel="telegram",
    )

    # Botones de feedback
    keyboard = [
        [
            InlineKeyboardButton("👍 Útil", callback_data=f"fb_pos_{sent.message_id}"),
            InlineKeyboardButton("👎 No útil", callback_data=f"fb_neg_{sent.message_id}"),
        ],
        [
            InlineKeyboardButton("👨‍⚖️ Hablar con abogado", callback_data="referral"),
        ],
    ]
    await sent.reply_text(
        "¿Te fue útil esta respuesta?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_callback(update: Update, context) -> None:
    """Handler para botones inline (feedback, áreas, etc.)."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("fb_pos_"):
        await query.edit_message_text("✅ ¡Gracias por tu feedback positivo!")
        # TODO: guardar feedback positivo en DB
    elif data.startswith("fb_neg_"):
        await query.edit_message_text(
            "📝 Gracias por avisarnos. Vamos a mejorar.\n"
            "¿Puedes decirnos qué estuvo mal? (escribe tu comentario)"
        )
        # TODO: guardar feedback negativo en DB
    elif data == "referral":
        await query.edit_message_text(
            "👨‍⚖️ Te conectaremos con un abogado especializado.\n"
            "Pronto recibirás información de contacto."
        )
        # TODO: crear referral en DB
    elif data.startswith("area_"):
        area = data.replace("area_", "")
        areas_info = {
            "laboral": "⚖️ *Derecho Laboral*: despidos, contratos, horas extra, licencias, acoso laboral (Ley Karin), finiquitos.",
            "vivienda": "🏠 *Vivienda*: arriendos, desahucios, contratos de arriendo, derechos del arrendatario.",
            "familia": "👨‍👩‍👧 *Familia*: pensión alimenticia, custodia, divorcio, herencias, violencia intrafamiliar.",
            "civil": "📄 *Civil/Contratos*: contratos, deudas, cobranzas, responsabilidad civil, prescripción.",
            "comercial": "🏢 *Comercial*: sociedades, SPA, marcas, PYMES, tributario básico.",
        }
        text = areas_info.get(area, "Área no reconocida.")
        await query.edit_message_text(
            f"{text}\n\nEscribe tu pregunta sobre este tema.",
            parse_mode="Markdown",
        )


def escape_md(text: str) -> str:
    """Escapa caracteres especiales para MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    for ch in special:
        text = text.replace(ch, f"\\{ch}")
    return text


# ─── Bot Setup ───────────────────────────────────────────────

def create_bot() -> Application:
    """Crea y configura la aplicación del bot."""
    settings = get_settings()
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Comandos
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("areas", areas_command))

    # Mensajes de texto (consultas)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Callbacks de botones inline
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot de Telegram configurado: @legalia_cl_bot")
    return app
