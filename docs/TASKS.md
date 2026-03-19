# Tareas y Agentes — LegalIA

## Fases de Desarrollo

### Fase 1: Foundation (Semana 1-2)

| # | Tarea | Agente/Responsable | Dependencia | Estado |
|---|-------|-------------------|-------------|--------|
| 1.1 | Setup proyecto Python (pyproject.toml, requirements.txt, estructura) | Dev | - | Pendiente |
| 1.2 | Configurar CI/CD (GitHub Actions: lint, test) | Dev | 1.1 | Pendiente |
| 1.3 | Setup FastAPI base (main.py, config, health check) | Dev | 1.1 | Pendiente |
| 1.4 | Configurar Supabase (proyecto, tablas, migrations) | Dev | 1.1 | Pendiente |
| 1.5 | Integrar Twilio WhatsApp Sandbox (webhook recibe msg) | Dev | 1.3 | Pendiente |
| 1.6 | Bot echo: recibe mensaje → responde el mismo texto | Dev | 1.5 | Pendiente |
| 1.7 | Session manager básico (identifica usuario por teléfono) | Dev | 1.4, 1.6 | Pendiente |
| 1.8 | Deploy inicial a Railway/Fly.io | Dev | 1.6 | Pendiente |

### Fase 2: RAG Core (Semana 3-5)

| # | Tarea | Agente/Responsable | Dependencia | Estado |
|---|-------|-------------------|-------------|--------|
| 2.1 | Scraper de Ley Chile (BCN) — extraer top 20 leyes | Agente Scraper | - | Pendiente |
| 2.2 | Legal Chunker — split por artículo/inciso con metadata | Agente NLP | 2.1 | Pendiente |
| 2.3 | Pipeline de embeddings (Voyage AI / OpenAI) | Agente NLP | 2.2 | Pendiente |
| 2.4 | Setup Qdrant (collection, schema, upload embeddings) | Dev | 2.3 | Pendiente |
| 2.5 | Retriever básico: query → top-k documentos | Dev | 2.4 | Pendiente |
| 2.6 | Generator con Claude: docs + pregunta → respuesta con citas | Dev | 2.5 | Pendiente |
| 2.7 | RAG pipeline completo integrado | Dev | 2.6 | Pendiente |
| 2.8 | Eval set: 50 preguntas legales con respuestas esperadas | Agente Legal | 2.7 | Pendiente |
| 2.9 | Benchmark de calidad RAG (accuracy, relevance, citations) | Dev | 2.8 | Pendiente |

### Fase 3: Agente Inteligente (Semana 5-7)

| # | Tarea | Agente/Responsable | Dependencia | Estado |
|---|-------|-------------------|-------------|--------|
| 3.1 | Clasificador de intención (laboral, civil, familia, etc.) | Agente NLP | 2.7 | Pendiente |
| 3.2 | System prompts especializados por área legal | Agente Legal | 3.1 | Pendiente |
| 3.3 | Guardrails: detectar emergencias, plazos, derivar abogado | Dev | 3.1 | Pendiente |
| 3.4 | Query rewriting (pregunta coloquial → lenguaje legal) | Agente NLP | 2.7 | Pendiente |
| 3.5 | Historial conversacional (contexto multi-turno) | Dev | 1.7 | Pendiente |
| 3.6 | Formatter WhatsApp (respuestas cortas, listas, botones) | Dev | 2.6 | Pendiente |
| 3.7 | Orquestador completo: clasificar → RAG → guardrails → format | Dev | 3.1-3.6 | Pendiente |
| 3.8 | Integrar Langfuse para monitoreo de RAG | Dev | 3.7 | Pendiente |

### Fase 4: Monetización (Semana 7-9)

| # | Tarea | Agente/Responsable | Dependencia | Estado |
|---|-------|-------------------|-------------|--------|
| 4.1 | Modelo de datos: planes, suscripciones, uso | Dev | 1.4 | Pendiente |
| 4.2 | Tracking de consultas por usuario (freemium limits) | Dev | 4.1 | Pendiente |
| 4.3 | Integración MercadoPago (checkout, webhooks) | Dev | 4.1 | Pendiente |
| 4.4 | Flujo de upgrade por WhatsApp ("te quedan 0 consultas") | Dev | 4.2, 4.3 | Pendiente |
| 4.5 | Sistema de derivación a abogados | Dev | 3.3 | Pendiente |
| 4.6 | Dashboard analytics (Metabase o custom) | Dev | 1.4 | Pendiente |
| 4.7 | Onboarding de usuario nuevo por WhatsApp | Dev | 3.7 | Pendiente |

### Fase 5: Launch (Semana 9-10)

| # | Tarea | Agente/Responsable | Dependencia | Estado |
|---|-------|-------------------|-------------|--------|
| 5.1 | Landing page (Next.js o HTML simple) | Dev | - | Pendiente |
| 5.2 | Beta cerrada: 50-100 usuarios reales | Todos | 3.7 | Pendiente |
| 5.3 | Feedback loop: ajustar prompts y RAG según uso real | Agente NLP | 5.2 | Pendiente |
| 5.4 | Campaña marketing (LinkedIn, Instagram, grupos legales) | Marketing | 5.1 | Pendiente |
| 5.5 | Documentación de API y guía de contribución | Dev | 3.7 | Pendiente |

---

## Agentes Necesarios

### 1. Agente Scraper (scripts/ingest_laws.py)
**Función:** Extraer el corpus legal chileno de fuentes públicas.
- Scraping de bcn.cl/leychile (API o web scraping)
- Extraer texto completo de leyes, códigos, DFL, DL
- Preservar metadata: número ley, fecha publicación, estado vigencia
- Output: archivos JSON/markdown estructurados en `data/raw/`

### 2. Agente NLP / RAG (app/rag/)
**Función:** Pipeline de procesamiento de lenguaje natural.
- Chunking inteligente de documentos legales
- Generación de embeddings
- Hybrid retrieval (vector + keyword)
- Query rewriting
- Reranking
- Evaluación de calidad

### 3. Agente Legal (prompts + eval)
**Función:** Conocimiento legal chileno.
- Diseñar system prompts por área legal
- Crear eval set de preguntas/respuestas legales
- Validar calidad de respuestas del RAG
- Definir guardrails y casos de derivación
- Mantener actualizado el corpus cuando cambien leyes

### 4. Agente WhatsApp (app/whatsapp/)
**Función:** Comunicación bidireccional con usuarios.
- Recibir/enviar mensajes vía Twilio
- Manejar sesiones de conversación
- Formatear respuestas para WhatsApp
- Manejar botones interactivos y listas

### 5. Agente de Billing (app/billing/)
**Función:** Monetización y pagos.
- Tracking de uso por usuario
- Control de límites freemium
- Integración con pasarelas de pago chilenas
- Flujos de upgrade/downgrade

---

## Prioridades Inmediatas (Sprint 1)

1. **Setup proyecto completo** (estructura, deps, CI/CD)
2. **WhatsApp webhook funcionando** (recibe y responde)
3. **Scraper de leyes** (al menos Código del Trabajo)
4. **RAG básico** (pregunta laboral → respuesta con artículo citado)
