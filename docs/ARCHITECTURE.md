# Arquitectura LegalIA

## Visión General

LegalIA es un bot legal por WhatsApp que usa RAG (Retrieval-Augmented Generation) sobre legislación chilena para responder consultas jurídicas.

## Componentes

### 1. Canal — WhatsApp Business API

**Ubicación:** `app/whatsapp/`

- Webhook receptor de mensajes entrantes (Twilio)
- Sender de respuestas formateadas para WhatsApp
- Session manager (contexto multi-turno por número de teléfono)
- Manejo de media (fotos de documentos, audios futuros)

**Límites WhatsApp:**
- Mensaje máximo: 4,096 caracteres
- Botones interactivos: máx 3
- Listas: máx 10 items
- Rate limit: 80 msg/seg (Business API)

### 2. API Gateway

**Ubicación:** `app/api/`

- FastAPI con endpoints de webhook y health check
- Rate limiter por usuario (token bucket)
- Autenticación de webhooks (signature validation)
- Middleware de logging estructurado

### 3. Orquestador de Agentes

**Ubicación:** `app/agents/`

Pipeline de procesamiento de cada mensaje:

```
Mensaje entrante
    │
    ▼
[Clasificador de Intención]
    │ área: laboral | civil | familia | penal | comercial | otro
    ▼
[Router]
    │ selecciona agente especializado + prompt
    ▼
[RAG Pipeline]
    │ retrieval → generation
    ▼
[Guardrails]
    │ valida respuesta, detecta riesgos
    ▼
[Formatter]
    │ adapta a formato WhatsApp
    ▼
Respuesta enviada
```

**Guardrails críticos:**
- No dar plazos judiciales sin disclaimer
- Detectar emergencias (violencia, riesgo vital) → derivar a 149/Carabineros
- Detectar necesidad de abogado real → ofrecer derivación
- Detectar consultas fuera de Chile → informar limitación
- Máximo 3 intercambios sin respuesta útil → ofrecer abogado

### 4. Sistema de 3 RAGs

> Documentación completa en [`docs/RAG_SYSTEMS.md`](RAG_SYSTEMS.md)

LegalIA opera con **3 RAGs independientes** que alimentan al mismo orquestador:

```
              ┌────────────┼────────────┐
              ▼            ▼            ▼
     ┌────────────┐ ┌───────────┐ ┌───────────┐
     │  RAG Laws  │ │ RAG Docs  │ │RAG Train  │
     │ Legislación│ │ Libros/PDF│ │ Feedback  │
     └────────────┘ └───────────┘ └───────────┘
```

#### RAG 1: Laws (Legislación)
- **Ubicación:** `app/rag/laws/`
- **Collection:** `chilean_laws` (~50K chunks)
- **Fuentes:** BCN/Ley Chile, códigos, jurisprudencia, dictámenes
- **Chunking:** por artículo/inciso con jerarquía legal
- **Actualización:** cron semanal

#### RAG 2: Documents (Libros/PDFs con OCR)
- **Ubicación:** `app/rag/documents/`
- **Collection:** `legal_documents` (~20K chunks, crece)
- **Fuentes:** libros de derecho, manuales, papers, documentos escaneados
- **OCR Stack:** Tesseract + Surya + OpenCV + SymSpell
- **Chunking:** por capítulo/sección, 800-1200 tokens
- **Actualización:** bajo demanda (upload)

#### RAG 3: Training (Mejora Continua)
- **Ubicación:** `app/rag/training/`
- **Collection:** `training_knowledge` (~5K chunks, crece)
- **Fuentes:** feedback usuarios (👍/👎), correcciones de abogados, patrones de error
- **Tipos:** Q&A validados, correcciones, patrones de reformulación, anti-patrones
- **Actualización:** tiempo real

#### Query Pipeline Unificado
```
Pregunta → Query Rewriter → Router de RAGs
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
               Laws (5)    Docs (3)   Training (3)
                    │           │           │
                    └───────────┼───────────┘
                                ▼
                     Merge & Cross-RAG Rerank
                                │
                                ▼
                     LLM (Claude) + Citations
```

### 5. Data Layer

**Ubicación:** `app/models/`

#### PostgreSQL (Supabase)
- `users`: perfil por número WhatsApp
- `conversations`: historial de chats
- `messages`: mensajes individuales con metadata
- `subscriptions`: planes y billing
- `referrals`: derivaciones a abogados
- `analytics_events`: tracking de uso
- `feedback`: thumbs up/down por mensaje
- `corrections`: correcciones de abogados
- `documents`: registro de PDFs/libros cargados
- `ocr_jobs`: estado de procesamiento OCR

#### Vector Store (Qdrant) — 3 Collections
- `chilean_laws`: legislación oficial (ley, artículo, área, vigencia, fuente)
- `legal_documents`: libros/PDFs (titulo, autor, año, tipo, area, pagina, ocr_score)
- `training_knowledge`: feedback/correcciones (tipo, area, fecha, score, validado_por)
- Dimensiones: 1024 (Voyage) o 1536 (OpenAI)

