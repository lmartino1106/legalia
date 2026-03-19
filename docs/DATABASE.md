# Base de Datos — LegalIA

## Diagrama de Relaciones (ERD)

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────┐
│    users     │       │  conversations   │       │   messages   │
├──────────────┤       ├──────────────────┤       ├──────────────┤
│ id (PK)      │──┐    │ id (PK)          │──┐    │ id (PK)      │
│ phone        │  │    │ user_id (FK)     │  │    │ conversation │
│ display_name │  ├───>│ status           │  ├───>│   _id (FK)   │
│ plan         │  │    │ area_legal       │  │    │ user_id (FK) │
│ queries_used │  │    │ summary          │  │    │ role         │
│ queries_limit│  │    │ message_count    │  │    │ content      │
│ is_active    │  │    │ started_at       │  │    │ rag_sources  │
│ last_active  │  │    │ last_message_at  │  │    │ citations    │
└──────────────┘  │    └──────────────────┘  │    │ confidence   │
                  │                           │    │ latency_ms   │
                  │                           │    └──────┬───────┘
                  │                           │           │
                  │    ┌──────────────────┐   │    ┌──────┴───────┐
                  │    │    feedback      │   │    │  (feedback   │
                  │    ├──────────────────┤   │    │   links to   │
                  ├───>│ id (PK)          │<──┘    │   messages)  │
                  │    │ message_id (FK)  │        └──────────────┘
                  │    │ user_id (FK)     │
                  │    │ rating (👍/👎)   │
                  │    │ question         │───────┐
                  │    │ answer           │       │
                  │    │ processed        │       │
                  │    └──────────────────┘       │
                  │                               │
                  │    ┌──────────────────┐       │    ┌──────────────────┐
                  │    │   corrections   │       │    │  training_data   │
                  │    ├──────────────────┤       │    ├──────────────────┤
                  ├───>│ id (PK)          │       └───>│ id (PK)          │
                  │    │ message_id (FK)  │            │ type             │
                  │    │ feedback_id (FK) │───────────>│ feedback_id (FK) │
                  │    │ question         │            │ correction_id    │
                  │    │ original_answer  │            │ question         │
                  │    │ corrected_answer │            │ answer           │
                  │    │ corrected_by(FK) │            │ area_legal       │
                  │    │ processed        │            │ indexed (Qdrant) │
                  │    └──────────────────┘            └──────────────────┘
                  │
                  │    ┌──────────────────┐    ┌──────────────────┐
                  │    │  subscriptions   │    │    payments     │
                  │    ├──────────────────┤    ├──────────────────┤
                  ├───>│ id (PK)          │<───│ id (PK)          │
                  │    │ user_id (FK)     │    │ user_id (FK)     │
                  │    │ plan             │    │ subscription_id  │
                  │    │ status           │    │ amount_clp       │
                  │    │ payment_provider │    │ status           │
                  │    │ price_clp        │    │ payment_provider │
                  │    └──────────────────┘    └──────────────────┘
                  │
                  │    ┌──────────────────┐    ┌──────────────────┐
                  │    │    referrals    │    │    documents     │
                  │    ├──────────────────┤    ├──────────────────┤
                  ├───>│ id (PK)          │    │ id (PK)          │
                  │    │ user_id (FK)     │    │ title            │
                  │    │ conversation_id  │    │ author           │
                  │    │ area_legal       │    │ document_type    │
                  │    │ lawyer_name      │    │ ocr_status       │
                  │    │ status           │    │ ocr_score        │
                  │    │ commission_clp   │    │ chunk_count      │
                  │    └──────────────────┘    │ indexed          │
                  │                            │ uploaded_by (FK) │
                  │                            └──────────────────┘
                  │
                  │    ┌──────────────────┐
                  └───>│ analytics_events │
                       ├──────────────────┤
                       │ id (PK)          │
                       │ user_id (FK)     │
                       │ event_type       │
                       │ event_data       │
                       │ area_legal       │
                       │ rag_used         │
                       └──────────────────┘
```

## Tablas (11)

| Tabla | Propósito | Relación principal |
|-------|----------|-------------------|
| `users` | Usuarios por número WhatsApp | Centro de todo |
| `conversations` | Sesiones de chat | users → conversations |
| `messages` | Mensajes individuales con RAG metadata | conversations → messages |
| `feedback` | 👍/👎 por respuesta | messages → feedback |
| `corrections` | Correcciones de abogados | feedback → corrections |
| `training_data` | Datos generados para RAG Training | feedback/corrections → training_data |
| `documents` | PDFs/libros para RAG Documents + OCR | Stand-alone con uploaded_by |
| `subscriptions` | Planes de pago | users → subscriptions |
| `payments` | Transacciones | users/subscriptions → payments |
| `referrals` | Derivaciones a abogados | users/conversations → referrals |
| `analytics_events` | Tracking de eventos | users → analytics_events |

## Funciones SQL

| Función | Propósito |
|---------|----------|
| `update_updated_at()` | Trigger: auto-actualiza `updated_at` |
| `reset_monthly_queries()` | Cron mensual: resetea contadores de consultas gratis |
| `increment_user_queries(user_id)` | Incrementa uso y retorna si alcanzó el límite |

## Flujos de datos clave

### Consulta de usuario
```
WhatsApp msg → users (find/create) → conversations (find/create) → messages (insert query)
    → RAG pipeline → messages (insert response) → WhatsApp reply
```

### Feedback y training
```
Usuario da 👍/👎 → feedback (insert) → training pipeline procesa
    → training_data (insert) → embeddings → Qdrant training_knowledge
```

### Corrección de abogado
```
Abogado revisa → corrections (insert) → training pipeline procesa
    → training_data (insert tipo lawyer_correction) → Qdrant
```

### OCR de documento
```
Upload PDF → documents (insert, status=pending) → OCR pipeline
    → documents (update status=completed, ocr_score) → chunking → Qdrant legal_documents
```

## Setup

### Opción 1: Supabase Cloud
1. Crear proyecto en supabase.com
2. Ir a SQL Editor
3. Pegar contenido de `supabase/migrations/001_initial_schema.sql`
4. Ejecutar

### Opción 2: Supabase CLI
```bash
npx supabase init
npx supabase db push
```

### Opción 3: PostgreSQL local (Docker)
```bash
docker run -d --name legalia-db -p 5432:5432 \
  -e POSTGRES_DB=legalia \
  -e POSTGRES_PASSWORD=legalia123 \
  postgres:16

psql -h localhost -U postgres -d legalia -f supabase/migrations/001_initial_schema.sql
```
