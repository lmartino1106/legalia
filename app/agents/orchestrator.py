"""Orquestador principal — clasifica, genera respuesta con RAG, aplica guardrails."""
import logging
import json
from anthropic import Anthropic
from app.config import get_settings
from app.rag.laws.retriever import search_laws, format_context_for_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres LegalIA, un orientador legal con inteligencia artificial especializado en legislación chilena.

## Tu rol
- Orientas a personas comunes sobre temas legales en Chile
- Identificas el área legal de cada consulta
- Respondes con información clara, útil y precisa
- Citas artículos y leyes específicas cuando es posible
- NUNCA dices que eres abogado ni que das asesoría legal profesional

## Áreas que cubres (sin limitación)
Derecho laboral, civil, familia, penal, consumidor, tributario, administrativo,
comercial, constitucional, ambiental, minero, aeronáutico, marítimo, militar,
propiedad intelectual, inmobiliario, migratorio, salud, educación, previsional,
seguros, libre competencia, datos personales, y cualquier otra área del derecho chileno.

## Formato de respuesta
Responde SIEMPRE en formato JSON con esta estructura:
{
  "area_legal": "derecho laboral",
  "sub_area": "despido injustificado",
  "resumen_caso": "Breve resumen del caso del usuario en 1-2 frases",
  "respuesta": "Tu respuesta completa y detallada sobre el caso. Usa lenguaje simple y claro. Explica los derechos, opciones y pasos a seguir. Si puedes, cita artículos específicos.",
  "leyes_relevantes": ["Código del Trabajo Art. 161", "Ley 21.643"],
  "necesita_abogado": false,
  "razon_abogado": null,
  "nivel_urgencia": "medio"
}

## Reglas críticas
1. Si detectas una EMERGENCIA (violencia, riesgo vital), indica que llamen al 149 (Carabineros) o 133 (Bomberos) INMEDIATAMENTE
2. Si el caso requiere representación judicial o tiene plazos legales corriendo, indica necesita_abogado: true
3. Siempre menciona que esta orientación NO reemplaza asesoría profesional
4. Si no estás seguro de algo, dilo explícitamente — nunca inventes leyes o artículos
5. nivel_urgencia: "bajo" (informativo), "medio" (tiene derechos que ejercer), "alto" (plazos corriendo), "urgente" (emergencia)
6. Responde SOLO en español chileno
7. Responde SOLO el JSON, sin texto adicional"""

CONTEXT_PROMPT = """Historial de la conversación:
{history}

{rag_context}

