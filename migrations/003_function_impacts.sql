-- ============================================
-- The Architect — Function Impact Schema
-- ============================================
-- Migration 003: Structured function-impact data for AIAIAI Wat Nu
-- Enables direct querying of AI/robotisation impact per function per period
-- Source: research_data_part1.json + research_data_part2.json (53 functies × 5 perioden)

-- ============================================
-- 1. Functions (base table)
-- ============================================
CREATE TABLE IF NOT EXISTS function_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sector TEXT NOT NULL,
    functiegroep TEXT NOT NULL,
    functie TEXT NOT NULL,
    -- 9-dimension impact scores (AIAIAI Wat Nu framework)
    dim_fte_impact TEXT CHECK (dim_fte_impact IN ('Laag', 'Midden', 'Hoog')),
    dim_functie_invulling TEXT CHECK (dim_functie_invulling IN ('Laag', 'Midden', 'Hoog')),
    dim_werving_arbeidsmarkt TEXT CHECK (dim_werving_arbeidsmarkt IN ('Laag', 'Midden', 'Hoog')),
    dim_competenties_scholing TEXT CHECK (dim_competenties_scholing IN ('Laag', 'Midden', 'Hoog')),
    dim_kennisbehoud TEXT CHECK (dim_kennisbehoud IN ('Laag', 'Midden', 'Hoog')),
    dim_werkbeleving_autonomie TEXT CHECK (dim_werkbeleving_autonomie IN ('Laag', 'Midden', 'Hoog')),
    dim_productiviteit_kwaliteit TEXT CHECK (dim_productiviteit_kwaliteit IN ('Laag', 'Midden', 'Hoog')),
    dim_fysieke_belasting TEXT CHECK (dim_fysieke_belasting IN ('Laag', 'Midden', 'Hoog')),
    dim_samenwerking_locatie TEXT CHECK (dim_samenwerking_locatie IN ('Laag', 'Midden', 'Hoog')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_func_profile_unique ON function_profiles(sector, functiegroep, functie);
CREATE INDEX IF NOT EXISTS idx_func_profile_sector ON function_profiles(sector);

-- ============================================
-- 2. Impact Percentages (per period)
-- ============================================
CREATE TABLE IF NOT EXISTS function_impacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    function_id UUID NOT NULL REFERENCES function_profiles(id) ON DELETE CASCADE,
    period TEXT NOT NULL,  -- '2025-2027', '2028-2030', etc.
    robotisering_ondersteuning DECIMAL DEFAULT 0,
    robotisering_augmentatie DECIMAL DEFAULT 0,
    robotisering_vervanging DECIMAL DEFAULT 0,
    ai_ondersteuning DECIMAL DEFAULT 0,
    ai_augmentatie DECIMAL DEFAULT 0,
    ai_vervanging DECIMAL DEFAULT 0,
    kennisoverdracht TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_func_impact_unique ON function_impacts(function_id, period);
CREATE INDEX IF NOT EXISTS idx_func_impact_period ON function_impacts(period);

-- ============================================
-- 3. Task Changes (per period)
-- ============================================
CREATE TABLE IF NOT EXISTS function_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    function_id UUID NOT NULL REFERENCES function_profiles(id) ON DELETE CASCADE,
    period TEXT NOT NULL,
    taak TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('ondersteuning', 'augmentatie', 'vervanging')),
    technologie TEXT NOT NULL CHECK (technologie IN ('AI', 'Robot', 'Beide')),
    beschrijving TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_func_tasks_function ON function_tasks(function_id);
CREATE INDEX IF NOT EXISTS idx_func_tasks_period ON function_tasks(function_id, period);

-- ============================================
-- 4. Competency Changes (per period)
-- ============================================
CREATE TABLE IF NOT EXISTS function_competencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    function_id UUID NOT NULL REFERENCES function_profiles(id) ON DELETE CASCADE,
    period TEXT NOT NULL,
    nieuwe_competenties TEXT[] DEFAULT '{}',
    vervallen_competenties TEXT[] DEFAULT '{}',
    nieuwe_technische_vaardigheden TEXT[] DEFAULT '{}',
    vervallen_technische_vaardigheden TEXT[] DEFAULT '{}',
    kennisoverdracht TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_func_comp_unique ON function_competencies(function_id, period);

-- Auto-update timestamps
CREATE TRIGGER tr_func_profiles_updated BEFORE UPDATE ON function_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
