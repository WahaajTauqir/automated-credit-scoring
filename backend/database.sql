-- Table to store analysis records
CREATE TABLE IF NOT EXISTS records (
    id SERIAL PRIMARY KEY,
    dataset_path TEXT NOT NULL,
    discrete_columns TEXT NOT NULL,
    continuous_columns TEXT NOT NULL,
    selected_columns TEXT NOT NULL,
    dashboard_selected_columns TEXT,
    target_variable TEXT NOT NULL,
    univariate_results TEXT NOT NULL,
    finebin_results TEXT NOT NULL,
    crosstab_results TEXT NOT NULL,
    woe_iv_results TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table to store fine binning details
CREATE TABLE IF NOT EXISTS finebin_details (
    id SERIAL PRIMARY KEY,
    record_id INTEGER NOT NULL,
    column_name TEXT NOT NULL,
    group_id TEXT NOT NULL,
    merged_bins TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records (id)
);
