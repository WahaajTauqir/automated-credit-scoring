-- =====================================================
-- MIGRATION: Add Train/Test Split Columns
-- =====================================================
-- This migration adds columns to track train/test split metadata
-- 
-- Run this migration:
-- psql -U myuser -d mydb -f 001_add_train_test_split_columns.sql
-- 
-- Or if using environment variables:
-- psql $DATABASE_URL -f 001_add_train_test_split_columns.sql
-- =====================================================

-- Add train/test split columns to records table
ALTER TABLE records ADD COLUMN IF NOT EXISTS train_test_split_seed INTEGER;
ALTER TABLE records ADD COLUMN IF NOT EXISTS train_test_split_size NUMERIC(5, 3);
ALTER TABLE records ADD COLUMN IF NOT EXISTS train_test_split_method VARCHAR(50);
ALTER TABLE records ADD COLUMN IF NOT EXISTS train_size INTEGER;
ALTER TABLE records ADD COLUMN IF NOT EXISTS test_size INTEGER;
ALTER TABLE records ADD COLUMN IF NOT EXISTS train_bad_count INTEGER;
ALTER TABLE records ADD COLUMN IF NOT EXISTS test_bad_count INTEGER;
ALTER TABLE records ADD COLUMN IF NOT EXISTS split_created_at TIMESTAMP;
ALTER TABLE records ADD COLUMN IF NOT EXISTS data_hash VARCHAR(64);

-- Add comments for documentation
COMMENT ON COLUMN records.train_test_split_seed IS 'Random seed used for train/test split (for reproducibility)';
COMMENT ON COLUMN records.train_test_split_size IS 'Proportion of data allocated to test set (e.g., 0.200 for 20%)';
COMMENT ON COLUMN records.train_test_split_method IS 'Method used for split (stratified, random, time_based)';
COMMENT ON COLUMN records.train_size IS 'Number of rows in training set';
COMMENT ON COLUMN records.test_size IS 'Number of rows in test set';
COMMENT ON COLUMN records.train_bad_count IS 'Number of bad cases (target=1) in training set';
COMMENT ON COLUMN records.test_bad_count IS 'Number of bad cases (target=1) in test set';
COMMENT ON COLUMN records.split_created_at IS 'Timestamp when train/test split was created';
COMMENT ON COLUMN records.data_hash IS 'Hash of data to detect changes requiring new split';

-- Verify columns were added
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'records'
AND (column_name LIKE 'train%' OR column_name = 'test_size' OR column_name = 'data_hash' OR column_name = 'split_created_at')
ORDER BY ordinal_position;

