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

### 4. RAG Pipeline

**Ubicación:** `app/rag/`

#### 4.1 Ingestion Pipeline (offline)
```
Fuente legal (BCN/Ley Chile)
    │
    ▼
[Scraper/Extractor]
    │ extrae texto + metadata
    ▼
[Legal Chunker]
    │ split por artículo/inciso, preserva jerarquía
    ▼
[Embeddings]
    │ Voyage AI o OpenAI
    ▼
[Vector Store]
    │ Qdrant con metadata filtering
    ▼
Corpus indexado
```

#### 4.2 Query Pipeline (online)
```
Pregunta del usuario
    │
    ▼
[Query Rewriter]
    │ reformula en lenguaje legal
    ▼
[Hybrid Search]
    │ vector similarity + BM25 keyword
    │ filtro por área legal
    ▼
[Reranker]
    │ Cohere Rerank o cross-encoder
    │ top-k documentos relevantes
    ▼
[LLM (Claude)]
    │ genera respuesta con citations
    │ system prompt: orientador legal
    ▼
[Citation Validator]
    │ verifica que artículos citados existen
    ▼
Respuesta con citas
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

#### Vector Store (Qdrant)
- Collection: `chilean_law`
- Metadata: ley, artículo, área, vigencia, fuente
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
│   ├── main.py              # FastAPI app entry point
│   ├── config.py             # Settings y env vars
│   ├── api/
│   │   ├── webhooks.py       # WhatsApp webhook endpoints
│   │   ├── health.py         # Health check
│   │   └── middleware.py     # Rate limiting, logging
│   ├── agents/
│   │   ├── orchestrator.py   # Pipeline principal
│   │   ├── classifier.py     # Clasificador de intención
│   │   ├── guardrails.py     # Safety checks
│   │   └── formatter.py      # WhatsApp message formatter
│   ├── rag/
│   │   ├── pipeline.py       # Query pipeline completo
│   │   ├── retriever.py      # Hybrid search
│   │   ├── reranker.py       # Reranking
│   │   ├── generator.py      # LLM response generation
│   │   └── citations.py      # Citation validation
│   ├── whatsapp/
│   │   ├── client.py         # Twilio WhatsApp client
│   │   ├── session.py        # Conversation session manager
│   │   └── templates.py      # Message templates
│   ├── billing/
│   │   ├── plans.py          # Plan definitions
│   │   ├── tracker.py        # Usage tracking
│   │   └── payments.py       # MercadoPago/Flow integration
│   ├── models/
│   │   ├── user.py           # User model
│   │   ├── conversation.py   # Conversation model
│   │   └── subscription.py   # Subscription model
│   └── utils/
│       ├── logging.py        # Structured logging
│       └── monitoring.py     # Langfuse integration
├── scripts/
│   ├── ingest_laws.py        # Corpus ingestion pipeline
│   ├── chunk_laws.py         # Legal document chunker
│   └── seed_db.py            # Database seeding
├── data/
│   ├── raw/                  # Raw legal documents
│   ├── processed/            # Chunked documents
│   └── embeddings/           # Generated embeddings
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
│   ├── ARCHITECTURE.md       # Este archivo
│   └── API.md                # API documentation
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
