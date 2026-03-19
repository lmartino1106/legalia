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
| 1.9 | Setup Qdrant (3 collections: laws, documents, training) | Dev | 1.1 | Pendiente |

### Fase 2: RAG Laws — Legislación (Semana 3-5)

| # | Tarea | Agente/Responsable | Dependencia | Estado |
|---|-------|-------------------|-------------|--------|
| 2.1 | Scraper de Ley Chile (BCN) — extraer top 20 leyes | Agente Scraper | - | Pendiente |
| 2.2 | Legal Chunker — split por artículo/inciso con metadata | Agente NLP | 2.1 | Pendiente |
| 2.3 | Metadata enricher (área legal, vigencia, relaciones) | Agente NLP | 2.2 | Pendiente |
| 2.4 | Pipeline de embeddings (Voyage AI / OpenAI) | Agente NLP | 2.3 | Pendiente |
| 2.5 | Upload a Qdrant collection `chilean_laws` | Dev | 2.4, 1.9 | Pendiente |
| 2.6 | Retriever híbrido: vector + BM25 + filtro área | Dev | 2.5 | Pendiente |
| 2.7 | Reranker (Cohere o cross-encoder) | Dev | 2.6 | Pendiente |
| 2.8 | Generator con Claude: docs + pregunta → respuesta con citas | Dev | 2.7 | Pendiente |
| 2.9 | Citation validator (verificar artículos citados existen) | Dev | 2.8 | Pendiente |
| 2.10 | RAG Laws pipeline completo integrado | Dev | 2.9 | Pendiente |
| 2.11 | Eval set: 50 preguntas legales con respuestas esperadas | Agente Legal | 2.10 | Pendiente |
| 2.12 | Benchmark de calidad RAG (accuracy, relevance, citations) | Dev | 2.11 | Pendiente |

### Fase 3: RAG Documents — Libros/PDFs con OCR (Semana 5-7)

| # | Tarea | Agente/Responsable | Dependencia | Estado |
|---|-------|-------------------|-------------|--------|
| 3.1 | File detector: clasificar PDF (texto nativo/escaneado/mixto) | Agente OCR | - | Pendiente |
| 3.2 | Extractor texto nativo (PyMuPDF/pdfplumber) | Agente OCR | 3.1 | Pendiente |
| 3.3 | Pre-procesamiento imagen (deskew, denoise, binarize, 300 DPI) | Agente OCR | 3.1 | Pendiente |
| 3.4 | Layout analysis (detectar columnas, tablas, headers, footnotes) | Agente OCR | 3.3 | Pendiente |
| 3.5 | OCR engine integration (Tesseract 5 spa + Surya fallback) | Agente OCR | 3.4 | Pendiente |
| 3.6 | Extractor de tablas (Camelot → markdown tables) | Agente OCR | 3.4 | Pendiente |
| 3.7 | Post-OCR: corrección ortográfica legal (SymSpell + dict jurídico) | Agente NLP | 3.5 | Pendiente |
| 3.8 | Quality scoring (confianza OCR por página/documento) | Agente OCR | 3.5 | Pendiente |
| 3.9 | Document chunker (por capítulo/sección, 800-1200 tokens) | Agente NLP | 3.7 | Pendiente |
| 3.10 | Metadata extractor (título, autor, año, área, ToC) | Agente NLP | 3.7 | Pendiente |
| 3.11 | Embeddings + upload a Qdrant `legal_documents` | Dev | 3.9, 3.10, 1.9 | Pendiente |
| 3.12 | Retriever documents con penalización por OCR score bajo | Dev | 3.11 | Pendiente |
| 3.13 | Script CLI batch ingestion (`scripts/ingest_books.py`) | Dev | 3.1-3.12 | Pendiente |
| 3.14 | Test con 5 PDFs reales (2 texto, 2 escaneados, 1 mixto) | QA | 3.13 | Pendiente |

### Fase 4: RAG Training — Mejora Continua (Semana 7-8)

