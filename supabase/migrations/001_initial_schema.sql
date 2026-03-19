-- ============================================================
-- LegalIA — Schema Inicial
-- Bot legal WhatsApp con 3 RAGs para Chile
-- ============================================================

-- Extensiones
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 1. USUARIOS
-- ============================================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone VARCHAR(20) UNIQUE NOT NULL,          -- +56912345678
    display_name VARCHAR(100),
    country_code VARCHAR(5) DEFAULT 'CL',
    language VARCHAR(5) DEFAULT 'es',
    plan VARCHAR(20) DEFAULT 'free',            -- free, pro, premium
    queries_used_this_month INT DEFAULT 0,
    queries_limit INT DEFAULT 5,                -- free = 5/mes
    is_active BOOLEAN DEFAULT TRUE,
    is_blocked BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',                -- datos extra flexibles
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_phone ON users(phone);
CREATE INDEX idx_users_plan ON users(plan);
CREATE INDEX idx_users_last_active ON users(last_active_at);

-- ============================================================
-- 2. CONVERSACIONES
-- ============================================================
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'active',        -- active, closed, archived
    area_legal VARCHAR(30),                     -- laboral, civil, familia, penal, comercial
    summary TEXT,                                -- resumen auto-generado
    message_count INT DEFAULT 0,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_conversations_status ON conversations(status);
CREATE INDEX idx_conversations_area ON conversations(area_legal);

-- ============================================================
-- 3. MENSAJES
-- ============================================================
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(10) NOT NULL,                  -- user, assistant
    content TEXT NOT NULL,

    -- RAG metadata (solo para role=assistant)
    rag_sources JSONB,                          -- [{rag: "laws", doc_id: "...", score: 0.95}]
    citations JSONB,                            -- [{ley: "21643", art: "1", texto: "..."}]
    area_detected VARCHAR(30),                  -- área legal detectada
    confidence_score FLOAT,                     -- confianza de la respuesta
    retrieval_scores JSONB,                     -- scores de retrieval por RAG

    -- WhatsApp metadata
    whatsapp_message_id VARCHAR(100),
    media_type VARCHAR(20),                     -- text, image, document, audio
    media_url TEXT,

    tokens_used INT,
    latency_ms INT,                             -- tiempo de respuesta
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_user ON messages(user_id);
CREATE INDEX idx_messages_created ON messages(created_at);

-- ============================================================
-- 4. FEEDBACK
-- ============================================================
CREATE TABLE feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    rating VARCHAR(10) NOT NULL,                -- positive, negative
    comment TEXT,                                -- comentario opcional del usuario

    -- Para el RAG Training
    question TEXT NOT NULL,                      -- pregunta original
    answer TEXT NOT NULL,                        -- respuesta que recibió feedback
    area_legal VARCHAR(30),
    rag_sources JSONB,                          -- de qué RAGs vino la respuesta

    -- Processing status
    processed BOOLEAN DEFAULT FALSE,            -- ya fue procesado por training pipeline
    processed_at TIMESTAMPTZ,
    training_action VARCHAR(30),                -- qa_validated, failure_flagged, needs_review

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_feedback_message ON feedback(message_id);
CREATE INDEX idx_feedback_rating ON feedback(rating);
CREATE INDEX idx_feedback_processed ON feedback(processed);
CREATE INDEX idx_feedback_area ON feedback(area_legal);

-- ============================================================
-- 5. CORRECCIONES DE ABOGADOS
-- ============================================================
CREATE TABLE corrections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    feedback_id UUID REFERENCES feedback(id) ON DELETE SET NULL,

    -- Contenido
    question TEXT NOT NULL,
    original_answer TEXT NOT NULL,
    corrected_answer TEXT NOT NULL,
    correction_reason TEXT,
    area_legal VARCHAR(30),

    -- Quién corrigió
    corrected_by UUID REFERENCES users(id),     -- abogado de la red
    lawyer_name VARCHAR(100),
    lawyer_specialty VARCHAR(50),

    -- Processing
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_corrections_processed ON corrections(processed);
CREATE INDEX idx_corrections_area ON corrections(area_legal);

-- ============================================================
-- 6. DOCUMENTOS (PDFs / Libros para RAG Documents)
-- ============================================================
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(300) NOT NULL,
    author VARCHAR(200),
    year INT,
    document_type VARCHAR(30) NOT NULL,         -- book, manual, paper, form, other
    area_legal VARCHAR(30),

    -- Archivo
    file_name VARCHAR(300) NOT NULL,
    file_path TEXT,                              -- path en storage
    file_size_bytes BIGINT,
    file_hash VARCHAR(64),                      -- SHA-256 para dedup
    page_count INT,

    -- OCR
    ocr_status VARCHAR(20) DEFAULT 'pending',   -- pending, processing, completed, failed
    ocr_type VARCHAR(20),                       -- native_text, scanned, mixed
    ocr_score FLOAT,                            -- confianza promedio OCR (0-1)
    ocr_engine VARCHAR(30),                     -- tesseract, surya, pymupdf
    ocr_started_at TIMESTAMPTZ,
    ocr_completed_at TIMESTAMPTZ,
    ocr_error TEXT,

    -- Indexación
    chunk_count INT DEFAULT 0,
    indexed BOOLEAN DEFAULT FALSE,
    indexed_at TIMESTAMPTZ,

    metadata JSONB DEFAULT '{}',
    uploaded_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_documents_type ON documents(document_type);
CREATE INDEX idx_documents_area ON documents(area_legal);
CREATE INDEX idx_documents_ocr_status ON documents(ocr_status);
CREATE INDEX idx_documents_hash ON documents(file_hash);

