-- ============================================
-- The Architect — Initial Database Schema
-- ============================================
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New Query)
-- Order: run this FIRST, then 002_functions.sql

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for text search

-- ============================================
-- 1. Knowledge Documents
-- ============================================
-- Stores all source documents: CBS data, reports, laws, frameworks, etc.
CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name TEXT NOT NULL,              -- 'CBS StatLine', 'UWV Spanningsindicator', etc.
    source_url TEXT,                         -- original URL
    source_type TEXT NOT NULL CHECK (source_type IN (
        'api_data', 'report', 'law', 'framework', 'own_research', 'sector_monitor', 'news'
    )),
    category TEXT NOT NULL CHECK (category IN (
        'arbeidsmarkt', 'sectorkennis', 'regelgeving', 'interventies',
        'internationaal', 'business_case', 'adviesframeworks'
    )),
    layer INTEGER NOT NULL CHECK (layer BETWEEN 1 AND 7),  -- knowledge layer from Blueprint
    sector TEXT[],                           -- relevant sectors (NULL = cross-sector)
    title TEXT NOT NULL,
    content TEXT NOT NULL,                   -- full text/data
    metadata JSONB DEFAULT '{}',            -- extra: date, author, version, etc.
    source_date DATE,                        -- date of the source data
    fetched_at TIMESTAMPTZ DEFAULT now(),    -- when fetched
    expires_at TIMESTAMPTZ,                 -- when to re-fetch
    is_current BOOLEAN DEFAULT true,         -- false after update (keep history)
    content_hash TEXT,                       -- SHA-256 hash for diff detection
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX idx_documents_source ON knowledge_documents(source_name);
CREATE INDEX idx_documents_category ON knowledge_documents(category);
CREATE INDEX idx_documents_layer ON knowledge_documents(layer);
CREATE INDEX idx_documents_sector ON knowledge_documents USING gin(sector);
CREATE INDEX idx_documents_current ON knowledge_documents(is_current) WHERE is_current = true;
CREATE INDEX idx_documents_expires ON knowledge_documents(expires_at) WHERE expires_at IS NOT NULL;

-- ============================================
-- 2. Knowledge Embeddings (Vector Store)
-- ============================================
-- Chunked + embedded document fragments for RAG retrieval
CREATE TABLE knowledge_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,            -- sequence within document
    chunk_text TEXT NOT NULL,                -- the text of this chunk
    embedding vector(1024) NOT NULL,         -- Voyage AI voyage-3 (1024 dimensions)
    metadata JSONB DEFAULT '{}',            -- chunk-specific metadata
    created_at TIMESTAMPTZ DEFAULT now()
);

-- HNSW index for fast approximate nearest neighbor search
-- Using cosine distance (most common for text embeddings)
CREATE INDEX idx_embeddings_vector ON knowledge_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Index for document lookups
CREATE INDEX idx_embeddings_document ON knowledge_embeddings(document_id);

-- ============================================
-- 3. Sector Intelligence (Aggregated Metrics)
-- ============================================
-- Pre-computed sector benchmarks for fast retrieval
CREATE TABLE sector_intelligence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sector_slug TEXT NOT NULL,               -- 'zorg', 'bouw', 'techniek', etc.
    metric_name TEXT NOT NULL,               -- 'verloop_gem', 'verzuim_gem', 'salaris_gem', etc.
    metric_value DECIMAL,
    metric_unit TEXT,                         -- '%', 'EUR', 'score', 'dagen'
    metric_context TEXT,                      -- explanation / nuance
    source TEXT NOT NULL,                     -- where this metric comes from
    source_date DATE NOT NULL,
    confidence DECIMAL DEFAULT 0.8 CHECK (confidence BETWEEN 0 AND 1),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_sector_metric ON sector_intelligence(sector_slug, metric_name);
CREATE INDEX idx_sector_slug ON sector_intelligence(sector_slug);

-- ============================================
-- 4. Risk Parameters
-- ============================================
-- Sector-specific risk scoring parameters
CREATE TABLE risk_parameters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sector_slug TEXT NOT NULL,
    risk_category TEXT NOT NULL CHECK (risk_category IN (
        'vergrijzing', 'arbeidsmarktafhankelijkheid', 'automatisering',
        'kennisbehoud', 'vitaliteit', 'innovatie_adoptie'
    )),
    parameter_name TEXT NOT NULL,            -- e.g. 'gemiddelde_leeftijd', 'openstaande_vacatures_ratio'
    parameter_value DECIMAL NOT NULL,
    threshold_low DECIMAL,                   -- below this = green
    threshold_high DECIMAL,                  -- above this = red
    weight DECIMAL DEFAULT 1.0,             -- relative importance within risk category
    source TEXT,
    source_date DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_risk_param ON risk_parameters(sector_slug, risk_category, parameter_name);

