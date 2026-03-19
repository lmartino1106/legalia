from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class IncomingMessage:
    """Mensaje normalizado de cualquier canal."""
    user_id: str                    # ID único del usuario en el canal
    channel: str                    # "telegram" | "whatsapp"
    text: str                       # Texto del mensaje
    user_name: str = ""             # Nombre del usuario
    user_phone: str = ""            # Teléfono (WhatsApp)
    media_type: str | None = None   # image, document, audio
    media_url: str | None = None
    raw_data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OutgoingMessage:
    """Respuesta del sistema, independiente del canal."""
    text: str
    citations: list[dict] = field(default_factory=list)
    area_legal: str | None = None
    buttons: list[dict] = field(default_factory=list)   # [{label, callback_data}]
    confidence: float = 0.0
    message_id: str | None = None   # ID para tracking de feedback


class ChannelAdapter(ABC):
    """Interfaz que cada canal debe implementar."""

    @abstractmethod
    async def parse_incoming(self, raw_data: dict) -> IncomingMessage:
        """Normaliza mensaje entrante."""

    @abstractmethod
    async def send_response(self, user_id: str, message: OutgoingMessage) -> bool:
        """Envía respuesta formateada al canal."""

    @abstractmethod
    async def send_feedback_prompt(self, user_id: str, message_id: str) -> bool:
        """Envía botones de feedback."""
