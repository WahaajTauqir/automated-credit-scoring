/**
 * Configuration constants for the Credit Scoring Application
 * 
 * This file contains all configuration constants that should be changed in one place.
 */

// API Configuration
// ===============================
// Use environment variable in production, fallback to localhost for development
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 
  (import.meta.env.PROD 
    ? 'https://credit-scoring-backend-XXXXX-uc.a.run.app'  // Replace with your Cloud Run URL
    : 'http://localhost:5000');

// Train/Test Split Configuration
// ===============================
// Default test size for train/test split (0.2 = 20% test, 80% train)
export const DEFAULT_TEST_SIZE = 0.2;

