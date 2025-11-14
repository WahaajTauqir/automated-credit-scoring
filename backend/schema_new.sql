-- =====================================================
-- NEW DATABASE SCHEMA FOR CREDIT SCORING APPLICATION
-- =====================================================

-- Drop existing tables if they exist (in correct dependency order)
DROP TABLE IF EXISTS binning_totals CASCADE;
DROP TABLE IF EXISTS merged_bins CASCADE;
DROP TABLE IF EXISTS bins CASCADE;
DROP TABLE IF EXISTS binning_steps CASCADE;
DROP TABLE IF EXISTS features CASCADE;
DROP TABLE IF EXISTS datasets CASCADE;

-- =====================================================
-- 1. DATASETS TABLE
-- Stores dataset/run information
-- =====================================================
CREATE TABLE datasets (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    file_path TEXT,
    total_features INT,
    discrete_features INT,
    continuous_features INT,
    target_variable TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE datasets IS 'Stores information about each credit scoring dataset/run';
COMMENT ON COLUMN datasets.name IS 'Human-readable name for the dataset';
COMMENT ON COLUMN datasets.file_path IS 'Path to the CSV file';
COMMENT ON COLUMN datasets.total_features IS 'Total number of features in dataset';
COMMENT ON COLUMN datasets.discrete_features IS 'Number of discrete/categorical features';
COMMENT ON COLUMN datasets.continuous_features IS 'Number of continuous/numeric features';
COMMENT ON COLUMN datasets.target_variable IS 'Name of the target/dependent variable';

-- =====================================================
-- 2. FEATURES TABLE
-- Each dataset has many features
-- =====================================================
CREATE TABLE features (
    id SERIAL PRIMARY KEY,
    dataset_id INT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('discrete', 'continuous')),
    selected BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(dataset_id, name)
);

COMMENT ON TABLE features IS 'Stores individual features/columns for each dataset';
COMMENT ON COLUMN features.dataset_id IS 'Foreign key to datasets table';
COMMENT ON COLUMN features.name IS 'Name of the feature/column';
COMMENT ON COLUMN features.type IS 'Type of feature: discrete or continuous';
COMMENT ON COLUMN features.selected IS 'Whether this feature is selected for analysis';

-- Index for faster feature lookups
CREATE INDEX idx_features_dataset_id ON features(dataset_id);
CREATE INDEX idx_features_name ON features(name);

-- =====================================================
-- 3. BINNING_STEPS TABLE
-- Tracks coarse and fine binning operations
-- =====================================================
CREATE TABLE binning_steps (
    id SERIAL PRIMARY KEY,
    feature_id INT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    step_type VARCHAR(20) NOT NULL CHECK (step_type IN ('coarse', 'fine')),
    method VARCHAR(50),
    num_bins INT,
    is_monotonic BOOLEAN DEFAULT FALSE,
    monotonic_direction VARCHAR(20),
    iv_value NUMERIC(10, 6),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(feature_id, step_type)
);

COMMENT ON TABLE binning_steps IS 'Stores binning operations (coarse and fine) for each feature';
COMMENT ON COLUMN binning_steps.feature_id IS 'Foreign key to features table';
COMMENT ON COLUMN binning_steps.step_type IS 'Type of binning: coarse or fine';
COMMENT ON COLUMN binning_steps.method IS 'Binning method used (e.g., qcut, merged, auto_monotonic)';
COMMENT ON COLUMN binning_steps.num_bins IS 'Number of bins created';
COMMENT ON COLUMN binning_steps.is_monotonic IS 'Whether WOE is monotonic';
COMMENT ON COLUMN binning_steps.monotonic_direction IS 'Direction of monotonicity: increasing, decreasing, or none';
COMMENT ON COLUMN binning_steps.iv_value IS 'Information Value for this binning';

-- Index for faster binning lookups
CREATE INDEX idx_binning_steps_feature_id ON binning_steps(feature_id);
CREATE INDEX idx_binning_steps_step_type ON binning_steps(step_type);

