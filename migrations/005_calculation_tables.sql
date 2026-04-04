-- sector_benchmarks: financial benchmark data per sector per year
CREATE TABLE IF NOT EXISTS sector_benchmarks (
    id SERIAL PRIMARY KEY,
    sector_id VARCHAR(50) NOT NULL,  -- healthcare, overheid, bouw, energie, onderwijs, transport
    sector_name VARCHAR(100) NOT NULL,
    subsector VARCHAR(100),  -- e.g. 'rail', 'luchtvaart', 'po', 'vo', 'mbo'
    year INTEGER NOT NULL,
    quarter INTEGER,  -- 1-4, nullable for annual data

    -- Sector profile
    total_workforce_fte INTEGER,
    avg_labour_cost_fte NUMERIC(10,2),  -- EUR
    labour_cost_ratio NUMERIC(5,2),  -- percentage
    avg_revenue_per_fte NUMERIC(12,2),  -- EUR
    sector_total_revenue_eur NUMERIC(15,2),  -- EUR (sector total)

    -- Vacancy metrics
    vacancy_rate NUMERIC(5,2),
    open_vacancies INTEGER,
    time_to_fill_days NUMERIC(6,1),
    cost_per_hire NUMERIC(10,2),  -- EUR
    cost_per_vacancy_month NUMERIC(10,2),  -- EUR indirect costs

    -- Turnover metrics
    turnover_rate NUMERIC(5,2),
    turnover_cost_per_exit NUMERIC(10,2),  -- EUR
    turnover_cost_pct_salary NUMERIC(5,2),  -- % of annual salary

    -- Absenteeism metrics
    absenteeism_rate NUMERIC(5,2),
    cost_per_sick_day NUMERIC(8,2),  -- EUR
    burnout_prevalence NUMERIC(5,2),  -- percentage
    burnout_cost_per_case NUMERIC(10,2),  -- EUR
    long_term_absence_pct NUMERIC(5,2),  -- % of total absence >6 weeks

    -- Productivity
    productivity_index NUMERIC(8,2),  -- sector-specific
    overhead_ratio NUMERIC(5,2),
    span_of_control NUMERIC(4,1),

    -- Technology
    ai_adoption_rate NUMERIC(5,2),
    robotics_adoption_rate NUMERIC(5,2),
    automation_roi_typical NUMERIC(5,2),  -- percentage
    automation_payback_months NUMERIC(5,1),
    digital_invest_per_fte NUMERIC(10,2),  -- EUR

    -- Training & development
    training_investment_per_fte NUMERIC(10,2),  -- EUR
    internal_mobility_rate NUMERIC(5,2),
    flex_ratio NUMERIC(5,2),  -- % non-permanent contracts

    -- Metadata
    source VARCHAR(500),
    confidence_level VARCHAR(20) DEFAULT 'medium',  -- high, medium, low
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(sector_id, subsector, year, quarter)
);

-- calculation_defaults: default parameter values for calculations
CREATE TABLE IF NOT EXISTS calculation_defaults (
    id SERIAL PRIMARY KEY,
    calculation_type VARCHAR(50) NOT NULL,  -- vacancy_cost, turnover_cost, etc.
    parameter_name VARCHAR(100) NOT NULL,
    sector_id VARCHAR(50),  -- NULL = cross-sector default
    default_value NUMERIC(15,4) NOT NULL,
    unit VARCHAR(30),  -- EUR, percentage, days, months, ratio
    min_value NUMERIC(15,4),
    max_value NUMERIC(15,4),
    description TEXT,
    source VARCHAR(500),
    year INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(calculation_type, parameter_name, sector_id)
);

-- calculation_results: audit trail of all calculations
CREATE TABLE IF NOT EXISTS calculation_results (
    id SERIAL PRIMARY KEY,
    calculation_type VARCHAR(50) NOT NULL,
    sector_id VARCHAR(50),
    input_parameters JSONB NOT NULL,
    output_results JSONB NOT NULL,
    methodology TEXT,
    confidence_level VARCHAR(20),
    user_session_id VARCHAR(100),
    source_context VARCHAR(200),  -- 'workshop', 'quick_scan', 'deep_dive', 'consultant'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_benchmarks_sector_year ON sector_benchmarks(sector_id, year);
CREATE INDEX idx_defaults_calc_sector ON calculation_defaults(calculation_type, sector_id);
CREATE INDEX idx_results_type ON calculation_results(calculation_type, created_at);
CREATE INDEX idx_results_session ON calculation_results(user_session_id);
