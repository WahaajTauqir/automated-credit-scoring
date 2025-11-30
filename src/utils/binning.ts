import { FeatureType, NormalizedBin, NormalizedBinningState } from '../types/analysis';

const firstDefined = <T>(...values: (T | undefined | null)[]): T | undefined => {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== '') {
      return value as T;
    }
  }
  return undefined;
};

const toNumber = (value: any, fallback: number | null = null): number | null => {
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const normalized = String(value).trim().replace(/,/g, '');
  if (normalized === '' || normalized.toLowerCase() === 'nan') return fallback;
  if (normalized.toLowerCase() === 'inf' || normalized.toLowerCase() === 'infinity') {
    return Number.POSITIVE_INFINITY;
  }
  if (normalized.endsWith('%')) {
    const parsed = Number(normalized.slice(0, -1));
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const ensureNumber = (value: any, fallback = 0): number => {
  const parsed = toNumber(value, fallback);
  if (parsed === null || !Number.isFinite(parsed)) return fallback;
  return Number(parsed);
};

export const normalizeBinArray = (bins?: any[]): NormalizedBin[] => {
  if (!Array.isArray(bins)) return [];

  return bins.map((raw, index) => {
    const binLabel =
      firstDefined(
        raw?.Bin,
        raw?.bin_label,
        raw?.bin_name,
        raw?.bin,
        `Bin_${index + 1}`
      ) ?? `Bin_${index + 1}`;

    const rangeValue = firstDefined(raw?.Range, raw?.range_text, raw?.bin_range);
    const minValue = firstDefined(raw?.Min, raw?.min_value);
    const maxValue = firstDefined(raw?.Max, raw?.max_value);

    const good = ensureNumber(
      firstDefined(raw?.Good, raw?.good_count, raw?.good),
      0
    );
    const bad = ensureNumber(
      firstDefined(raw?.Bad, raw?.bad_count, raw?.bad),
      0
    );
    const total = ensureNumber(
      firstDefined(raw?.Total, raw?.total_count, raw?.total),
      good + bad
    );

    let badRate =
      toNumber(
        firstDefined(
          raw?.['Bad Rate'],
          raw?.['Bad Rate (%)'],
          raw?.bad_rate,
          raw?.BadRate
        )
      ) ?? (total > 0 ? (bad / total) * 100 : null);

    let freqPercent =
      toNumber(firstDefined(raw?.['Freq%'], raw?.freq_percent, raw?.freq)) ??
      null;

    const distGood =
      toNumber(firstDefined(raw?.['Dist_Good_%'], raw?.dist_good)) ?? null;
    const distBad =
      toNumber(firstDefined(raw?.['Dist_Bad_%'], raw?.dist_bad)) ?? null;
    const woeValue =
      toNumber(firstDefined(raw?.WOE, raw?.woe)) ?? null;
    const ivValue =
      toNumber(firstDefined(raw?.IV, raw?.iv)) ?? null;

    if (badRate !== null && !Number.isFinite(badRate)) badRate = null;
    if (freqPercent !== null && !Number.isFinite(freqPercent)) freqPercent = null;

    const normalized: NormalizedBin = {
      ...raw,
      Bin: binLabel,
      bin_label: binLabel,
      Range: rangeValue,
      range_text: rangeValue,
      Min: minValue ?? null,
      Max: maxValue ?? null,
      Good: good,
      good_count: good,
      Bad: bad,
      bad_count: bad,
      Total: total,
      total_count: total,
      'Bad Rate': badRate,
      bad_rate: badRate,
      'Freq%': freqPercent,
      freq_percent: freqPercent,
      'Dist_Good_%': distGood,
      dist_good: distGood,
      'Dist_Bad_%': distBad,
      dist_bad: distBad,
      WOE: woeValue,
      woe: woeValue,
      IV: ivValue,
      iv: ivValue,
      raw,
    };

    return normalized;
  });
};

export const buildBinningState = (
  binningData?: Record<string, any>,
  typeLookup?: Record<string, FeatureType | undefined>
): NormalizedBinningState => {
  const state: NormalizedBinningState = {
    univariate: {},
    coarse: {},
    fine: {},
    woe: {},
    merged: {},
  };

  if (!binningData) return state;

  Object.entries(binningData).forEach(([column, binning]: [string, any]) => {
    const inferredType: FeatureType | undefined =
      binning?.coarse?.type ||
      binning?.fine?.type ||
      typeLookup?.[column];

    if (binning?.coarse?.bins?.length) {
      const bins = normalizeBinArray(binning.coarse.bins);
      state.coarse[column] = bins;
      state.univariate[column] = {
        type: inferredType,
        stats: bins,
      };
    }

    if (binning?.fine?.bins?.length) {
      const bins = normalizeBinArray(binning.fine.bins);
      state.fine[column] = bins;
      if (!state.univariate[column]) {
        state.univariate[column] = { type: inferredType, stats: bins };
      }
    }

    if (binning?.fine?.merged_bins) {
      state.merged[column] = binning.fine.merged_bins;
    }

    if (binning?.woe_iv?.bins?.length) {
      state.woe[column] = {
        iv:
          typeof binning.woe_iv.iv === 'number'
            ? binning.woe_iv.iv
            : toNumber(binning.woe_iv.iv),
        stats: normalizeBinArray(binning.woe_iv.bins),
      };
    }
  });

  return state;
};

export const buildTypeLookup = (
  discrete: string[] = [],
  continuous: string[] = []
): Record<string, FeatureType> => {
  const lookup: Record<string, FeatureType> = {};
  discrete.forEach((col) => (lookup[col] = 'discrete'));
  continuous.forEach((col) => (lookup[col] = 'continuous'));
  return lookup;
};

export const prepareBinMetricsPayload = (bins: NormalizedBin[]) =>
  bins.map((bin) => ({
    bin_name: bin.Bin,
    bin_range: bin.Range,
    good_count: bin.Good,
    bad_count: bin.Bad,
    total_count: bin.Total,
  }));