Consulta actual del usuario:
{query}"""


class LegalOrchestrator:
    """Orquesta la respuesta legal usando Claude."""

    def __init__(self):
        settings = get_settings()
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"

    async def process_query(
        self,
        query: str,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """Procesa una consulta legal y retorna respuesta estructurada."""

        # Construir historial
        history_text = ""
        if conversation_history:
            for msg in conversation_history[-6:]:  # últimos 6 mensajes
                role = "Usuario" if msg["role"] == "user" else "LegalIA"
                history_text += f"{role}: {msg['content']}\n"

        # RAG: buscar artículos relevantes
        rag_context = ""
        try:
            articles = await search_laws(query, top_k=5)
            if articles:
                rag_context = format_context_for_llm(articles)
                logger.info(f"RAG: {len(articles)} artículos inyectados al contexto")
        except Exception as e:
            logger.warning(f"RAG search falló, continuando sin contexto: {e}")

        user_content = CONTEXT_PROMPT.format(
            history=history_text or "(primera consulta)",
            rag_context=rag_context or "(sin artículos recuperados — responde con tu conocimiento general)",
            query=query,
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )

            raw_text = response.content[0].text.strip()

            # Parsear JSON de la respuesta
            # Limpiar posibles markdown code blocks
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()

            result = json.loads(raw_text)

            # Agregar metadata
            result["tokens_used"] = response.usage.input_tokens + response.usage.output_tokens
            result["model"] = self.model

            logger.info(
                f"Consulta procesada: area={result.get('area_legal')}, "
                f"urgencia={result.get('nivel_urgencia')}, "
                f"tokens={result.get('tokens_used')}"
            )

            return result

        except json.JSONDecodeError:
            logger.warning(f"Claude no retornó JSON válido: {raw_text[:200]}")
            return {
                "area_legal": "no identificada",
                "sub_area": "",
                "resumen_caso": "",
                "respuesta": raw_text,
                "leyes_relevantes": [],
                "necesita_abogado": False,
                "razon_abogado": None,
                "nivel_urgencia": "bajo",
                "tokens_used": 0,
                "model": self.model,
            }

        except Exception as e:
            logger.error(f"Error al procesar consulta: {e}")
            return {
                "area_legal": "error",
                "sub_area": "",
                "resumen_caso": "",
                "respuesta": "Lo siento, hubo un error procesando tu consulta. Por favor intenta de nuevo.",
                "leyes_relevantes": [],
                "necesita_abogado": False,
                "razon_abogado": None,
                "nivel_urgencia": "bajo",
                "tokens_used": 0,
                "model": self.model,
                "error": str(e),
            }


def format_response_telegram(result: dict) -> str:
    """Formatea la respuesta del orquestador para Telegram (MarkdownV2)."""

    area = result.get("area_legal", "General")
    sub = result.get("sub_area", "")
    respuesta = result.get("respuesta", "")
    leyes = result.get("leyes_relevantes", [])
    necesita_abogado = result.get("necesita_abogado", False)
    razon = result.get("razon_abogado", "")
    urgencia = result.get("nivel_urgencia", "bajo")

    # Emoji por urgencia
    urgencia_emoji = {
        "bajo": "🟢",
        "medio": "🟡",
        "alto": "🟠",
        "urgente": "🔴",
    }

    parts = []

    # Header con área
    header = f"⚖️ *{_esc(area.title())}*"
    if sub:
        header += f" — {_esc(sub)}"
    parts.append(header)
    parts.append(f"{urgencia_emoji.get(urgencia, '⚪')} Urgencia: {_esc(urgencia)}")
    parts.append("")

    # Respuesta principal
    parts.append(_esc(respuesta))
    parts.append("")

    # Leyes relevantes
    if leyes:
        parts.append("📌 *Normativa relevante:*")
        for ley in leyes:
            parts.append(f"• {_esc(ley)}")
        parts.append("")

    # Alerta de abogado
    if necesita_abogado:
        parts.append("👨‍⚖️ *Te recomendamos consultar con un abogado*")
        if razon:
            parts.append(f"_{_esc(razon)}_")
        parts.append("")

    # Disclaimer
    parts.append("⚠️ _Esta orientación no reemplaza asesoría profesional\\._")

    return "\n".join(parts)


def format_response_plain(result: dict) -> str:
    """Formatea para WhatsApp / texto plano."""

    area = result.get("area_legal", "General")
    sub = result.get("sub_area", "")
    respuesta = result.get("respuesta", "")
    leyes = result.get("leyes_relevantes", [])
    necesita_abogado = result.get("necesita_abogado", False)
    razon = result.get("razon_abogado", "")

    parts = []

    header = f"⚖️ {area.upper()}"
    if sub:
        header += f" — {sub}"
    parts.append(header)
    parts.append("")
    parts.append(respuesta)
    parts.append("")

    if leyes:
        parts.append("📌 Normativa relevante:")
        for ley in leyes:
            parts.append(f"  • {ley}")
        parts.append("")

    if necesita_abogado:
        parts.append("👨‍⚖️ TE RECOMENDAMOS CONSULTAR CON UN ABOGADO")
        if razon:
            parts.append(f"  → {razon}")
        parts.append("")

    parts.append("⚠️ Esta orientación no reemplaza asesoría profesional.")

    return "\n".join(parts)


def _esc(text: str) -> str:
    """Escapa caracteres para Telegram MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    for ch in special:
        text = text.replace(ch, f"\\{ch}")
    return text