| # | Tarea | Agente/Responsable | Dependencia | Estado |
|---|-------|-------------------|-------------|--------|
| 4.1 | Feedback capture: botones 👍/👎 en WhatsApp post-respuesta | Dev | 1.6 | Pendiente |
| 4.2 | Event collector: captura pregunta + respuesta + feedback | Dev | 4.1 | Pendiente |
| 4.3 | Q&A pair creator: convierte feedback positivo en training data | Agente NLP | 4.2 | Pendiente |
| 4.4 | Failure analyzer: clasifica feedback negativo (retrieval/generation) | Agente NLP | 4.2 | Pendiente |
| 4.5 | Correction processor: ingiere correcciones de abogados | Dev | 4.2 | Pendiente |
| 4.6 | Anti-pattern extractor: detecta patrones de error recurrentes | Agente NLP | 4.4 | Pendiente |
| 4.7 | Reformulation pattern learner: coloquial → legal mapping | Agente NLP | 4.3 | Pendiente |
| 4.8 | Training chunker + embedder + upload a Qdrant `training_knowledge` | Dev | 4.3-4.7, 1.9 | Pendiente |
| 4.9 | Training retriever (boost Q&A validados, boost correcciones) | Dev | 4.8 | Pendiente |
| 4.10 | Quality analyzer con Langfuse (gaps por área, tasa de error) | Dev | 3.8 (Fase 3) | Pendiente |
| 4.11 | Jobs automáticos: feedback processor (RT), quality report (semanal) | Dev | 4.10 | Pendiente |
| 4.12 | Dashboard de correcciones para abogados (web simple) | Dev | 4.5 | Pendiente |

### Fase 5: Orquestador Multi-RAG (Semana 8-9)

| # | Tarea | Agente/Responsable | Dependencia | Estado |
|---|-------|-------------------|-------------|--------|
| 5.1 | RAG Router: decide qué RAGs consultar según pregunta | Dev | 2.10, 3.12, 4.9 | Pendiente |
| 5.2 | Parallel retrieval: consulta múltiples RAGs simultáneamente | Dev | 5.1 | Pendiente |
| 5.3 | Cross-RAG merger & deduplicator | Dev | 5.2 | Pendiente |
| 5.4 | Cross-RAG reranker con ponderación (Laws > Training > Docs) | Dev | 5.3 | Pendiente |
| 5.5 | Context builder: arma contexto multi-fuente para LLM | Dev | 5.4 | Pendiente |
| 5.6 | Clasificador de intención (laboral, civil, familia, etc.) | Agente NLP | 2.10 | Pendiente |
| 5.7 | System prompts especializados por área legal | Agente Legal | 5.6 | Pendiente |
| 5.8 | Guardrails: emergencias, plazos, derivar abogado | Dev | 5.6 | Pendiente |
| 5.9 | Query rewriting (coloquial → legal) | Agente NLP | 2.10 | Pendiente |
| 5.10 | Formatter WhatsApp (respuestas cortas, listas, botones) | Dev | 5.5 | Pendiente |
| 5.11 | Orquestador completo end-to-end | Dev | 5.1-5.10 | Pendiente |
| 5.12 | Integrar Langfuse para monitoreo multi-RAG | Dev | 5.11 | Pendiente |

### Fase 6: Monetización (Semana 9-10)

| # | Tarea | Agente/Responsable | Dependencia | Estado |
|---|-------|-------------------|-------------|--------|
| 6.1 | Modelo de datos: planes, suscripciones, uso | Dev | 1.4 | Pendiente |
| 6.2 | Tracking de consultas por usuario (freemium limits) | Dev | 6.1 | Pendiente |
| 6.3 | Integración MercadoPago (checkout, webhooks) | Dev | 6.1 | Pendiente |
| 6.4 | Flujo de upgrade por WhatsApp ("te quedan 0 consultas") | Dev | 6.2, 6.3 | Pendiente |
| 6.5 | Sistema de derivación a abogados | Dev | 5.8 | Pendiente |
| 6.6 | Dashboard analytics (Metabase o custom) | Dev | 1.4 | Pendiente |
| 6.7 | Onboarding de usuario nuevo por WhatsApp | Dev | 5.11 | Pendiente |

### Fase 7: Launch (Semana 10-12)

