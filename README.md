# LegalIA 🇨🇱

Bot legal por WhatsApp con inteligencia artificial para Chile.

Consultas legales instantáneas basadas en legislación chilena, impulsadas por RAG (Retrieval-Augmented Generation).

## Qué es

LegalIA es un asistente legal por WhatsApp que permite a cualquier persona hacer consultas legales y recibir orientación jurídica instantánea basada en la legislación chilena vigente.

## Problema

- El acceso a asesoría legal en Chile es caro y lento
- Las consultas iniciales con abogados cuestan $30.000-$80.000 CLP
- El 90% de los chilenos usa WhatsApp diariamente
- No existe un bot legal por WhatsApp dominante en Chile

## Solución

Un bot de WhatsApp que:
- Responde consultas legales 24/7 en lenguaje simple
- Cita artículos específicos de la ley chilena
- Cubre derecho laboral, civil, familiar, comercial y penal
- Deriva a abogados reales cuando el caso lo requiere
- Modelo freemium accesible

## Stack

| Componente | Tecnología |
|-----------|-----------|
| WhatsApp API | Twilio / 360dialog |
| Backend | Python (FastAPI) |
| LLM | Claude API (Anthropic) |
| Embeddings | Voyage AI / OpenAI |
| Vector DB | Qdrant / pgvector |
| Base de datos | Supabase (PostgreSQL) |
| Hosting | Railway / Fly.io |
| Pagos | MercadoPago + Flow.cl |
| Monitoreo RAG | Langfuse |

## Arquitectura

```
Usuario (WhatsApp)
    │
    ▼
WhatsApp Business API (Twilio)
    │
    ▼
API Gateway (FastAPI)
    │
    ▼
Orquestador de Agentes
  ├── Clasificador de intención
  ├── Guardrails & Safety
  └── Formatter WhatsApp
    │
    ▼
RAG Pipeline
  ├── Query Rewriting
  ├── Hybrid Search (Vector + BM25)
  └── LLM + Citations
    │
    ▼
Data Stores
  ├── PostgreSQL (usuarios, billing, analytics)
  └── Vector Store (corpus legal chileno)
```

## Corpus Legal

Fuentes indexadas:
- Códigos: Civil, Penal, del Trabajo, de Comercio
- Leyes especiales (Ley Karin, Consumidor, Insolvencia, etc.)
- Jurisprudencia: Corte Suprema, Cortes de Apelaciones
- Dictámenes: Dirección del Trabajo, Contraloría, SII

## Desarrollo

```bash
# Setup
pip install -r requirements.txt
cp .env.example .env

# Run
uvicorn app.main:app --reload

# Tests
pytest
```

## Licencia

MIT
