-- =============================================================
-- Baton Agency Conversion Engine — Supabase PostgreSQL Schema
-- =============================================================
-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================
-- SECTION 1 — SERVICE CATALOGUE & PRICING
-- =============================================================

CREATE TABLE service_catalogue (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    description     TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_service_catalogue_category  ON service_catalogue (category);
CREATE INDEX idx_service_catalogue_metadata  ON service_catalogue USING GIN (metadata);

CREATE TABLE pricing_rules (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_id      UUID NOT NULL REFERENCES service_catalogue(id) ON DELETE CASCADE,
    tier            TEXT NOT NULL DEFAULT 'standard',         -- e.g. standard | premium | enterprise
    unit_price      NUMERIC(12, 4) NOT NULL,
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    min_quantity    INT NOT NULL DEFAULT 1,
    max_quantity    INT,
    valid_from      DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_until     DATE,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_pricing_rules_service_id    ON pricing_rules (service_id);
CREATE INDEX idx_pricing_rules_tier          ON pricing_rules (tier);

-- =============================================================
-- SECTION 2 — ACCOUNTS, CONTACTS & LEADS
-- =============================================================

CREATE TABLE accounts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    domain          TEXT,
    industry        TEXT,
    employee_count  INT,
    annual_revenue  NUMERIC(18, 2),
    country         CHAR(2),
    stage           TEXT NOT NULL DEFAULT 'prospect',         -- prospect | customer | churned
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_accounts_domain             ON accounts (domain);
CREATE INDEX idx_accounts_stage              ON accounts (stage);
CREATE INDEX idx_accounts_metadata           ON accounts USING GIN (metadata);

CREATE TABLE contacts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id      UUID REFERENCES accounts(id) ON DELETE SET NULL,
    first_name      TEXT,
    last_name       TEXT,
    email           TEXT,
    phone           TEXT,
    title           TEXT,
    linkedin_url    TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_contacts_account_id         ON contacts (account_id);
CREATE INDEX idx_contacts_email              ON contacts (email);
CREATE INDEX idx_contacts_metadata           ON contacts USING GIN (metadata);

CREATE TABLE leads (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id      UUID REFERENCES accounts(id) ON DELETE SET NULL,
    contact_id      UUID REFERENCES contacts(id) ON DELETE SET NULL,
    source          TEXT NOT NULL DEFAULT 'maps_scraper',      -- maps_scraper | manual | referral
    stage           TEXT NOT NULL DEFAULT 'raw',               -- raw | cleaned | enriched | qualified | negotiation | converted | lost
    score           NUMERIC(5, 2),
    dedupe_key      TEXT NOT NULL,
    raw_data        JSONB NOT NULL DEFAULT '{}',
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_leads_dedupe_key UNIQUE (dedupe_key)
);
CREATE INDEX idx_leads_stage                 ON leads (stage);
CREATE INDEX idx_leads_score                 ON leads (score DESC);
CREATE INDEX idx_leads_account_id            ON leads (account_id);
CREATE INDEX idx_leads_contact_id            ON leads (contact_id);
CREATE INDEX idx_leads_raw_data              ON leads USING GIN (raw_data);
CREATE INDEX idx_leads_metadata              ON leads USING GIN (metadata);

CREATE TABLE lead_enrichment (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    enrichment_type TEXT NOT NULL,                            -- linkedin | clearbit | manual
    provider        TEXT,
    payload         JSONB NOT NULL DEFAULT '{}',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_lead_enrichment_lead_id     ON lead_enrichment (lead_id);
CREATE INDEX idx_lead_enrichment_type        ON lead_enrichment (enrichment_type);
CREATE INDEX idx_lead_enrichment_payload     ON lead_enrichment USING GIN (payload);

-- =============================================================
-- SECTION 3 — CONVERSATIONS, MESSAGES & OUTREACH
-- =============================================================

CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    channel         TEXT NOT NULL DEFAULT 'email',            -- email | phone | chat | linkedin
    status          TEXT NOT NULL DEFAULT 'open',             -- open | closed | paused
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_conversations_lead_id       ON conversations (lead_id);
CREATE INDEX idx_conversations_status        ON conversations (status);
CREATE INDEX idx_conversations_channel       ON conversations (channel);

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,                            -- user | assistant | system
    content         TEXT NOT NULL,
    model_used      TEXT,
    tokens_in       INT,
    tokens_out      INT,
    latency_ms      INT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_messages_conversation_id    ON messages (conversation_id);
CREATE INDEX idx_messages_role               ON messages (role);
CREATE INDEX idx_messages_created_at         ON messages (created_at DESC);

CREATE TABLE outreach_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    event_type      TEXT NOT NULL,                            -- sent | opened | clicked | replied | bounced
    channel         TEXT NOT NULL,
    subject         TEXT,
    body_snippet    TEXT,
    external_id     TEXT,                                     -- Gmail message-id or thread-id
    metadata        JSONB NOT NULL DEFAULT '{}',
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_outreach_events_lead_id     ON outreach_events (lead_id);
CREATE INDEX idx_outreach_events_event_type  ON outreach_events (event_type);
CREATE INDEX idx_outreach_events_occurred_at ON outreach_events (occurred_at DESC);

CREATE TABLE stage_transitions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    from_stage      TEXT NOT NULL,
    to_stage        TEXT NOT NULL,
    agent_name      TEXT NOT NULL,                            -- cleaner | enricher | qualifier | negotiator | supervisor
    reason          TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    transitioned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_stage_transitions_lead_id   ON stage_transitions (lead_id);
CREATE INDEX idx_stage_transitions_to_stage  ON stage_transitions (to_stage);
CREATE INDEX idx_stage_transitions_agent     ON stage_transitions (agent_name);

-- =============================================================
-- SECTION 4 — QUOTATIONS, APPROVALS & CONVERSIONS
-- =============================================================

CREATE TABLE quotations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    version         INT NOT NULL DEFAULT 1,
    total_amount    NUMERIC(14, 2) NOT NULL,
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    line_items      JSONB NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'draft',            -- draft | sent | accepted | rejected | expired
    valid_until     DATE,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_quotations_lead_id          ON quotations (lead_id);
CREATE INDEX idx_quotations_status           ON quotations (status);
CREATE INDEX idx_quotations_line_items       ON quotations USING GIN (line_items);

CREATE TABLE approvals (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    quotation_id    UUID NOT NULL REFERENCES quotations(id) ON DELETE CASCADE,
    requested_by    TEXT NOT NULL,                            -- agent name or user email
    approved_by     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',          -- pending | approved | rejected
    notes           TEXT,
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);
CREATE INDEX idx_approvals_quotation_id      ON approvals (quotation_id);
CREATE INDEX idx_approvals_status            ON approvals (status);

CREATE TABLE conversion_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    quotation_id    UUID REFERENCES quotations(id) ON DELETE SET NULL,
    conversion_type TEXT NOT NULL DEFAULT 'closed_won',       -- closed_won | closed_lost | upsell
    value           NUMERIC(14, 2),
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    metadata        JSONB NOT NULL DEFAULT '{}',
    converted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_conversion_events_lead_id   ON conversion_events (lead_id);
CREATE INDEX idx_conversion_events_type      ON conversion_events (conversion_type);
CREATE INDEX idx_conversion_events_date      ON conversion_events (converted_at DESC);

-- =============================================================
-- SECTION 5 — RATE LIMITING & SEMANTIC MEMORY
-- =============================================================

CREATE TABLE rate_limit_log (
    id              BIGSERIAL PRIMARY KEY,
    service         TEXT NOT NULL,                            -- nvidia | groq | google | gmail | maps_scraper
    endpoint        TEXT NOT NULL,
    tokens_used     INT,
    requests_used   INT DEFAULT 1,
    window_start    TIMESTAMPTZ NOT NULL DEFAULT date_trunc('minute', NOW()),
    metadata        JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_rate_limit_log_service      ON rate_limit_log (service);
CREATE INDEX idx_rate_limit_log_window       ON rate_limit_log (window_start DESC);

CREATE TABLE semantic_memory (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type     TEXT NOT NULL,                            -- lead | account | contact | conversation
    entity_id       UUID NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector(1536),
    model_used      TEXT NOT NULL DEFAULT 'text-embedding-3-small',
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_semantic_memory_entity      ON semantic_memory (entity_type, entity_id);
CREATE INDEX idx_semantic_memory_embedding   ON semantic_memory USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_semantic_memory_metadata    ON semantic_memory USING GIN (metadata);

-- =============================================================
-- SECTION 6 — UTILITY TRIGGERS
-- =============================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_accounts_updated_at
    BEFORE UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_contacts_updated_at
    BEFORE UPDATE ON contacts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_quotations_updated_at
    BEFORE UPDATE ON quotations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_service_catalogue_updated_at
    BEFORE UPDATE ON service_catalogue
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