### 6. Billing

**Ubicación:** `app/billing/`

- Tracking de consultas por usuario
- Control de límites freemium
- Integración MercadoPago / Flow.cl
- Webhook de confirmación de pago

## Estructura de Carpetas

```
legalia/
├── app/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                 # Settings y env vars
│   ├── api/
│   │   ├── webhooks.py           # WhatsApp webhook endpoints
│   │   ├── health.py             # Health check
│   │   └── middleware.py         # Rate limiting, logging
│   ├── agents/
│   │   ├── orchestrator.py       # Pipeline principal
│   │   ├── classifier.py         # Clasificador de intención
│   │   ├── guardrails.py         # Safety checks
│   │   └── formatter.py          # WhatsApp message formatter
│   ├── rag/
│   │   ├── router.py             # Decide qué RAGs consultar
│   │   ├── merger.py             # Merge & rerank cross-RAG
│   │   ├── generator.py          # LLM response generation
│   │   ├── citations.py          # Citation validation
│   │   ├── laws/                 # RAG 1: Legislación
│   │   │   ├── pipeline.py       # Query pipeline laws
│   │   │   ├── retriever.py      # Hybrid search laws
│   │   │   ├── chunker.py        # Legal chunker (art/inciso)
│   │   │   ├── enricher.py       # Metadata enricher
│   │   │   └── embedder.py       # Embeddings laws
│   │   ├── documents/            # RAG 2: Libros/PDFs+OCR
│   │   │   ├── pipeline.py       # Query pipeline docs
│   │   │   ├── retriever.py      # Search documents
│   │   │   ├── detector.py       # Detecta tipo PDF (texto/scan/mixto)
│   │   │   ├── ocr.py            # OCR engine (Tesseract/Surya)
│   │   │   ├── preprocessor.py   # Deskew, denoise, binarize
│   │   │   ├── layout.py         # Layout analysis
│   │   │   ├── chunker.py        # Doc chunker (cap/sección)
│   │   │   ├── metadata.py       # Extractor metadata docs
│   │   │   ├── tables.py         # Extracción de tablas
│   │   │   └── embedder.py       # Embeddings docs
│   │   └── training/             # RAG 3: Mejora continua
│   │       ├── pipeline.py       # Query pipeline training
│   │       ├── retriever.py      # Search training data
│   │       ├── collector.py      # Event collector (feedback)
│   │       ├── processor.py      # Procesa correcciones/feedback
│   │       ├── analyzer.py       # Quality analyzer (Langfuse)
│   │       ├── chunker.py        # Training data chunker
│   │       └── embedder.py       # Embeddings training
│   ├── whatsapp/
│   │   ├── client.py             # Twilio WhatsApp client
│   │   ├── session.py            # Conversation session manager
│   │   └── templates.py          # Message templates
│   ├── billing/
│   │   ├── plans.py              # Plan definitions
│   │   ├── tracker.py            # Usage tracking
│   │   └── payments.py           # MercadoPago/Flow integration
│   ├── models/
│   │   ├── user.py               # User model
│   │   ├── conversation.py       # Conversation model
│   │   ├── subscription.py       # Subscription model
│   │   ├── feedback.py           # Feedback model
│   │   └── document.py           # Document/OCR job model
│   └── utils/
│       ├── logging.py            # Structured logging
│       └── monitoring.py         # Langfuse integration
├── scripts/
│   ├── ingest_laws.py            # Corpus legal ingestion
│   ├── ingest_books.py           # PDF/book ingestion + OCR
│   ├── process_feedback.py       # Batch feedback processor
│   ├── quality_report.py         # Weekly quality report
│   └── seed_db.py                # Database seeding
├── data/
│   ├── raw/                      # Raw legal documents
│   ├── books/                    # PDFs y libros para OCR
│   ├── processed/                # Chunked documents
│   ├── feedback/                 # Feedback data exports
│   ├── training/                 # Training data sets
│   └── embeddings/               # Generated embeddings
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
│   ├── ARCHITECTURE.md           # Este archivo
│   ├── RAG_SYSTEMS.md            # Detalle de los 3 RAGs
│   ├── TASKS.md                  # Plan de tareas
│   └── API.md                    # API documentation
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
└── pyproject.toml
```

## Decisiones Técnicas

| Decisión | Opción elegida | Alternativa | Razón |
|----------|---------------|-------------|-------|
| LLM | Claude (Anthropic) | GPT-4 | Mejor en español, más seguro para legal |
| Vector DB | Qdrant | Pinecone | Self-hosted, gratis, buen rendimiento |
| WhatsApp API | Twilio | 360dialog | Mejor docs, más fácil de integrar |
| Backend | FastAPI | Django | Async nativo, más ligero para API |
| DB | Supabase | Firebase | PostgreSQL, mejor para datos estructurados |
| Pagos | MercadoPago | Stripe | Estándar en Chile, Flow.cl como backup |