-- ============================================================
-- 7. SUSCRIPCIONES
-- ============================================================
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan VARCHAR(20) NOT NULL,                  -- pro, premium
    status VARCHAR(20) DEFAULT 'active',        -- active, cancelled, expired, past_due

    -- Pagos
    payment_provider VARCHAR(20),               -- mercadopago, flow
    external_subscription_id VARCHAR(100),
    external_customer_id VARCHAR(100),

    -- Periodo
    price_clp INT NOT NULL,                     -- precio en CLP
    billing_cycle VARCHAR(10) DEFAULT 'monthly',-- monthly, yearly
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,

    cancelled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);

-- ============================================================
-- 8. PAGOS
-- ============================================================
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,

    amount_clp INT NOT NULL,
    currency VARCHAR(3) DEFAULT 'CLP',
    status VARCHAR(20) NOT NULL,                -- pending, completed, failed, refunded

    payment_provider VARCHAR(20),               -- mercadopago, flow
    external_payment_id VARCHAR(100),
    payment_method VARCHAR(30),                 -- credit_card, debit_card, transfer

    description TEXT,
    metadata JSONB DEFAULT '{}',

    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_payments_user ON payments(user_id);
CREATE INDEX idx_payments_status ON payments(status);

-- ============================================================
-- 9. DERIVACIONES A ABOGADOS
-- ============================================================
CREATE TABLE referrals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,

    area_legal VARCHAR(30) NOT NULL,
    reason TEXT,                                 -- por qué se derivó
    user_summary TEXT,                           -- resumen del caso para el abogado

    -- Abogado asignado
    lawyer_name VARCHAR(100),
    lawyer_phone VARCHAR(20),
    lawyer_email VARCHAR(200),
    lawyer_specialty VARCHAR(50),

    -- Estado
    status VARCHAR(20) DEFAULT 'pending',       -- pending, contacted, accepted, completed, cancelled
    commission_clp INT,                         -- comisión por derivación

    contacted_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_referrals_user ON referrals(user_id);
CREATE INDEX idx_referrals_status ON referrals(status);
CREATE INDEX idx_referrals_area ON referrals(area_legal);

-- ============================================================
-- 10. ANALYTICS EVENTS
-- ============================================================
CREATE TABLE analytics_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    event_type VARCHAR(50) NOT NULL,            -- query, feedback, upgrade, referral, error
    event_data JSONB DEFAULT '{}',

    -- Contexto
    area_legal VARCHAR(30),
    rag_used VARCHAR(30),                       -- laws, documents, training, multi
    session_id VARCHAR(100),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_analytics_type ON analytics_events(event_type);
CREATE INDEX idx_analytics_user ON analytics_events(user_id);
CREATE INDEX idx_analytics_created ON analytics_events(created_at);
CREATE INDEX idx_analytics_area ON analytics_events(area_legal);

-- ============================================================
-- 11. TRAINING DATA (registro de datos generados para RAG Training)
-- ============================================================
CREATE TABLE training_data (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type VARCHAR(30) NOT NULL,                  -- qa_validated, lawyer_correction, reformulation, anti_pattern

    -- Contenido
    question TEXT,
    answer TEXT,
    corrected_answer TEXT,
    correction_reason TEXT,
    pattern_from TEXT,                           -- para reformulaciones: versión coloquial
    pattern_to TEXT,                             -- para reformulaciones: versión legal
    anti_pattern_scenario TEXT,
    anti_pattern_bad_response TEXT,
    anti_pattern_correct_approach TEXT,

    area_legal VARCHAR(30),
    source VARCHAR(30),                         -- user_feedback, lawyer_correction, auto_extracted
    confidence_score FLOAT,

    -- Indexación en Qdrant
    indexed BOOLEAN DEFAULT FALSE,
    indexed_at TIMESTAMPTZ,
    qdrant_point_id VARCHAR(100),

    -- Origen
    feedback_id UUID REFERENCES feedback(id) ON DELETE SET NULL,
    correction_id UUID REFERENCES corrections(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_training_type ON training_data(type);
CREATE INDEX idx_training_area ON training_data(area_legal);
CREATE INDEX idx_training_indexed ON training_data(indexed);
CREATE INDEX idx_training_source ON training_data(source);

-- ============================================================
-- FUNCIONES HELPER
-- ============================================================

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tr_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER tr_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER tr_subscriptions_updated_at
    BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Reset queries mensuales (ejecutar con cron de Supabase)
CREATE OR REPLACE FUNCTION reset_monthly_queries()
RETURNS void AS $$
BEGIN
    UPDATE users SET queries_used_this_month = 0;
END;
$$ LANGUAGE plpgsql;

-- Incrementar contador de queries
CREATE OR REPLACE FUNCTION increment_user_queries(p_user_id UUID)
RETURNS TABLE(queries_remaining INT, limit_reached BOOLEAN) AS $$
DECLARE
    v_used INT;
    v_limit INT;
BEGIN
    UPDATE users
    SET queries_used_this_month = queries_used_this_month + 1,
        last_active_at = NOW()
    WHERE id = p_user_id
    RETURNING queries_used_this_month, queries_limit INTO v_used, v_limit;

    RETURN QUERY SELECT (v_limit - v_used) AS queries_remaining,
                        (v_used >= v_limit) AS limit_reached;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================

-- Habilitar RLS en todas las tablas
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;

-- Política: service_role puede todo (backend usa service_role key)
CREATE POLICY "Service role full access" ON users
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON conversations
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON messages
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON feedback
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON subscriptions
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON payments
    FOR ALL USING (auth.role() = 'service_role');