| # | Tarea | Agente/Responsable | Dependencia | Estado |
|---|-------|-------------------|-------------|--------|
| 7.1 | Landing page (Next.js o HTML simple) | Dev | - | Pendiente |
| 7.2 | Beta cerrada: 50-100 usuarios reales | Todos | 5.11 | Pendiente |
| 7.3 | Feedback loop: ajustar prompts y RAG según uso real | Agente NLP | 7.2 | Pendiente |
| 7.4 | Campaña marketing (LinkedIn, Instagram, grupos legales) | Marketing | 7.1 | Pendiente |
| 7.5 | Documentación de API y guía de contribución | Dev | 5.11 | Pendiente |
| 7.6 | Cron de actualización semanal de leyes (BCN) | Dev | 2.1 | Pendiente |

---

## Agentes Necesarios (7)

### 1. Agente Scraper Legal
**Módulo:** `scripts/ingest_laws.py`
**Función:** Extraer corpus legal chileno de fuentes públicas.
- Scraping de bcn.cl/leychile (API o web scraping)
- Extraer texto completo de leyes, códigos, DFL, DL
- Preservar metadata: número ley, fecha publicación, vigencia
- Detectar actualizaciones/modificaciones de leyes existentes
- Output: JSON/markdown estructurados en `data/raw/`

### 2. Agente NLP / RAG
**Módulo:** `app/rag/` (shared across all 3 RAGs)
**Función:** Pipeline de procesamiento de lenguaje natural.
- Chunking inteligente (legal + documentos + training)
- Generación de embeddings
- Hybrid retrieval (vector + BM25)
- Query rewriting (coloquial → legal)
- Reranking (single-RAG y cross-RAG)
- Reformulation pattern learning
- Evaluación de calidad

### 3. Agente OCR / Document Processing
**Módulo:** `app/rag/documents/`
**Función:** Procesar PDFs y documentos escaneados.
- Detección de tipo (texto nativo, escaneado, mixto)
- Pre-procesamiento de imágenes (deskew, denoise, binarize)
- Layout analysis (columnas, tablas, headers)
- OCR con Tesseract 5 + Surya
- Extracción de tablas (Camelot)
- Post-OCR con corrección ortográfica legal
- Quality scoring por documento

### 4. Agente Legal (Conocimiento)
**Módulo:** prompts, eval sets, guardrails
**Función:** Expertise legal chileno.
- System prompts especializados por área
- Eval set de preguntas/respuestas legales
- Validar calidad de respuestas
- Definir guardrails y casos de derivación
- Diseñar anti-patrones
- Revisar correcciones de abogados

### 5. Agente WhatsApp
**Módulo:** `app/whatsapp/`
**Función:** Comunicación bidireccional.
- Recibir/enviar mensajes vía Twilio
- Manejar sesiones de conversación
- Formatear respuestas para WhatsApp
- Botones interactivos (feedback 👍/👎, derivación)
- Flujos conversacionales (onboarding, upgrade)

### 6. Agente de Billing
**Módulo:** `app/billing/`
**Función:** Monetización y pagos.
- Tracking de uso por usuario
- Control de límites freemium
- Integración MercadoPago / Flow.cl
- Flujos de upgrade/downgrade por WhatsApp

### 7. Agente de Training / Quality
**Módulo:** `app/rag/training/`
**Función:** Mejora continua del sistema.
- Recolectar y procesar feedback de usuarios
- Analizar fallos (retrieval vs generation)
- Procesar correcciones de abogados
- Extraer anti-patrones de errores recurrentes
- Generar reportes de calidad semanales
- Mantener y actualizar training knowledge base
- Monitorear métricas (hit rate, correction rate, feedback ratio)

---

## Resumen de Tareas

| Fase | Nombre | Tareas | Semanas |
|------|--------|--------|---------|
| 1 | Foundation | 9 | 1-2 |
| 2 | RAG Laws | 12 | 3-5 |
| 3 | RAG Documents + OCR | 14 | 5-7 |
| 4 | RAG Training | 12 | 7-8 |
| 5 | Orquestador Multi-RAG | 12 | 8-9 |
| 6 | Monetización | 7 | 9-10 |
| 7 | Launch | 6 | 10-12 |
| **Total** | | **72 tareas** | **12 semanas** |

---

## Prioridades Inmediatas (Sprint 1)

1. **Setup proyecto completo** (estructura, deps, CI/CD)
2. **WhatsApp webhook funcionando** (recibe y responde)
3. **Setup Qdrant** (3 collections vacías)
4. **Scraper de leyes** (al menos Código del Trabajo)
5. **RAG Laws básico** (pregunta laboral → respuesta con artículo citado)