-- =====================================================
-- 4. BINS TABLE
-- Stores detailed bin results (Good, Bad, WOE, IV, etc.)
-- =====================================================
CREATE TABLE bins (
    id SERIAL PRIMARY KEY,
    binning_step_id INT NOT NULL REFERENCES binning_steps(id) ON DELETE CASCADE,
    bin_number INT NOT NULL,
    bin_label TEXT,
    min_value NUMERIC,
    max_value NUMERIC,
    range_text TEXT,
    good_count INT NOT NULL DEFAULT 0,
    bad_count INT NOT NULL DEFAULT 0,
    total_count INT NOT NULL DEFAULT 0,
    good_bad_ratio NUMERIC(10, 4),
    bad_rate NUMERIC(10, 4),
    freq_percent NUMERIC(10, 4),
    odds NUMERIC(10, 4),
    index_value NUMERIC(10, 4),
    odds_index NUMERIC(10, 4),
    dist_good NUMERIC(10, 4),
    dist_bad NUMERIC(10, 4),
    woe NUMERIC(10, 4),
    iv NUMERIC(10, 6),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(binning_step_id, bin_number)
);

COMMENT ON TABLE bins IS 'Stores detailed statistics for each bin';
COMMENT ON COLUMN bins.binning_step_id IS 'Foreign key to binning_steps table';
COMMENT ON COLUMN bins.bin_number IS 'Sequential bin number (1, 2, 3, ...)';
COMMENT ON COLUMN bins.bin_label IS 'Human-readable bin label (e.g., Bin_1, Bin_1_2)';
COMMENT ON COLUMN bins.min_value IS 'Minimum value in bin (for continuous features)';
COMMENT ON COLUMN bins.max_value IS 'Maximum value in bin (for continuous features)';
COMMENT ON COLUMN bins.range_text IS 'Text representation of range (for discrete features)';
COMMENT ON COLUMN bins.good_count IS 'Count of Good cases (target=0)';
COMMENT ON COLUMN bins.bad_count IS 'Count of Bad cases (target=1)';
COMMENT ON COLUMN bins.total_count IS 'Total count (Good + Bad)';
COMMENT ON COLUMN bins.good_bad_ratio IS 'Ratio of Good to Bad';
COMMENT ON COLUMN bins.bad_rate IS 'Percentage of Bad cases';
COMMENT ON COLUMN bins.freq_percent IS 'Percentage of total population in this bin';
COMMENT ON COLUMN bins.dist_good IS 'Distribution of Good (percentage)';
COMMENT ON COLUMN bins.dist_bad IS 'Distribution of Bad (percentage)';
COMMENT ON COLUMN bins.woe IS 'Weight of Evidence';
COMMENT ON COLUMN bins.iv IS 'Information Value contribution';

-- Index for faster bin lookups
CREATE INDEX idx_bins_binning_step_id ON bins(binning_step_id);
CREATE INDEX idx_bins_bin_number ON bins(bin_number);

