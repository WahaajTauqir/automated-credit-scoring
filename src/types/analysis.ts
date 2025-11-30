export type FeatureType = 'discrete' | 'continuous';

export interface NormalizedBin {
  Bin: string;
  bin_label?: string;
  Range?: string;
  range_text?: string;
  Min?: number | null;
  Max?: number | null;
  Good: number;
  Bad: number;
  Total: number;
  'Bad Rate'?: number | null;
  'Freq%'?: number | null;
  'Dist_Good_%'?: number | null;
  'Dist_Bad_%'?: number | null;
  WOE?: number | null;
  IV?: number | null;
  bad_rate?: number | null;
  freq_percent?: number | null;
  dist_good?: number | null;
  dist_bad?: number | null;
  woe?: number | null;
  iv?: number | null;
  good_count?: number;
  bad_count?: number;
  total_count?: number;
  raw?: Record<string, any>;
}

export interface NormalizedBinningState {
  univariate: Record<string, { type?: FeatureType; stats: NormalizedBin[] }>;
  coarse: Record<string, NormalizedBin[]>;
  fine: Record<string, NormalizedBin[]>;
  woe: Record<string, { iv?: number | null; stats: NormalizedBin[] }>;
  merged: Record<string, any[]>;
}

export interface AnalysisRecord {
  id: number;
  dataset_path: string;
  discrete_columns: string[];
  continuous_columns: string[];
  selected_columns: string[];
  target_variable: string;
  created_at: string;
  total_features?: number;
  discrete_features?: number;
  continuous_features?: number;
  binning_data?: Record<string, any>;
}
