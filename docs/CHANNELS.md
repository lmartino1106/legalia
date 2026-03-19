# Arquitectura Multi-Canal — LegalIA

## Diseño Channel-Agnostic

El core del sistema (RAG, agentes, billing) no conoce el canal. Cada canal implementa una interfaz común.

```
┌──────────┐  ┌──────────┐
│ Telegram │  │ WhatsApp │  ... (futuro: web, SMS)
└────┬─────┘  └────┬─────┘
     │              │
     ▼              ▼
┌─────────────────────────┐
│    Channel Adapter      │  ← Normaliza mensaje entrante
│    (interfaz común)     │
└───────────┬─────────────┘
            │
            ▼
     IncomingMessage {
       user_id: str
       channel: "telegram" | "whatsapp"
       text: str
       media?: Media
       metadata: dict
     }
            │
            ▼
┌─────────────────────────┐
│     Orquestador         │  ← No sabe de qué canal viene
│     RAG Pipeline        │
│     Guardrails          │
└───────────┬─────────────┘
            │
            ▼
     OutgoingMessage {
       text: str
       citations: list
       buttons?: list
       format: "markdown" | "plain"
     }
            │
            ▼
┌─────────────────────────┐
│    Channel Formatter    │  ← Adapta al formato del canal
└───────────┬─────────────┘
     ┌──────┴──────┐
     ▼             ▼
 Telegram       WhatsApp
 (markdown,     (plain text,
  inline KB)     list buttons)
```

## Interfaz del Channel Adapter

```python
class ChannelAdapter(ABC):
    """Cada canal implementa esta interfaz."""

    @abstractmethod
    async def parse_incoming(self, raw_request: dict) -> IncomingMessage:
        """Normaliza el mensaje entrante del canal."""

    @abstractmethod
    async def send_response(self, user_id: str, message: OutgoingMessage) -> bool:
        """Envía respuesta formateada al canal."""

    @abstractmethod
    async def send_feedback_prompt(self, user_id: str, message_id: str) -> bool:
        """Envía botones de feedback (👍/👎)."""

    @abstractmethod
    async def send_upgrade_prompt(self, user_id: str) -> bool:
        """Envía mensaje de upgrade cuando se acaban las consultas."""
```

## Telegram

**Ubicación:** `app/channels/telegram/`

| Archivo | Propósito |
|---------|----------|
| `bot.py` | Inicialización del bot (python-telegram-bot) |
| `adapter.py` | Implementa ChannelAdapter |
| `handlers.py` | Command handlers (/start, /help, /plan) |
| `keyboard.py` | Inline keyboards (feedback, áreas legales) |

**Ventajas para desarrollo:**
- Markdown nativo (negrita, cursiva, links)
- Inline keyboards (botones bajo el mensaje)
- Callback queries (reaccionar a botones sin nuevo mensaje)
- Sin costo por mensaje
- Grupos y canales (futuro: comunidad legal)
- Bot commands (/start, /help, /consulta, /plan)

**Formato de respuesta:**
```
📋 *Derecho Laboral*

Según el Art. 161 del Código del Trabajo, el empleador
no puede despedir a un trabajador durante licencia médica.

📌 *Artículos relevantes:*
• Art. 161 — Causales de despido
• Art. 174 — Desafuero por licencia

⚠️ _Esta orientación no reemplaza asesoría profesional._

[👍 Útil] [👎 No útil] [👨‍⚖️ Hablar con abogado]
```

## WhatsApp (Twilio Sandbox)

**Ubicación:** `app/channels/whatsapp/`

| Archivo | Propósito |
|---------|----------|
| `client.py` | Twilio WhatsApp client |
| `adapter.py` | Implementa ChannelAdapter |
| `webhook.py` | Webhook handler |
| `templates.py` | Message templates |

**Limitaciones sandbox:**
- Solo números registrados manualmente
- Sin botones interactivos (solo texto)
- Sin templates aprobados
- Suficiente para testing

**Formato de respuesta:**
```
DERECHO LABORAL

Según el Art. 161 del Código del Trabajo, el empleador
no puede despedir a un trabajador durante licencia médica.

Artículos relevantes:
- Art. 161: Causales de despido
- Art. 174: Desafuero por licencia

⚠ Esta orientación no reemplaza asesoría profesional.

Responde:
1 - Útil
2 - No útil
3 - Hablar con abogado
```

## Diferencias de formato por canal

| Feature | Telegram | WhatsApp |
|---------|----------|----------|
| Markdown | Sí (MarkdownV2) | No (plain text) |
| Botones inline | Sí (InlineKeyboard) | No en sandbox, sí en producción |
| Max largo msg | 4,096 chars | 4,096 chars |
| Imágenes | Sí | Sí |
| Documentos | Sí (PDF) | Sí |
| Feedback | Inline buttons | Numbered reply |
| Commands | /start, /help, etc. | No |

## Estructura de carpetas

```
app/channels/
├── base.py              # ChannelAdapter ABC + data models
├── telegram/
│   ├── bot.py           # Bot init + webhook setup
│   ├── adapter.py       # TelegramAdapter(ChannelAdapter)
│   ├── handlers.py      # Command + message handlers
│   └── keyboard.py      # InlineKeyboard builders
└── whatsapp/
    ├── client.py        # Twilio client wrapper
    ├── adapter.py       # WhatsAppAdapter(ChannelAdapter)
    ├── webhook.py       # Twilio webhook handler
    └── templates.py     # Message formatting
```