-- =====================================================
-- 5. MERGED_BINS TABLE
-- Tracks which coarse bins were merged in fine binning
-- =====================================================
CREATE TABLE merged_bins (
    id SERIAL PRIMARY KEY,
    fine_step_id INT NOT NULL REFERENCES binning_steps(id) ON DELETE CASCADE,
    merged_bin_number INT NOT NULL,
    original_bin_ids INT[] NOT NULL,
    original_bin_labels TEXT[] NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE merged_bins IS 'Tracks which coarse bins were merged during fine binning';
COMMENT ON COLUMN merged_bins.fine_step_id IS 'Foreign key to binning_steps (must be step_type=fine)';
COMMENT ON COLUMN merged_bins.merged_bin_number IS 'The resulting bin number after merge';
COMMENT ON COLUMN merged_bins.original_bin_ids IS 'Array of original bin IDs that were merged';
COMMENT ON COLUMN merged_bins.original_bin_labels IS 'Array of original bin labels that were merged';

-- Index for faster merged bin lookups
CREATE INDEX idx_merged_bins_fine_step_id ON merged_bins(fine_step_id);

-- =====================================================
-- 6. BINNING_TOTALS TABLE
-- Stores overall totals for each feature for each binning step
-- =====================================================
CREATE TABLE binning_totals (
    id SERIAL PRIMARY KEY,
    binning_step_id INT NOT NULL REFERENCES binning_steps(id) ON DELETE CASCADE,
    total_good INT NOT NULL DEFAULT 0,
    total_bad INT NOT NULL DEFAULT 0,
    total_count INT NOT NULL DEFAULT 0,
    good_bad_ratio NUMERIC(10, 4),
    bad_rate NUMERIC(10, 4),
    freq_percent NUMERIC(10, 4) DEFAULT 100.0,
    iv NUMERIC(10, 6),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(binning_step_id)
);

COMMENT ON TABLE binning_totals IS 'Stores aggregated totals for each feature at each binning stage (coarse/fine)';
COMMENT ON COLUMN binning_totals.binning_step_id IS 'Foreign key to binning_steps table';
COMMENT ON COLUMN binning_totals.total_good IS 'Total count of Good cases (target=0) across all bins';
COMMENT ON COLUMN binning_totals.total_bad IS 'Total count of Bad cases (target=1) across all bins';
COMMENT ON COLUMN binning_totals.total_count IS 'Total count (Good + Bad) across all bins';
COMMENT ON COLUMN binning_totals.good_bad_ratio IS 'Overall ratio of Good to Bad';
COMMENT ON COLUMN binning_totals.bad_rate IS 'Overall percentage of Bad cases';
COMMENT ON COLUMN binning_totals.freq_percent IS 'Frequency percentage (typically 100%)';
COMMENT ON COLUMN binning_totals.iv IS 'Total Information Value for this binning step';

-- Index for faster totals lookups
CREATE INDEX idx_binning_totals_step_id ON binning_totals(binning_step_id);

-- =====================================================
-- HELPER FUNCTIONS
-- =====================================================

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at for datasets
CREATE TRIGGER update_datasets_updated_at
    BEFORE UPDATE ON datasets
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- SAMPLE DATA (for testing)
-- =====================================================

-- Uncomment to insert sample data:
-- INSERT INTO datasets (name, total_features, discrete_features, continuous_features, target_variable)
-- VALUES ('Loan_Data_Run1', 30, 10, 20, 'default');

-- INSERT INTO features (dataset_id, name, type, selected)
-- VALUES (1, 'age', 'continuous', true);

-- INSERT INTO binning_steps (feature_id, step_type, method, num_bins)
-- VALUES (1, 'coarse', 'qcut', 5);

-- =====================================================
-- VIEWS FOR EASIER QUERYING
-- =====================================================

-- View to see all features with their dataset info
CREATE OR REPLACE VIEW v_features_with_dataset AS
SELECT 
    f.id AS feature_id,
    f.name AS feature_name,
    f.type AS feature_type,
    f.selected,
    d.id AS dataset_id,
    d.name AS dataset_name,
    d.target_variable,
    d.created_at AS dataset_created_at
FROM features f
JOIN datasets d ON f.dataset_id = d.id;

-- View to see all binning results with feature and dataset info
CREATE OR REPLACE VIEW v_binning_results AS
SELECT 
    b.id AS bin_id,
    b.bin_number,
    b.bin_label,
    b.min_value,
    b.max_value,
    b.range_text,
    b.good_count,
    b.bad_count,
    b.total_count,
    b.woe,
    b.iv,
    bs.step_type,
    bs.method,
    bs.iv_value AS step_iv_value,
    f.name AS feature_name,
    f.type AS feature_type,
    d.name AS dataset_name
FROM bins b
JOIN binning_steps bs ON b.binning_step_id = bs.id
JOIN features f ON bs.feature_id = f.id
JOIN datasets d ON f.dataset_id = d.id
ORDER BY d.id, f.id, bs.step_type, b.bin_number;

COMMENT ON VIEW v_binning_results IS 'Comprehensive view of all binning results with context';
