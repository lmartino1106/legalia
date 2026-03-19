"""LegalIA — Bot legal con IA para Chile."""
import logging
import asyncio
from app.config import get_settings
from app.channels.telegram.bot import create_bot

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    """Start the Telegram bot in polling mode (development)."""
    settings = get_settings()

    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN no configurado en .env")
        return

    logger.info("Iniciando LegalIA bot (@legalia_cl_bot)...")
    logger.info(f"Entorno: {settings.app_env}")

    bot = create_bot()
    bot.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
