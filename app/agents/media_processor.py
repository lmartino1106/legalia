"""Procesador de media: transcribe audio, extrae texto de imágenes y documentos."""
import logging
import tempfile
import os
import httpx
from anthropic import Anthropic
import openai
import base64
from app.config import get_settings

logger = logging.getLogger(__name__)

_anthropic_client: Anthropic | None = None
_openai_client = None


def _get_anthropic() -> Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        settings = get_settings()
        _anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def _get_openai():
    global _openai_client
    if _openai_client is None:
        settings = get_settings()
        _openai_client = openai.OpenAI(api_key=settings.openai_api_key)
    return _openai_client


async def download_telegram_file(bot, file_id: str) -> bytes:
    """Descarga un archivo de Telegram y retorna los bytes."""
    tg_file = await bot.get_file(file_id)
    file_bytes = await tg_file.download_as_bytearray()
    return bytes(file_bytes)


async def transcribe_audio(file_bytes: bytes, file_name: str = "audio.ogg") -> str:
    """Transcribe audio usando OpenAI Whisper.

    Soporta: ogg, mp3, wav, m4a, webm (formatos de Telegram voice/audio).
    """
    settings = get_settings()
    if not settings.openai_api_key:
        return "[Error: OpenAI API key no configurada para transcripcion]"

    try:
        client = _get_openai()

        # Guardar temporalmente para enviar a Whisper
        suffix = os.path.splitext(file_name)[1] or ".ogg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="es",
                    response_format="text",
                )

            text = transcript.strip() if isinstance(transcript, str) else transcript.text.strip()
            logger.info(f"Audio transcrito: {len(text)} chars")
            return text
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        logger.error(f"Error transcribiendo audio: {e}")
        return f"[Error al transcribir audio: {e}]"


async def extract_text_from_image(file_bytes: bytes) -> str:
    """Extrae texto y contexto legal de una imagen usando Claude Vision.

    Soporta: fotos de documentos legales, contratos, notificaciones, etc.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        return "[Error: Anthropic API key no configurada para vision]"

    try:
        client = _get_anthropic()

        # Codificar imagen en base64
        image_b64 = base64.b64encode(file_bytes).decode("utf-8")

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Analiza esta imagen en el contexto legal chileno. "
                            "Si es un documento legal (contrato, carta de despido, notificacion, "
                            "demanda, resolucion, boleta, factura, etc.), extrae TODO el texto visible. "
                            "Si es una foto de una situacion (accidente, dano, evidencia), "
                            "describe detalladamente lo que se ve. "
                            "Responde en espanol. Si no puedes leer algo, indicalo."
                        ),
                    },
                ],
            }],
        )

        text = response.content[0].text.strip()
        logger.info(f"Imagen analizada: {len(text)} chars")
        return text

    except Exception as e:
        logger.error(f"Error analizando imagen: {e}")
        return f"[Error al analizar imagen: {e}]"


async def extract_text_from_document(file_bytes: bytes, file_name: str) -> str:
    """Extrae texto de documentos (PDF, Word, etc.) usando Claude Vision.

    Para PDFs: convierte páginas a imágenes y las analiza con Vision.
    Para otros formatos: intenta leer como texto.
    """
    settings = get_settings()
    ext = os.path.splitext(file_name)[1].lower()

    # Intentar leer como texto plano
    if ext in (".txt", ".csv", ".json", ".md"):
        try:
            text = file_bytes.decode("utf-8")
            logger.info(f"Documento texto leido: {len(text)} chars")
            return text[:10000]  # Limitar tamaño
        except UnicodeDecodeError:
            pass

    # Para PDFs: enviar directamente a Claude como document
    if ext == ".pdf":
        return await _analyze_pdf_with_claude(file_bytes)

    # Para imágenes de documentos
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
        return await extract_text_from_image(file_bytes)

    # Para otros formatos, intentar análisis como imagen o texto
    try:
        text = file_bytes.decode("utf-8", errors="replace")
        return text[:10000]
    except Exception:
        return f"[No se pudo procesar el documento {file_name}. Formatos soportados: PDF, TXT, imagenes]"


async def _analyze_pdf_with_claude(file_bytes: bytes) -> str:
    """Analiza un PDF enviandolo directamente a Claude como documento."""
    try:
        client = _get_anthropic()

        pdf_b64 = base64.b64encode(file_bytes).decode("utf-8")

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extrae TODO el texto de este documento PDF. "
                            "Es un documento legal chileno. "
                            "Mantiene la estructura y formato. "
                            "Si hay tablas, represéntalas de forma legible. "
                            "Incluye fechas, montos, nombres y cualquier dato relevante."
                        ),
                    },
                ],
            }],
        )

        text = response.content[0].text.strip()
        logger.info(f"PDF analizado: {len(text)} chars")
        return text

    except Exception as e:
        logger.error(f"Error analizando PDF: {e}")
        return f"[Error al analizar PDF: {e}]"


async def process_media(
    bot,
    media_type: str,
    file_id: str,
    file_name: str = "",
    caption: str = "",
) -> dict:
    """Procesa cualquier tipo de media y retorna texto extraido + metadata.

    Args:
        bot: Instancia del bot de Telegram
        media_type: "voice", "audio", "photo", "document"
        file_id: File ID de Telegram
        file_name: Nombre del archivo (para documentos)
        caption: Caption del mensaje (opcional)

    Returns:
        {
            "text": "texto extraido del media",
            "media_type": "voice|audio|photo|document",
            "original_caption": "caption si habia",
            "processing_note": "nota sobre como se proceso"
        }
    """
    try:
        # Descargar archivo
        file_bytes = await download_telegram_file(bot, file_id)
        logger.info(f"Media descargado: type={media_type}, size={len(file_bytes)} bytes")

        extracted_text = ""
        processing_note = ""

        if media_type in ("voice", "audio"):
            extracted_text = await transcribe_audio(file_bytes, file_name or "audio.ogg")
            processing_note = "Audio transcrito con Whisper"

        elif media_type == "photo":
            extracted_text = await extract_text_from_image(file_bytes)
            processing_note = "Imagen analizada con Claude Vision"

        elif media_type == "document":
            extracted_text = await extract_text_from_document(file_bytes, file_name)
            processing_note = f"Documento procesado: {file_name}"

        else:
            extracted_text = "[Tipo de media no soportado]"
            processing_note = f"Media type '{media_type}' no soportado"

        # Combinar con caption si existe
        full_text = ""
        if caption:
            full_text = f"{caption}\n\n[Contenido del {media_type}]:\n{extracted_text}"
        else:
            full_text = extracted_text

        return {
            "text": full_text,
            "media_type": media_type,
            "original_caption": caption,
            "processing_note": processing_note,
        }

    except Exception as e:
        logger.error(f"Error procesando media: {e}")
        return {
            "text": f"[Error procesando {media_type}: {e}]",
            "media_type": media_type,
            "original_caption": caption,
            "processing_note": f"Error: {e}",
        }
