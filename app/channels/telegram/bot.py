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
from app.db import get_or_create_user, save_message, get_conversation_history, save_analytics_event
from app.agents.orchestrator import LegalOrchestrator, format_response_telegram
from app.agents.media_processor import process_media

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
        "Puedes *escribir tu caso*, enviar un *audio*, "
        "una *foto* de un documento, o un *archivo PDF*\\.\n\n"
        "⚠️ _Esta orientación no reemplaza asesoría profesional\\._"
    )
    await update.message.reply_text(welcome, parse_mode="MarkdownV2")


async def help_command(update: Update, context) -> None:
    """Handler para /help."""
    text = (
        "📋 *Cómo usar LegalIA:*\n\n"
        "Escribe tu situación legal y te oriento\\.\n\n"
        "*Puedes enviar:*\n"
        "📝 _Texto_ \\— escribe tu consulta\n"
        "🎤 _Audio_ \\— graba un mensaje de voz\n"
        "📷 _Foto_ \\— foto de un documento legal\n"
        "📄 _Documento_ \\— PDF, contrato, carta, etc\\.\n\n"
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


async def _process_and_respond(update: Update, context, db_user: dict, query_text: str, media_note: str = "") -> None:
    """Lógica compartida: procesa query (texto o extraído de media) y responde."""

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
    result = await orchestrator.process_query(query=query_text, conversation_history=history)

    # Formatear respuesta para Telegram
    try:
        response_text = format_response_telegram(result)
        # Si hubo procesamiento de media, agregar nota
        if media_note:
            response_text = f"_{_esc(media_note)}_\n\n{response_text}"
        sent = await update.message.reply_text(response_text, parse_mode="MarkdownV2")
    except Exception as e:
        logger.warning(f"Error con MarkdownV2, usando plain text: {e}")
        plain = result.get("respuesta", "Error procesando la consulta.")
        area = result.get("area_legal", "")
        leyes = result.get("leyes_relevantes", [])

        fallback = ""
        if media_note:
            fallback = f"[{media_note}]\n\n"
        fallback += f"⚖️ {area.upper()}\n\n{plain}"
        if leyes:
            fallback += "\n\n📌 Normativa:\n" + "\n".join(f"  • {l}" for l in leyes)
        fallback += "\n\n⚠️ Esta orientación no reemplaza asesoría profesional."

        sent = await update.message.reply_text(fallback)

    # Guardar respuesta en DB con confidence_score real
    confidence = result.get("confidence_score", 0.0)
    await save_message(
        user_id=db_user["id"],
        role="assistant",
        content=result.get("respuesta", ""),
        channel="telegram",
        area_detected=result.get("area_legal"),
        confidence_score=confidence,
        citations=[{"ley": l} for l in result.get("leyes_relevantes", [])],
    )

    # Loguear métricas a analytics_events
    verification = result.get("verification", {})
    await save_analytics_event(
        event_type="query",
        event_data={
            "cas_score": verification.get("cas_score", 0.0),
            "fji_score": verification.get("fji_score", 0.0),
            "confidence_score": confidence,
            "articles_retrieved": result.get("articles_retrieved", 0),
            "latency_ms": result.get("latency_ms", 0),
            "tokens_used": result.get("tokens_used", 0),
            "model": result.get("model", ""),
            "fabricated_citations": verification.get("fabricated_citations", []),
            "low_confidence_warning": result.get("low_confidence_warning", False),
            "query_preview": query_text[:100],
            "media_note": media_note,
        },
        user_id=db_user["id"],
        area_legal=result.get("area_legal"),
        rag_used="laws",
    )

    # Botones de feedback
    keyboard = [
        [
            InlineKeyboardButton("👍 Útil", callback_data=f"fb_pos_{sent.message_id}"),
            InlineKeyboardButton("👎 No útil", callback_data=f"fb_neg_{sent.message_id}"),
        ],
    ]

    if result.get("necesita_abogado"):
        keyboard.append([
            InlineKeyboardButton("👨‍⚖️ Conectar con abogado", callback_data="referral"),
        ])

    await sent.reply_text(
        "¿Te fue útil?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_message(update: Update, context) -> None:
    """Handler principal — procesa consultas legales de texto."""
    user = update.effective_user
    text = update.message.text

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

    await _process_and_respond(update, context, db_user, text)


async def handle_voice(update: Update, context) -> None:
    """Handler para mensajes de voz — transcribe y procesa."""
    user = update.effective_user
    voice = update.message.voice

    db_user = await get_or_create_user(
        channel="telegram",
        channel_user_id=str(user.id),
        display_name=user.first_name or "",
    )

    # Notificar que estamos procesando
    processing_msg = await update.message.reply_text("🎤 Transcribiendo audio...")

    media_result = await process_media(
        bot=context.bot,
        media_type="voice",
        file_id=voice.file_id,
        file_name="voice.ogg",
    )

    extracted_text = media_result["text"]
    await processing_msg.delete()

    if not extracted_text or extracted_text.startswith("[Error"):
        await update.message.reply_text(
            "No pude transcribir el audio. Intenta enviarlo de nuevo o escribe tu consulta."
        )
        return

    await save_message(
        user_id=db_user["id"],
        role="user",
        content=f"[Audio transcrito]: {extracted_text}",
        channel="telegram",
    )

    await _process_and_respond(
        update, context, db_user, extracted_text,
        media_note="🎤 Audio transcrito"
    )


async def handle_audio(update: Update, context) -> None:
    """Handler para archivos de audio."""
    user = update.effective_user
    audio = update.message.audio

    db_user = await get_or_create_user(
        channel="telegram",
        channel_user_id=str(user.id),
        display_name=user.first_name or "",
    )

    processing_msg = await update.message.reply_text("🎵 Procesando audio...")

    media_result = await process_media(
        bot=context.bot,
        media_type="audio",
        file_id=audio.file_id,
        file_name=audio.file_name or "audio.mp3",
    )

    extracted_text = media_result["text"]
    await processing_msg.delete()

    if not extracted_text or extracted_text.startswith("[Error"):
        await update.message.reply_text(
            "No pude procesar el audio. Intenta enviarlo de nuevo o escribe tu consulta."
        )
        return

    await save_message(
        user_id=db_user["id"],
        role="user",
        content=f"[Audio transcrito]: {extracted_text}",
        channel="telegram",
    )

    await _process_and_respond(
        update, context, db_user, extracted_text,
        media_note="🎵 Audio transcrito"
    )


async def handle_photo(update: Update, context) -> None:
    """Handler para fotos — analiza con Vision y procesa."""
    user = update.effective_user
    # Telegram envía varias resoluciones, tomar la mejor
    photo = update.message.photo[-1]
    caption = update.message.caption or ""

    db_user = await get_or_create_user(
        channel="telegram",
        channel_user_id=str(user.id),
        display_name=user.first_name or "",
    )

    processing_msg = await update.message.reply_text("📷 Analizando imagen...")

    media_result = await process_media(
        bot=context.bot,
        media_type="photo",
        file_id=photo.file_id,
        caption=caption,
    )

    extracted_text = media_result["text"]
    await processing_msg.delete()

    if not extracted_text or extracted_text.startswith("[Error"):
        await update.message.reply_text(
            "No pude analizar la imagen. Intenta enviarla de nuevo con mejor iluminacion."
        )
        return

    await save_message(
        user_id=db_user["id"],
        role="user",
        content=f"[Imagen analizada]: {extracted_text[:500]}",
        channel="telegram",
    )

    # Si el usuario puso caption, usarlo como pregunta principal con contexto de la imagen
    if caption:
        query = f"El usuario pregunta: '{caption}'\n\nContexto extraido de la imagen que envio:\n{extracted_text}"
    else:
        query = f"El usuario envio esta imagen de un documento legal. Analiza y orienta:\n{extracted_text}"

    await _process_and_respond(
        update, context, db_user, query,
        media_note="📷 Imagen analizada"
    )


async def handle_document(update: Update, context) -> None:
    """Handler para documentos — PDF, Word, etc."""
    user = update.effective_user
    doc = update.message.document
    caption = update.message.caption or ""

    db_user = await get_or_create_user(
        channel="telegram",
        channel_user_id=str(user.id),
        display_name=user.first_name or "",
    )

    # Verificar tamaño (máximo 20MB para Telegram)
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text(
            "El archivo es muy grande. El limite es 20MB."
        )
        return

    processing_msg = await update.message.reply_text(
        f"📄 Procesando documento: {doc.file_name or 'sin nombre'}..."
    )

    media_result = await process_media(
        bot=context.bot,
        media_type="document",
        file_id=doc.file_id,
        file_name=doc.file_name or "document",
        caption=caption,
    )

    extracted_text = media_result["text"]
    await processing_msg.delete()

    if not extracted_text or extracted_text.startswith("[Error") or extracted_text.startswith("[No se pudo"):
        await update.message.reply_text(
            f"No pude procesar el documento '{doc.file_name}'. "
            "Formatos soportados: PDF, TXT, imagenes (JPG, PNG)."
        )
        return

    await save_message(
        user_id=db_user["id"],
        role="user",
        content=f"[Documento: {doc.file_name}]: {extracted_text[:500]}",
        channel="telegram",
    )

    if caption:
        query = f"El usuario pregunta: '{caption}'\n\nContenido del documento '{doc.file_name}':\n{extracted_text}"
    else:
        query = f"El usuario envio un documento legal '{doc.file_name}'. Analiza y orienta:\n{extracted_text}"

    await _process_and_respond(
        update, context, db_user, query,
        media_note=f"📄 Documento: {doc.file_name}"
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

    # Comandos
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("nuevo", nuevo_command))

    # Texto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Media
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Callbacks (feedback, referral)
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot de Telegram configurado: @legalia_cl_bot (texto + audio + foto + documentos)")
    return app