-- ============================================
-- 5. Business Case Parameters
-- ============================================
-- Sector-specific cost parameters for business case calculations
CREATE TABLE businesscase_parameters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sector_slug TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN (
        'arbeidstekorten', 'verloop', 'verzuim', 'automatisering', 'kennisbehoud'
    )),
    parameter_name TEXT NOT NULL,            -- e.g. 'kosten_per_vacature', 'verzuimkosten_per_dag'
    parameter_value DECIMAL NOT NULL,
    parameter_unit TEXT NOT NULL,            -- 'EUR', '%', 'dagen', 'maanden'
    description TEXT,
    source TEXT,
    source_date DATE,
    is_adjustable BOOLEAN DEFAULT false,    -- can expert mode change this?
    min_value DECIMAL,                       -- for expert mode slider
    max_value DECIMAL,                       -- for expert mode slider
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_bc_param ON businesscase_parameters(sector_slug, category, parameter_name);

-- ============================================
-- 6. Organizations (analyzed organizations)
-- ============================================
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    sector_slug TEXT NOT NULL,
    employee_count INTEGER,
    profile JSONB DEFAULT '{}',             -- full intake profile
    source TEXT,                             -- 'jaarverslag', 'kvk', 'manual'
    is_public_benchmark BOOLEAN DEFAULT false, -- used in sector benchmarks?
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_org_sector ON organizations(sector_slug);

-- ============================================
-- 7. Analyses (generated reports)
-- ============================================
CREATE TABLE analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id),
    user_id UUID,                            -- from Supabase Auth
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'processing', 'completed', 'failed'
    )),
    intake_data JSONB NOT NULL,             -- full intake answers
    results JSONB,                           -- full analysis output
    risk_matrix JSONB,                       -- 6 risks with scores
    business_case JSONB,                     -- 5 categories with EUR
    sources_used JSONB,                      -- citations
    processing_time_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_analyses_org ON analyses(organization_id);
CREATE INDEX idx_analyses_status ON analyses(status);

-- ============================================
-- 8. Knowledge Changelog (audit trail)
-- ============================================
CREATE TABLE knowledge_changelog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action TEXT NOT NULL CHECK (action IN (
        'added', 'updated', 'expired', 'refreshed', 'deleted', 'validated'
    )),
    document_id UUID REFERENCES knowledge_documents(id),
    summary TEXT,                             -- what changed
    source_job TEXT,                          -- 'weekly_update', 'manual', 'collector_cbs', etc.
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_changelog_action ON knowledge_changelog(action);
CREATE INDEX idx_changelog_created ON knowledge_changelog(created_at DESC);

-- ============================================
-- 9. Marketplace: Service Providers
-- ============================================
CREATE TABLE service_providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT,
    website TEXT,
    contact_email TEXT NOT NULL,
    logo_url TEXT,
    categories TEXT[] NOT NULL,              -- 'recruitment', 'coaching', 'consultancy', 'innovatie'
    sectors TEXT[],                           -- which sectors they serve
    subscription_status TEXT DEFAULT 'pending' CHECK (subscription_status IN (
        'pending', 'active', 'expired', 'cancelled'
    )),
    subscription_fee DECIMAL DEFAULT 500.00, -- EUR/year
    commission_rate DECIMAL DEFAULT 0.05,    -- 5% on follow-up
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_providers_categories ON service_providers USING gin(categories);
CREATE INDEX idx_providers_sectors ON service_providers USING gin(sectors);
CREATE INDEX idx_providers_status ON service_providers(subscription_status);

-- ============================================
-- 10. Marketplace: Referrals
-- ============================================
CREATE TABLE referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID REFERENCES analyses(id),
    provider_id UUID REFERENCES service_providers(id),
    risk_category TEXT,                      -- which risk triggered this referral
    action_item TEXT,                        -- which action from the report
    status TEXT DEFAULT 'shown' CHECK (status IN (
        'shown', 'clicked', 'contacted', 'converted'
    )),
    revenue DECIMAL,                         -- if converted, the project value
    commission DECIMAL,                      -- ModellenWerk commission
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_referrals_analysis ON referrals(analysis_id);
CREATE INDEX idx_referrals_provider ON referrals(provider_id);

-- ============================================
-- Auto-update timestamps
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tr_documents_updated BEFORE UPDATE ON knowledge_documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_sector_intel_updated BEFORE UPDATE ON sector_intelligence
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_risk_params_updated BEFORE UPDATE ON risk_parameters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_bc_params_updated BEFORE UPDATE ON businesscase_parameters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_orgs_updated BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_providers_updated BEFORE UPDATE ON service_providers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- Row Level Security (RLS)
-- ============================================
-- Knowledge tables: read-only for anon, full access for service role
ALTER TABLE knowledge_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE sector_intelligence ENABLE ROW LEVEL SECURITY;
ALTER TABLE analyses ENABLE ROW LEVEL SECURITY;

-- Public read for sector intelligence (benchmark pages)
CREATE POLICY "Public can read sector intelligence"
    ON sector_intelligence FOR SELECT
    USING (true);

-- Analyses: users can only see their own
CREATE POLICY "Users can read own analyses"
    ON analyses FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role full access to analyses"
    ON analyses FOR ALL
    USING (auth.role() = 'service_role');

-- Knowledge: only service role can write
CREATE POLICY "Service role full access to knowledge"
    ON knowledge_documents FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to embeddings"
    ON knowledge_embeddings FOR ALL
    USING (auth.role() = 'service_role');
