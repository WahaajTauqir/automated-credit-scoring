-- Table to store analysis records
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_path TEXT NOT NULL,
    discrete_columns TEXT NOT NULL,
    continuous_columns TEXT NOT NULL,
    selected_columns TEXT NOT NULL,
    target_variable TEXT NOT NULL,
    univariate_results TEXT NOT NULL,
    finebin_results TEXT NOT NULL,
    crosstab_results TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
