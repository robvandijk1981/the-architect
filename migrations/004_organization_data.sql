-- Migration 004: Add organization financial and AI data columns

-- Add financial and capacity columns to organizations table
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS personeelskosten_mln DECIMAL(10, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS omzet_budget_mln DECIMAL(12, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS vacatures INTEGER;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS verzuim_pct DECIMAL(5, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS gem_jaarsalaris DECIMAL(10, 0);

-- Add AI cost and benefit analysis columns
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS kritieke_functies TEXT;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS kosten_krapte_totaal_mln DECIMAL(10, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS kosten_werving_mln DECIMAL(10, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS kosten_onvervuld_mln DECIMAL(10, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS kosten_inhuur_mln DECIMAL(10, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS kosten_verzuim_mln DECIMAL(10, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS kosten_burnout_mln DECIMAL(10, 2);

-- Add AI benefit scenarios
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ai_baten_25_mln DECIMAL(10, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ai_baten_50_mln DECIMAL(10, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ai_baten_75_mln DECIMAL(10, 2);

-- Add AI impact metrics
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS fte_bespaard_50 INTEGER;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ai_ondersteuning_pct DECIMAL(5, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ai_augmentatie_pct DECIMAL(5, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ai_vervanging_pct DECIMAL(5, 2);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ai_status TEXT;

-- Create sector_profiles table with aggregated sector data
CREATE TABLE IF NOT EXISTS sector_profiles (
    sector_slug TEXT PRIMARY KEY,
    fte INTEGER NOT NULL,
    personeelskosten_mln DECIMAL(10, 2),
    omzet_budget_mln DECIMAL(12, 2),
    vacatures INTEGER,
    gem_verzuim_pct DECIMAL(5, 2),
    kosten_krapte_mln DECIMAL(10, 2),
    ai_ondersteuning_pct DECIMAL(5, 2),
    ai_augmentatie_pct DECIMAL(5, 2),
    ai_vervanging_pct DECIMAL(5, 2),
    ai_baten_25_mln DECIMAL(10, 2),
    ai_baten_50_mln DECIMAL(10, 2),
    ai_baten_75_mln DECIMAL(10, 2),
    fte_bespaard_50 INTEGER,
    kritieke_functies TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_organizations_sector_slug ON organizations(sector_slug);
CREATE INDEX IF NOT EXISTS idx_organizations_source ON organizations(source);
CREATE INDEX IF NOT EXISTS idx_organizations_is_public ON organizations(is_public_benchmark);
