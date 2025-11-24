-- =====================================================
-- MIGRATION: Add Train/Test Split File Paths
-- =====================================================
-- This migration adds columns to store train/test split file paths
-- 
-- Run this migration:
-- psql -U myuser -d mydb -f 002_add_train_test_paths.sql
-- 
-- Or if using environment variables:
-- psql $DATABASE_URL -f 002_add_train_test_paths.sql
-- =====================================================

-- Add train/test split file path columns to records table
ALTER TABLE records ADD COLUMN IF NOT EXISTS train_path TEXT;
ALTER TABLE records ADD COLUMN IF NOT EXISTS test_path TEXT;

-- Add comments for documentation
COMMENT ON COLUMN records.train_path IS 'Path to saved preprocessed training set CSV file';
COMMENT ON COLUMN records.test_path IS 'Path to saved preprocessed test set CSV file';

