import { useLocation } from 'react-router-dom';
import { useEffect, useState, useRef, useCallback, useMemo, memo } from 'react';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import LogisticRegressionResults from './LogisticRegressionResults';
import Navbar from './Navbar';
import RandomForestResults from './RandomForestResults';
import XGBoostResults from './XGBoostResults';
import StackingResults from './StackingResults';
import { DiscreteValuesDropdown } from './DiscreteValues';
import ColumnPanels from './ColumnsPanel';
import PreprocessingDetails from './PreprocessingDetails';
import { authPost, authGet } from '../utils/api';
// import WoeIvResults from './WoeIvResults';
import './SelectedColumnsPage.css';
import { buildBinningState, buildTypeLookup, normalizeBinArray, prepareBinMetricsPayload } from '../utils/binning';
import { NormalizedBin, NormalizedBinningState } from '../types/analysis';
import { DEFAULT_TEST_SIZE } from '../config';

const normalizeDisplayLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const getBinLabelValue = (bin: NormalizedBin | undefined, fallbackIndex = 0) => {
  if (!bin) return `Bin_${fallbackIndex + 1}`;
  const label = bin.Bin ?? bin.bin_label;
  return label ? String(label) : `Bin_${fallbackIndex + 1}`;
};

const getRangeText = (bin: NormalizedBin | undefined) =>
  typeof bin?.Range === 'string' ? bin.Range : '';

const getNumericOrderFromLabel = (label: string) => {
  const match = label.match(/\d+/);
  return match ? parseInt(match[0], 10) : null;
};

const getMinFromBin = (bin: NormalizedBin | undefined): number | null =>
  typeof bin?.Min === 'number' ? bin.Min : null;

const getMaxFromBin = (bin: NormalizedBin | undefined): number | null =>
  typeof bin?.Max === 'number' ? bin.Max : null;
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  LineChart,
  Line,
  Legend,
} from 'recharts';

// Memoized AutoBinningCard component to prevent unnecessary re-renders
interface AutoBinningCardProps {
  col: string;
  woeData: any;
  isLoading: boolean;
  isSelected: boolean;
  isSelectedForExport: boolean;
  onToggle: (col: string) => void;
  onToggleExport: (col: string) => void;
  onConfigureManually: (col: string) => void;
  continuousColumns: string[];
  cardRef?: React.RefObject<HTMLDivElement | null>;
}

const AutoBinningCard = memo(({ 
  col, 
  woeData, 
  isLoading, 
  isSelected,
  isSelectedForExport,
  onToggle,
  onToggleExport,
  onConfigureManually,
  continuousColumns,
  cardRef
}: AutoBinningCardProps) => {
  const woeStats: NormalizedBin[] = woeData?.stats ?? [];
  const totalIV = woeStats.reduce((sum: number, s: NormalizedBin) => sum + (Number(s.IV) || 0), 0);

  const chartData = useMemo(() => {
    return woeStats
      .map((s, idx) => {
        const label = getBinLabelValue(s, idx);
        const order = typeof s.Min === 'number'
          ? s.Min
          : getNumericOrderFromLabel(label) ?? idx;
        return {
          bin: label,
          WOE: Number(s.WOE ?? 0),
          order
        };
      })
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  }, [woeStats]); // Only recalculate when woeStats changes

  const isContinuous = (continuousColumns || []).includes(col);
  const varTypeTag = isContinuous ? 'continuous' : 'discrete';

  return (
    <div 
      className={`auto-binning-card ${isSelectedForExport ? 'selected-for-export' : ''}`} 
      ref={(el) => {
        if (cardRef && 'current' in cardRef) {
          (cardRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
        }
      }}
      data-column={col}
    >
      <div className="auto-binning-card-header">
        <input
          type="checkbox"
          className="fancy-checkbox"
          checked={isSelected}
          onChange={(e) => {
            e.stopPropagation();
            onToggle(col);
          }}
          aria-label={`Select ${col} for modeling`}
        />
        <h4>{col}</h4>
        <input
          type="checkbox"
          className="export-checkbox"
          checked={isSelectedForExport}
          onChange={(e) => {
            e.stopPropagation();
            onToggleExport(col);
          }}
          title="Select for export"
          aria-label={`Select ${col} for export`}
        />
        <span className={`var-type-tag ${varTypeTag}`}>
          {varTypeTag}
        </span>
      </div>

      <div className="auto-binning-chart">
        <div className="chart-label">WOE Graph</div>
        {isLoading ? (
          <div className="loading-placeholder">
            <span>Loading...</span>
          </div>
        ) : chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis
                dataKey="bin"
                tick={{ fontSize: 10, fill: '#8b949e' }}
                interval={0}
                angle={-45}
                textAnchor="end"
                height={60}
              />
              <YAxis tick={{ fontSize: 10, fill: '#8b949e' }} />
              <Tooltip
                contentStyle={{
                  background: '#0d1117',
                  border: '1px solid #30363d',
                  borderRadius: '6px',
                  fontSize: '12px'
                }}
              />
              <Line
                type="monotone"
                dataKey="WOE"
                stroke="#2ea043"
                strokeWidth={2}
                dot={{ r: 3, fill: '#2ea043' }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="no-data-placeholder">
            <span>No WOE data available</span>
          </div>
        )}
      </div>

      <div className="auto-binning-footer">
        <div className="iv-display">
          <span className="iv-label">Total IV:</span>
          <span className={`iv-value ${totalIV < 0.02 ? 'weak' : totalIV < 0.1 ? 'medium' : 'strong'}`}>
            {totalIV.toFixed(4)}
          </span>
        </div>
        <button
          className="configure-manually-btn"
          onClick={() => onConfigureManually(col)}
        >
          Configure Manually
        </button>
      </div>
    </div>
  );
}, (prevProps, nextProps) => {
  // Custom comparison function - only re-render if relevant props change
  // Compare woeData by checking if the stats array reference changed
  const prevStats = prevProps.woeData?.stats;
  const nextStats = nextProps.woeData?.stats;
  const woeDataEqual = prevStats === nextStats; // Reference equality - if stats array hasn't changed, don't re-render
  
  return (
    prevProps.col === nextProps.col &&
    prevProps.isSelected === nextProps.isSelected &&
    prevProps.isSelectedForExport === nextProps.isSelectedForExport &&
    prevProps.isLoading === nextProps.isLoading &&
    woeDataEqual &&
    prevProps.continuousColumns === nextProps.continuousColumns
  );
});

AutoBinningCard.displayName = 'AutoBinningCard';

const SelectedColumnsPage = () => {
  const { state } = useLocation();
  const {
    selectedColumns: navSelectedColumns,
    discreteColumns: navDiscreteColumns,
    continuousColumns: navContinuousColumns,
    targetVariable: navTargetVariable,
    recordId: initialRecordId,
    datasetPath: navDatasetPath,
    columns: navColumns,
    modelReadyColumns: navModelReadyColumns,
    finalSelectedColumns: navFinalSelectedColumns,
  } = state || {};
  // State declarations
  const [columns] = useState<string[]>(navColumns || []);
  const [selectedColumns, setSelectedColumns] = useState<string[]>(navSelectedColumns || []);
  const [discreteColumns, setDiscreteColumns] = useState<string[]>(navDiscreteColumns || []);
  const [continuousColumns, setContinuousColumns] = useState<string[]>(navContinuousColumns || []);
  const [targetVariable, setTargetVariable] = useState<string>(navTargetVariable || '');
  const [activeColumn, setActiveColumn] = useState<string>('');
  const [currentStep, setCurrentStep] = useState(0); // Start at step 0 (Column Selection)
  const [currentPage, setCurrentPage] = useState(1);
  const [columnsPerPage, setColumnsPerPage] = useState(7);
  const columnListRef = useRef<HTMLDivElement>(null);
  const previousStepRef = useRef<number>(0); // Track previous step to detect navigation source
  
  // Calculate columns per page based on available viewport height
  useEffect(() => {
    if (currentStep !== 0) return; // Only calculate for Classification step
    
    let resizeObserver: ResizeObserver | null = null;
    let timeoutIds: ReturnType<typeof setTimeout>[] = [];
    
    const calculateColumnsPerPage = () => {
      let availableHeight = 0;
      
      // Try to get height from ref first
      if (columnListRef.current) {
        availableHeight = columnListRef.current.clientHeight;
      }
      
      // Fallback: use viewport height calculation if ref height is not available
      if (availableHeight <= 50) {
        // Calculate based on viewport height minus estimated header/footer space
        const viewportHeight = window.innerHeight;
        const estimatedHeaderFooterSpace = 300; // navbar, progress bar, padding, etc.
        availableHeight = viewportHeight - estimatedHeaderFooterSpace;
        
        // If still too small, use a reasonable default
        if (availableHeight <= 50) {
          availableHeight = 500; // fallback default
        }
      }
      
      // Estimate height per column box: padding (20px) + content (~40px) + gap (8px) ≈ 68px
      // Using a more conservative estimate to account for radio buttons and variable content
      const estimatedColumnHeight = 75; // pixels per column including gap
      
      // Calculate how many columns can fit, with a minimum of 3 and maximum of 20
      const calculatedColumns = Math.max(3, Math.min(20, Math.floor(availableHeight / estimatedColumnHeight)));
      
      // Always update to ensure it changes from the initial 7
      setColumnsPerPage(calculatedColumns);
    };

    // Calculate multiple times to ensure we get the right value
    timeoutIds.push(setTimeout(calculateColumnsPerPage, 100));
    timeoutIds.push(setTimeout(calculateColumnsPerPage, 300));
    timeoutIds.push(setTimeout(calculateColumnsPerPage, 600));
    timeoutIds.push(setTimeout(calculateColumnsPerPage, 1000));
    
    // Setup ResizeObserver
    const setupObserver = () => {
      if (columnListRef.current) {
        if (resizeObserver) {
          resizeObserver.disconnect();
        }
        resizeObserver = new ResizeObserver(() => {
          calculateColumnsPerPage();
        });
        resizeObserver.observe(columnListRef.current);
      } else {
        const retryId = setTimeout(setupObserver, 200);
        timeoutIds.push(retryId);
      }
    };
    
    timeoutIds.push(setTimeout(setupObserver, 500));
    
    // Also listen to window resize
    window.addEventListener('resize', calculateColumnsPerPage);

    return () => {
      timeoutIds.forEach(id => clearTimeout(id));
      window.removeEventListener('resize', calculateColumnsPerPage);
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
    };
  }, [currentStep]);

  const totalPages = Math.ceil(columns.length / columnsPerPage);
  const paginatedColumns = columns.slice(
    (currentPage - 1) * columnsPerPage,
    currentPage * columnsPerPage
  );
  const [targetCounts, setTargetCounts] = useState<Record<string, number>>({});
  const [selectedForUnivariate, setSelectedForUnivariate] = useState<string[]>([]);
  const [univariateResults, setUnivariateResults] = useState<Record<string, any>>({});
  const [coarseBinResults, setCoarseBinResults] = useState<Record<string, NormalizedBin[]>>({});
  const [fineBinResults, setFineBinResults] = useState<Record<string, NormalizedBin[]>>({});
  const [selectedFineBins, setSelectedFineBins] = useState<Record<string, string[]>>({});
  const [binMergeHistory, setBinMergeHistory] = useState<Record<string, Record<string, any[]>>>({});
  const [recordId, setRecordId] = useState<number | undefined>(initialRecordId);
  const [datasetPath, setDatasetPath] = useState<string>(navDatasetPath || '');
  const [woeIvResults, setWoeIvResults] = useState<Record<string, { iv?: number; stats: NormalizedBin[] }>>({});
  const woeIvResultsRef = useRef<Record<string, { iv?: number; stats: NormalizedBin[] }>>({});
  const [woeReadyColumns, setWoeReadyColumns] = useState<Set<string>>(new Set());
  const [selectedForModeling, setSelectedForModeling] = useState<string[]>(navModelReadyColumns || []); // For Column Selection & Binning (model_ready)
  const [selectedForFinalModeling, setSelectedForFinalModeling] = useState<string[]>(navFinalSelectedColumns || []); // For Model Training (final_selected)
  const [vifData, setVifData] = useState<Record<string, number | null>>({}); // VIF values for each variable
  const [significanceData, setSignificanceData] = useState<Record<string, { pValue: number | null; level: string }>>({}); // Significance data for each variable
  const [isCalculatingVIF, setIsCalculatingVIF] = useState(false);
  const [hasLRCompleted, setHasLRCompleted] = useState(false); // Track if LR has completed
  const [triggerLogisticRegression, setTriggerLogisticRegression] = useState(0);
  const [triggerRandomForest, setTriggerRandomForest] = useState(0);
  const [triggerXGBoost, setTriggerXGBoost] = useState(0);
  const [triggerStacking, setTriggerStacking] = useState(0);
  const [preprocessSelectionSaved, setPreprocessSelectionSaved] = useState(false); // Whether preprocessing selection has been saved
  const [notification, setNotification] = useState<string | null>(null);
  const [scoreCardData, setScoreCardData] = useState<any>(null);
  const [testScoreLoading, setTestScoreLoading] = useState(false);
  const [testScoreResults, setTestScoreResults] = useState<any[] | null>(null);
  const [testScoreKSData, setTestScoreKSData] = useState<{ ks_stat: number | null; ks_threshold: number | null; ks_curve: any[] | null } | null>(null);
  const [testScoreRiskBands, setTestScoreRiskBands] = useState<any[] | null>(null);
  const [createRangesLoading, setCreateRangesLoading] = useState(false);
  const [trainingScoreResults, setTrainingScoreResults] = useState<any[] | null>(null);
  const [trainingScoreKSData, setTrainingScoreKSData] = useState<{ ks_stat: number | null; ks_threshold: number | null; ks_curve: any[] | null } | null>(null);
  const [trainingScoreRiskBands, setTrainingScoreRiskBands] = useState<any[] | null>(null);
  const [currentDataSource, setCurrentDataSource] = useState<'training' | 'test'>('test'); // Track which data source is currently displayed
  const [isRiskLabelsInverted, setIsRiskLabelsInverted] = useState(false); // Track if risk labels are inverted (higher score = higher risk)
  const [invertScoreRange, setInvertScoreRange] = useState(false); // If true: 600-0 range (higher score = higher risk)
  const [generatingScoreCard, setGeneratingScoreCard] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedModel, setSelectedModel] = useState<string>('stacking'); // Default to stacking ensemble
  const [selectedModelForScorecard, setSelectedModelForScorecard] = useState<string>('stacking'); // Default to stacking ensemble
  const [developerMode, setDeveloperMode] = useState<boolean>(false); // Developer mode toggle - off by default
  const [logisticResults, setLogisticResults] = useState<any>(null);
  const [randomForestResults, setRandomForestResults] = useState<any>(null);
  const [xgboostResults, setXgboostResults] = useState<any>(null);
  const [stackingResults, setStackingResults] = useState<any>(null);
  const [binningMode, setBinningMode] = useState<'manual' | 'auto'>('manual');
  const isLoadingAutoBinning = useRef(false);
  const [loadingColumns] = useState<Set<string>>(new Set());
  const [isLoadingCoarseBins, setIsLoadingCoarseBins] = useState(false);
  const [isLoadingAllAutoMonotonic, setIsLoadingAllAutoMonotonic] = useState(false);
  const [isLoadingAIClassification, setIsLoadingAIClassification] = useState(false);
  const [selectedForExport, setSelectedForExport] = useState<string[]>([]); // Charts selected for export
  const [isExportingCharts, setIsExportingCharts] = useState(false); // Export loading state
  const chartCardRefs = useRef<Record<string, HTMLDivElement | null>>({}); // Refs for chart cards
  const updateLocalWoeState = useCallback(
    (col: string, payload?: { iv?: number; stats?: any[]; bins?: any[] }) => {
      if (!payload) {
        return false;
      }
      const normalized = normalizeBinArray(payload.stats || payload.bins || []);
      if (normalized.length === 0 && typeof payload.iv !== 'number') {
        return false;
      }
      setWoeIvResults((prev) => {
        const next = {
          ...prev,
          [col]: {
            iv: typeof payload.iv === 'number' ? payload.iv : prev[col]?.iv,
            stats: normalized.length > 0 ? normalized : prev[col]?.stats || [],
          },
        };
        woeIvResultsRef.current = next;
        return next;
      });
      setWoeReadyColumns((prev) => {
        const next = new Set(prev);
        next.add(col);
        return next;
      });
      return true;
    },
    [setWoeIvResults, setWoeReadyColumns]
  );


  // Add to your existing state declarations
  const [binScoringMetrics, setBinScoringMetrics] = useState<Record<string, any[]>>({});
  const [binScoringTotals, setBinScoringTotals] = useState<Record<string, { total_good: number; total_bad: number; total_zero_one_ratio?: number }>>({});
  // Removed UI sorting controls per request; keep search only
  // Helper to format IV class if needed later
  // (kept here for possible future IV badge usage)
  // Filtered and sorted columns
  // Filter columns by search term and sort alphabetically by name
  // Add these state setters to your component
  // Cache model results to localStorage
  const saveCachedModelResults = (modelType: string, results: any) => {
    if (!recordId || !results) return;
    
    try {
      const cacheKey = `model_results_${recordId}_${modelType}`;
      localStorage.setItem(cacheKey, JSON.stringify({
        results: results,
        timestamp: Date.now()
      }));
      console.log(`[Model Cache] Saved ${modelType} results to cache`);
    } catch (error) {
      console.error(`[Model Cache] Error saving ${modelType} results:`, error);
    }
  };

  // Load cached model results from localStorage
  const loadCachedModelResults = (modelType: string): any | null => {
    if (!recordId) return null;
    
    try {
      const cacheKey = `model_results_${recordId}_${modelType}`;
      const cached = localStorage.getItem(cacheKey);
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed.results) {
          console.log(`[Model Cache] Loaded ${modelType} results from cache`);
          return parsed.results;
        }
      }
    } catch (error) {
      console.error(`[Model Cache] Error loading ${modelType} results:`, error);
    }
    return null;
  };

  // Cache selectedForFinalModeling to localStorage
  const saveCachedFinalSelected = (finalSelected: string[]) => {
    if (!recordId) return;
    
    try {
      const cacheKey = `final_selected_${recordId}`;
      localStorage.setItem(cacheKey, JSON.stringify({
        finalSelected: finalSelected,
        timestamp: Date.now()
      }));
      console.log('[Final Selected Cache] Saved final_selected to cache:', finalSelected);
    } catch (error) {
      console.error('[Final Selected Cache] Error saving final_selected:', error);
    }
  };

  // Load cached selectedForFinalModeling from localStorage
  const loadCachedFinalSelected = (): string[] | null => {
    if (!recordId) return null;
    
    try {
      const cacheKey = `final_selected_${recordId}`;
      const cached = localStorage.getItem(cacheKey);
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed.finalSelected && Array.isArray(parsed.finalSelected)) {
          console.log('[Final Selected Cache] Loaded final_selected from cache:', parsed.finalSelected);
          return parsed.finalSelected;
        }
      }
    } catch (error) {
      console.error('[Final Selected Cache] Error loading final_selected:', error);
    }
    return null;
  };

  const handleLogisticResults = (results: any) => {
    setLogisticResults(results);
    saveCachedModelResults('logistic', results);
  };

  const handleRandomForestResults = (results: any) => {
    setRandomForestResults(results);
    saveCachedModelResults('random_forest', results);
  };

  const handleXGBoostResults = (results: any) => {
    setXgboostResults(results);
    saveCachedModelResults('xgboost', results);
  };

  const handleStackingResults = (results: any) => {
    setStackingResults(results);
    saveCachedModelResults('stacking', results);
  };

  const syncBinningFromState = useCallback(
    (nextState?: Partial<NormalizedBinningState>) => {
      if (!nextState) {
        return;
      }

      if (nextState.univariate && Object.keys(nextState.univariate).length > 0) {
        setUnivariateResults((prev) => ({ ...prev, ...nextState.univariate! }));
      }

      if (nextState.coarse && Object.keys(nextState.coarse).length > 0) {
        setCoarseBinResults((prev) => ({ ...prev, ...nextState.coarse! }));
      }

      if (nextState.fine && Object.keys(nextState.fine).length > 0) {
        setFineBinResults((prev) => ({ ...prev, ...nextState.fine! }));
      }

      if (nextState.merged && Object.keys(nextState.merged).length > 0) {
        setBinMergeHistory((prev) => {
          const merged = nextState.merged!;
          const updated = { ...prev };
          Object.entries(merged).forEach(([col, value]) => {
            if (value && typeof value === 'object' && !Array.isArray(value)) {
              updated[col] = value as Record<string, any[]>;
            }
          });
          return updated;
        });
      }

      if (nextState.woe && Object.keys(nextState.woe).length > 0) {
        setWoeIvResults((prev) => {
          const woe = nextState.woe!;
          const updated = { ...prev };
          Object.entries(woe).forEach(([col, entry]) => {
            if (entry && typeof entry === 'object' && 'stats' in entry) {
              updated[col] = {
                iv: typeof entry.iv === 'number' ? entry.iv : undefined,
                stats: entry.stats || [],
              };
            }
          });
          return updated;
        });
        setWoeReadyColumns((prev) => {
          const updated = new Set(prev);
          Object.keys(nextState.woe!).forEach((col) => updated.add(col));
          return updated;
        });
      }
    },
    []
  );

  // Update your model components to pass these handlers
  // Filter columns by search term, preserving the sorted order from selectedColumns
  // (selectedColumns is sorted by: monotonic+high IV+more bins > monotonic+lower IV > non-monotonic)
  const filteredColumns = selectedColumns
    .filter(col => col.toLowerCase().includes(searchTerm.toLowerCase()));
  // Recommend functionality removed (UI buttons removed per request)
  // Initialize component state from navigation state
  useEffect(() => {
    if (!state) return;

    console.log('🔄 SelectedColumnsPage: Initializing from navigation state', {
      hasState: !!state,
      selectedColumns: navSelectedColumns?.length,
      discreteColumns: navDiscreteColumns?.length,
      continuousColumns: navContinuousColumns?.length,
      recordId: initialRecordId,
      datasetPath: navDatasetPath
    });

    const anyUnivariate = (state as any).univariateResults;
    const anyFine = (state as any).fineBinResults;
    const anyCross = (state as any).crossTabResults;
    const anyWoe = (state as any).woeIvResults;
    const incomingBinningState = (state as any).binningState as Partial<NormalizedBinningState> | undefined;

    if (anyUnivariate) {
      console.log('✅ Setting univariate results:', Object.keys(anyUnivariate).length, 'columns');
      const normalized: Record<string, any> = {};
      Object.entries(anyUnivariate).forEach(([col, entry]: [string, any]) => {
        normalized[col] = {
          ...entry,
          stats: normalizeBinArray(entry?.stats || entry || []),
        };
      });
      setUnivariateResults((prev) => ({ ...prev, ...normalized }));
    }
    if (anyFine) {
      console.log('✅ Setting fine bin results:', Object.keys(anyFine).length, 'columns');
      const normalizedFine: Record<string, NormalizedBin[]> = {};
      Object.entries(anyFine).forEach(([col, bins]: [string, any]) => {
        normalizedFine[col] = normalizeBinArray(bins);
      });
      setFineBinResults((prev) => ({ ...prev, ...normalizedFine }));
    }
    if (anyCross) {
      console.log('✅ Setting coarse bin results:', Object.keys(anyCross).length, 'columns');
      const normalizedCoarse: Record<string, NormalizedBin[]> = {};
      Object.entries(anyCross).forEach(([col, bins]: [string, any]) => {
        normalizedCoarse[col] = normalizeBinArray(bins?.stats || bins);
      });
      setCoarseBinResults((prev) => ({ ...prev, ...normalizedCoarse }));
    }
    if (anyWoe) {
      const woeKeys = Object.keys(anyWoe);
      console.log('✅ Setting WOE/IV results:', woeKeys.length, 'columns');
      const normalizedWoe: Record<string, { iv?: number; stats: NormalizedBin[] }> = {};
      woeKeys.forEach((col) => {
        const entry = anyWoe[col];
        normalizedWoe[col] = {
          ...entry,
          stats: normalizeBinArray(entry?.stats || entry?.bins || []),
        };
      });
      setWoeIvResults((prev) => ({ ...prev, ...normalizedWoe }));
      setWoeReadyColumns((prev) => {
        const next = new Set(prev);
        woeKeys.forEach((col) => next.add(col));
        return next;
      });
    }
    if (navSelectedColumns) {
      console.log('✅ Setting selected columns:', navSelectedColumns.length);
      setSelectedColumns(navSelectedColumns);
      // Also set selectedForUnivariate for Classification checkboxes
      setSelectedForUnivariate(navSelectedColumns);
    }
    if (navDiscreteColumns) {
      console.log('✅ Setting discrete columns:', navDiscreteColumns.length);
      setDiscreteColumns(navDiscreteColumns);
    }
    if (navContinuousColumns) {
      console.log('✅ Setting continuous columns:', navContinuousColumns.length);
      setContinuousColumns(navContinuousColumns);
    }
    if (navTargetVariable) {
      console.log('✅ Setting target variable:', navTargetVariable);
      setTargetVariable(navTargetVariable);
    }
    if ((state as any).recordId) {
      console.log('✅ Setting record ID:', (state as any).recordId);
      setRecordId((state as any).recordId);
    }
    if ((state as any).datasetPath) {
      console.log('✅ Setting dataset path:', (state as any).datasetPath);
      setDatasetPath((state as any).datasetPath);
    }
    if (incomingBinningState) {
      syncBinningFromState(incomingBinningState);
    }
  }, [state, navSelectedColumns, navDiscreteColumns, navContinuousColumns, navTargetVariable, initialRecordId, navDatasetPath, syncBinningFromState]);
  // Sync WOE/IV states and selectedForModeling when selectedColumns changes
  useEffect(() => {
    const currentWoeKeys = Object.keys(woeIvResults);
    const columnsToRemove = currentWoeKeys.filter((col) => !selectedColumns.includes(col));
    if (columnsToRemove.length > 0) {
      setWoeIvResults((prev) => {
        const newResults = { ...prev };
        columnsToRemove.forEach((col) => delete newResults[col]);
        return newResults;
      });
      setWoeReadyColumns((prev) => {
        const newSet = new Set(prev);
        columnsToRemove.forEach((col) => newSet.delete(col));
        return newSet;
      });
      setSelectedForModeling((prev) => prev.filter((col) => selectedColumns.includes(col)));
      // Notification removed per user request
    }
  }, [selectedColumns, woeIvResults, woeReadyColumns]);
  // Column Selection functions (from ColumnSelectionPage)
  const handleTypeChange = (column: string, type: string) => {
    let computedDiscrete: string[] = [];
    let computedContinuous: string[] = [];

    setDiscreteColumns(prev => {
      const next = type === 'discrete'
        ? Array.from(new Set([...prev, column]))
        : prev.filter(c => c !== column);
      computedDiscrete = next;
      return next;
    });

    setContinuousColumns(prev => {
      const next = type === 'continuous'
        ? Array.from(new Set([...prev, column]))
        : prev.filter(c => c !== column);
      computedContinuous = next;
      return next;
    });

    // Persist change to backend (non-blocking)
    (async () => {
      try {
        await authPost('/api/upsert-single-record', {
            dataset_path: datasetPath,
            discrete_columns: computedDiscrete,
            continuous_columns: computedContinuous,
            selected_columns: selectedForUnivariate,
            target_variable: targetVariable,
            record_id: recordId
        });
      } catch (err) {
        console.error('Failed to persist type change:', err);
      }
    })();
  };

  const assignRemainingToContinuous = () => {
    const selectedDiscrete = new Set(discreteColumns);
    const remaining = columns.filter(col => !selectedDiscrete.has(col) && col !== targetVariable);
    setContinuousColumns(remaining);

    // Persist to backend
    (async () => {
      try {
        await authPost('/api/upsert-single-record', {
            dataset_path: datasetPath,
            discrete_columns: discreteColumns,
            continuous_columns: remaining,
            selected_columns: selectedForUnivariate,
            target_variable: targetVariable,
            record_id: recordId
        });
      } catch (err) {
        console.error('Failed to persist remaining columns:', err);
      }
    })();
  };

  const toggleSelectedForUnivariate = (col: string) => {
    setSelectedForUnivariate(prev =>
      prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col]
    );
  };

  const toggleSelectAllDiscrete = (selectAll?: boolean) => {
    setSelectedForUnivariate(prev => {
      const currentSet = new Set(prev);
      if (selectAll === false) {
        discreteColumns.forEach(c => currentSet.delete(c));
        return Array.from(currentSet);
      }
      if (selectAll === true) {
        discreteColumns.forEach(c => currentSet.add(c));
        return Array.from(currentSet);
      }
      const allSelected = discreteColumns.every(c => currentSet.has(c));
      if (allSelected) {
        discreteColumns.forEach(c => currentSet.delete(c));
      } else {
        discreteColumns.forEach(c => currentSet.add(c));
      }
      return Array.from(currentSet);
    });
  };

  const toggleSelectAllContinuous = (selectAll?: boolean) => {
    setSelectedForUnivariate(prev => {
      const currentSet = new Set(prev);
      if (selectAll === false) {
        continuousColumns.forEach(c => currentSet.delete(c));
        return Array.from(currentSet);
      }
      if (selectAll === true) {
        continuousColumns.forEach(c => currentSet.add(c));
        return Array.from(currentSet);
      }
      const allSelected = continuousColumns.every(c => currentSet.has(c));
      if (allSelected) {
        continuousColumns.forEach(c => currentSet.delete(c));
      } else {
        continuousColumns.forEach(c => currentSet.add(c));
      }
      return Array.from(currentSet);
    });
  };

  const handleNextPage = () => {
    const totalPages = Math.ceil(columns.length / columnsPerPage);
    if (currentPage < totalPages) {
      setCurrentPage(prev => prev + 1);
    }
  };

  const handlePrevPage = () => {
    if (currentPage > 1) {
      setCurrentPage(prev => prev - 1);
    }
  };
  
  // Reset to page 1 when columnsPerPage changes
  useEffect(() => {
    setCurrentPage(1);
  }, [columnsPerPage]);

  const handleProceedToFeatureSelection = async () => {
    // Fetch selected columns from database (from PreprocessingDetails)
    try {
      if (!recordId) {
        alert('No dataset ID available.');
        return;
      }

      // Fetch selected features from database
      const featuresData = await authGet(`/api/dataset/${recordId}/features`);
      const selectedFeatureNames = featuresData
        .filter((f: any) => f.selected === true)
        .map((f: any) => f.name);

      if (selectedFeatureNames.length === 0) {
        alert('Please select at least one column in the Data Preprocessing section.');
        return;
      }

      // Update the record with selected columns
      const data = await authPost('/api/upsert-single-record', {
          dataset_path: datasetPath,
          discrete_columns: discreteColumns,
          continuous_columns: continuousColumns,
          selected_columns: selectedFeatureNames,
          target_variable: targetVariable,
          record_id: recordId
      });
      if (!data.error) {
        if (data.id) setRecordId(data.id);
        setSelectedColumns(selectedFeatureNames);
        
        // Create train/test split (preprocess first, then split) - exactly as before
        console.log('[TTS] Creating train/test split when moving from Data Preprocessing to Binning...');
        try {
          const ttsData = await authPost('/api/train-test-split', {
              dataset_id: data.id || recordId,
              test_size: DEFAULT_TEST_SIZE,
              preprocess_first: true, // Preprocess before split (exactly as before)
              force_recalculate: false // Use existing split if available, but ensure it's preprocessed
          });

          if (ttsData) {
            if (ttsData.success) {
              console.log('[TTS] ✅ Train/test split created successfully:', ttsData.split_info);
              if (!ttsData.is_existing) {
                console.log(`[TTS] Split: ${ttsData.split_info.train_size} train, ${ttsData.split_info.test_size_count} test`);
                showNotification(`Train/test split created: ${ttsData.split_info.train_size} train, ${ttsData.split_info.test_size_count} test`);
              } else {
                console.log('[TTS] Using existing train/test split');
                showNotification('Using existing train/test split');
              }
            } else {
              console.warn('[TTS] ⚠️ Train/test split creation returned success=false:', ttsData);
              showNotification('Warning: Train/test split creation had issues. Check console for details.');
            }
          } else {
            console.error('[TTS] ❌ Failed to create train/test split: No response data');
            showNotification('Error creating train/test split: No response data');
          }
        } catch (ttsError) {
          console.error('[TTS] ❌ Exception creating train/test split:', ttsError);
          showNotification('Error creating train/test split. Check console for details.');
        }
        
        setCurrentStep(2); // Move to Binning step (Step 2)
      } else {
        alert(`Error: ${data.error}`);
      }
    } catch (error) {
      alert(`Error: ${error}`);
    }
  };

  // Fetch target counts
  const fetchTargetCounts = async (col: string) => {
    try {
      const data = await authPost('/api/target-distribution', {
          column: col,
          record_id: recordId,
          dataset_path: datasetPath || navDatasetPath || undefined,
      });
      if (!data.error) setTargetCounts(data);
    } catch (err) {
      console.error('Failed to fetch target counts:', err);
    }
  };

  useEffect(() => {
    if (targetVariable) fetchTargetCounts(targetVariable);
  }, [targetVariable]);

  // Persist target variable to backend when user selects it
  useEffect(() => {
    if (!targetVariable || !recordId) return;
    (async () => {
      try {
        // Persist target variable
        await authPost('/api/upsert-single-record', {
            dataset_path: datasetPath,
            discrete_columns: discreteColumns,
            continuous_columns: continuousColumns,
            selected_columns: selectedForUnivariate,
            target_variable: targetVariable,
            record_id: recordId
        });
        console.log('[TARGET] ✅ Target variable persisted to backend');
      } catch (err) {
        console.error('Failed to persist target variable:', err);
      }
    })();
  }, [targetVariable, recordId]);

  // Utility functions

  // Calculate metrics for all bins of a column
  const handleTestScoreCard = async (modelType: string = selectedModelForScorecard) => {
    setTestScoreLoading(true);
    setTestScoreResults(null);
    try {
      // Get the appropriate model results based on the selected model
      let modelResults: any = null;

      switch (modelType) {
        case 'logistic':
          modelResults = logisticResults;
          break;
        case 'random_forest':
          modelResults = randomForestResults;
          break;
        case 'xgboost':
          modelResults = xgboostResults;
          break;
        case 'stacking':
          modelResults = stackingResults;
          break;
        default:
          modelResults = logisticResults;
      }


      if (!modelResults) {
        alert(`No results available for ${modelType}. Please run the model first.`);
        setTestScoreLoading(false);
        return;
      }

      // Map frontend model type to backend model type
      const backendModelType = modelType === 'stacking' ? 'stacking_ensemble' : modelType;

      const data = await authPost('/api/apply-scorecard', {
          selected_variables: selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling,
          target: targetVariable,
          woe_transformed_data: Object.fromEntries(
            Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
          ),
          model_results: modelResults,
          model_type: backendModelType,
          record_id: recordId,
          invert_score_range: invertScoreRange  // Pass the score range inversion option
      });
      if (data.success && data.results) {
        setTestScoreResults(data.results);
        // Store KS data if available
        if (data.ks_stat !== undefined && data.ks_curve) {
          setTestScoreKSData({
            ks_stat: data.ks_stat,
            ks_threshold: data.ks_threshold || null,
            ks_curve: data.ks_curve
          });
        }
        // Store risk bands
        if (data.risk_bands && data.risk_bands.length > 0) {
          setTestScoreRiskBands(data.risk_bands);
        }
        setCurrentDataSource('test');
        showNotification(`Score card tested using ${modelType} model on test data`);
      } else {
        alert('Error applying score card: ' + (data.error || 'Unknown error'));
      }
    } catch (err) {
      alert('Error applying score card: ' + err);
    } finally {
      setTestScoreLoading(false);
    }
  };

  // Create ranges from training data
  const handleCreateRanges = async (modelType: string = selectedModelForScorecard) => {
    setCreateRangesLoading(true);
    setTrainingScoreResults(null);
    setTrainingScoreRiskBands(null);
    setTrainingScoreKSData(null);
    try {
      // Get the appropriate model results based on the selected model
      let modelResults: any = null;

      switch (modelType) {
        case 'logistic':
          modelResults = logisticResults;
          break;
        case 'random_forest':
          modelResults = randomForestResults;
          break;
        case 'xgboost':
          modelResults = xgboostResults;
          break;
        case 'stacking':
          modelResults = stackingResults;
          break;
        default:
          modelResults = logisticResults;
      }

      if (!modelResults) {
        alert(`No results available for ${modelType}. Please run the model first.`);
        setCreateRangesLoading(false);
        return;
      }

      // Map frontend model type to backend model type
      const backendModelType = modelType === 'stacking' ? 'stacking_ensemble' : modelType;

      const data = await authPost('/api/apply-scorecard', {
          selected_variables: selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling,
          target: targetVariable,
          woe_transformed_data: Object.fromEntries(
            Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
          ),
          model_results: modelResults,
          model_type: backendModelType,
          record_id: recordId,
          data_source: 'training',  // Use training data instead of test
          invert_score_range: invertScoreRange  // Pass the score range inversion option
      });
      if (data.success && data.results) {
        setTrainingScoreResults(data.results);
        // Store KS data if available
        if (data.ks_stat !== undefined && data.ks_curve) {
          setTrainingScoreKSData({
            ks_stat: data.ks_stat,
            ks_threshold: data.ks_threshold || null,
            ks_curve: data.ks_curve
          });
        }
        // Store risk bands from training data
        if (data.risk_bands && data.risk_bands.length > 0) {
          setTrainingScoreRiskBands(data.risk_bands);
        }
        setCurrentDataSource('training');
        showNotification(`Score card applied to training data using ${modelType} model`);
      } else {
        alert('Error creating ranges: ' + (data.error || 'Unknown error'));
      }
    } catch (err) {
      alert('Error creating ranges: ' + err);
    } finally {
      setCreateRangesLoading(false);
    }
  };
  const calculateAllBinMetrics = async (columnName: string, bins: NormalizedBin[]) => {
    if (!bins || bins.length === 0) {
      return null;
    }
    try {
      const data = await authPost('/api/calculate-bin-metrics', {
        bins: prepareBinMetricsPayload(bins)
      });

      if (!data) {
        return null;
      }

      if (data?.success) {
        setBinScoringMetrics(prev => ({
          ...prev,
          [columnName]: data.bin_metrics
        }));
        setBinScoringTotals(prev => ({
          ...prev,
          [columnName]: {
            total_good: Number(data.total_good ?? 0),
            total_bad: Number(data.total_bad ?? 0),
            total_zero_one_ratio: data.total_zero_one_ratio
          }
        }));
        return data.bin_metrics;
      }
      return null;
    } catch {

      return null;
    }
  };

  // Call this when bin data changes
  // Add this useEffect to debug bin matching
  useEffect(() => {
    if (activeColumn && binScoringMetrics[activeColumn] && fineBinResults[activeColumn]) {

      // Check if we can match the first bin
      const firstBin = fineBinResults[activeColumn][0];
      if (firstBin) {
        const firstBinLabel = firstBin.Bin ?? `Bin_1`;
        binScoringMetrics[activeColumn]?.find(m => m.bin_name === String(firstBinLabel));
      }
    }
  }, [activeColumn, binScoringMetrics, fineBinResults]);
  // Ensure bin scoring metrics are calculated whenever fine bin results load for the active column
  useEffect(() => {
    const tryCompute = async () => {
      try {
        if (!activeColumn) return;
        const bins = fineBinResults[activeColumn];
        if (!Array.isArray(bins) || bins.length === 0) return;
        // Only request metrics if we don't already have them
        if (!binScoringMetrics[activeColumn] || binScoringMetrics[activeColumn].length === 0) {
          await calculateAllBinMetrics(activeColumn, bins);
        }
      } catch (e) {

      }
    };
    tryCompute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeColumn, fineBinResults]);
  const formatToFourDecimals = (value: any) => (typeof value === 'number' ? value.toFixed(4) : String(value));

  const showNotification = (message: string) => {
    setNotification(message);
    setTimeout(() => setNotification(null), 3000);
  };
  const generateScoreCard = async () => {
    setGeneratingScoreCard(true);
    try {
      // Get the appropriate model results based on the selected model
      let modelResults: any = null;

      switch (selectedModelForScorecard) {
        case 'logistic':
          modelResults = logisticResults;
          break;
        case 'random_forest':
          modelResults = randomForestResults;
          break;
        case 'xgboost':
          modelResults = xgboostResults;
          break;
        case 'stacking':
          modelResults = stackingResults;
          break;
        default:
          modelResults = logisticResults;
      }

      if (!modelResults) {
        alert(`No results available for ${selectedModelForScorecard}. Please run the model first.`);
        setGeneratingScoreCard(false);
        return;
      }

      // Filter to only include variables that have WOE data
      const woeData = Object.fromEntries(
        Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
      );
      const varsToUse = selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling;
      const validVariables = varsToUse.filter(v => v in woeData && woeData[v].length > 0);

      if (validVariables.length === 0) {
        alert('No variables with WOE data available. Please calculate WOE for selected variables first.');
        setGeneratingScoreCard(false);
        return;
      }

      if (validVariables.length < varsToUse.length) {
        const missing = varsToUse.filter(v => !(v in woeData) || woeData[v].length === 0);
        console.warn(`Skipping variables without WOE data: ${missing.join(', ')}`);
      }

      // Map frontend model type to backend model type
      const backendModelType = selectedModelForScorecard === 'stacking' ? 'stacking_ensemble' : selectedModelForScorecard;

      const data = await authPost('/api/generate-scorecard', {
          selected_variables: validVariables,
          target: targetVariable,
          woe_transformed_data: Object.fromEntries(
            validVariables.map(v => [v, woeData[v]])
          ),
          model_type: backendModelType,
          model_results: modelResults,
          record_id: recordId,
          invert_score_range: invertScoreRange  // Pass the score range inversion option
      });

      if (!data) {
        alert(`Error generating score card: Failed to generate scorecard`);
        setGeneratingScoreCard(false);
        return;
      }
      if (data.success) {
        setScoreCardData(data);
        if (data.scorecard_bins) {
          const totalBins = data.scorecard_bins.length;
          const varsToUse = selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling;
          showNotification(`Score card generated with ${totalBins} bins across ${varsToUse.length} variables using ${selectedModelForScorecard} model`);
        } else {
          showNotification(`Score card generated successfully using ${selectedModelForScorecard} model!`);
        }
      } else {
        alert(`Error generating score card: ${data.error}`);
      }
    } catch (error) {
      alert(`Error generating score card: ${error}`);
    } finally {
      setGeneratingScoreCard(false);
    }
  };
  const gotoScoreCardAndGenerate = () => {
    setCurrentStep(4);
    setTimeout(() => {
      generateScoreCard();
    }, 50);
  };

  const handleDownloadScorecard = () => {
    if (!scoreCardData || !scoreCardData.scorecard_bins) {
      alert('No scorecard data available to download');
      return;
    }

    try {
      // Prepare CSV data
      const csvRows: string[] = [];
      
      // Header row
      const headers = ['Bin #', 'Variable', 'Bin Range', 'WOE', 
        (selectedModelForScorecard === 'logistic' || selectedModelForScorecard === 'stacking') ? 'Coefficient (β)' : 'Feature Importance',
        'Score'];
      csvRows.push(headers.join(','));

      // Group bins by variable
      const grouped: Record<string, any[]> = {};
      const varsToUse = selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling;
      
      scoreCardData.scorecard_bins.forEach((b: any) => {
        if (varsToUse.includes(b.variable)) {
          grouped[b.variable] = grouped[b.variable] || [];
          grouped[b.variable].push(b);
        }
      });

      // Add data rows
      Object.keys(grouped).sort().forEach(variable => {
        grouped[variable].forEach((bin: any, index: number) => {
          const row = [
            index + 1,
            `"${variable}"`,
            `"${bin.bin_range || bin.range || ''}"`,
            bin.woe !== undefined ? bin.woe.toFixed(4) : '',
            bin.coefficient !== undefined ? bin.coefficient.toFixed(4) : 
            bin.feature_importance !== undefined ? bin.feature_importance.toFixed(4) : '',
            bin.score !== undefined ? bin.score.toFixed(2) : ''
          ];
          csvRows.push(row.join(','));
        });
      });

      // Add score parameters section
      if (scoreCardData.score_parameters) {
        csvRows.push('');
        csvRows.push('Score Parameters');
        csvRows.push(`Factor,${scoreCardData.score_parameters.factor?.toFixed(4) || ''}`);
        csvRows.push(`Offset,${scoreCardData.score_parameters.offset?.toFixed(4) || ''}`);
        const scoreRangeDisplay = scoreCardData.score_parameters.invert_score_range 
          ? `${scoreCardData.score_parameters.max_score || ''} - ${scoreCardData.score_parameters.min_score || ''}`
          : `${scoreCardData.score_parameters.min_score || ''} - ${scoreCardData.score_parameters.max_score || ''}`;
        csvRows.push(`Score Range,${scoreRangeDisplay}`);
        csvRows.push(`Score Interpretation,${scoreCardData.score_parameters.invert_score_range ? 'Higher Score = Higher Risk' : 'Higher Score = Lower Risk'}`);
      }

      // Create CSV content
      const csvContent = csvRows.join('\n');
      
      // Create blob and download
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `scorecard_${selectedModelForScorecard}_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      
      showNotification('Scorecard downloaded successfully');
    } catch (error) {
      console.error('Error downloading scorecard:', error);
      alert('Failed to download scorecard. Please try again.');
    }
  };

  const runFineBinPassThrough = async (
    col: string,
    varType: string,
    mergesOverride?: Record<string, any[]>
  ): Promise<{ merges: Record<string, any[]> } | null> => {
    if (!recordId || !targetVariable) {
      return null;
    }
    try {
      const data = await authPost('/api/fine-bin', {
          variable: col,
          target: targetVariable,
          type: varType,
          bin_merges: mergesOverride || {},
          record_id: recordId,
          dashboard_selected_columns: Array.from(selectedForModeling),
      }).catch(err => {
        console.warn(`Fine-bin fallback failed for ${col}:`, err);
        return null;
      });
      if (!data) {
        return null;
      }
      if (!data.success || data.error) {
        console.warn(`Fine-bin fallback response for ${col} indicated failure`, data);
        return null;
      }
      const normalizedStats = normalizeBinArray(data.stats || []);
      const mergesToPersist = data.bin_merges || mergesOverride || {};
      setFineBinResults((prev) => ({ ...prev, [col]: normalizedStats }));
      setBinMergeHistory((prev) => ({ ...prev, [col]: mergesToPersist }));
      setSelectedFineBins((prev) => ({ ...prev, [col]: [] }));
      try {
        await calculateAllBinMetrics(col, normalizedStats);
      } catch (e) {

      }
      const appliedWoe = updateLocalWoeState(col, data.woe_iv);
      if (!appliedWoe) {
        await fetchWoeIv(col, mergesToPersist, false);
      }
      return { merges: mergesToPersist };
    } catch (error) {
      console.error(`Fine-bin fallback crashed for ${col}:`, error);
      return null;
    }
  };

  // API calls
  const loadSavedFineBins = async (
    col: string,
    varType: string
  ): Promise<{ merges: Record<string, any[]> | undefined; hydrated: boolean }> => {
    const cachedMerges = binMergeHistory[col];
    const cachedBins = fineBinResults[col];
    if (
      cachedMerges &&
      Object.keys(cachedMerges).length > 0 &&
      Array.isArray(cachedBins) &&
      cachedBins.length > 0
    ) {
      return { merges: cachedMerges, hydrated: true };
    }

    if (!recordId || !targetVariable) return { merges: undefined, hydrated: false };

    // First attempt: hydrate directly from persisted fine-bin cache (no recomputation)
    try {
      const cacheData = await authGet(`/api/finebin-cache/${recordId}/${encodeURIComponent(col)}`);
      if (cacheData?.success && Array.isArray(cacheData.stats) && cacheData.stats.length > 0) {
          const normalizedStats = normalizeBinArray(cacheData.stats);
          setFineBinResults((prev) => ({ ...prev, [col]: normalizedStats }));
          const mergesFromCache: Record<string, any[]> = cacheData.bin_merges || {};
          if (Object.keys(mergesFromCache).length > 0) {
            setBinMergeHistory((prev) => ({ ...prev, [col]: mergesFromCache }));
          }
          setSelectedFineBins((prev) => ({ ...prev, [col]: [] }));
          try {
            await calculateAllBinMetrics(col, normalizedStats);
          } catch (e) {

          }
          const cacheWoePayload =
            cacheData?.woe_iv ||
            (typeof cacheData?.iv === 'number'
              ? { iv: cacheData.iv, stats: cacheData.stats }
              : undefined);
          const woeApplied = updateLocalWoeState(col, cacheWoePayload);
          if (!woeApplied) {
            await fetchWoeIv(col, mergesFromCache, false);
          }
          return {
            merges: Object.keys(mergesFromCache).length > 0 ? mergesFromCache : cachedMerges,
            hydrated: true,
          };
        }
    } catch (cacheError) {
      console.warn(`Fine-bin cache hydrate failed for ${col}:`, cacheError);
    }

    // Fallback: pull merge blueprint then recompute via fine-bin endpoint
    try {
      const details = await authGet(`/api/finebin-details/${recordId}/${encodeURIComponent(col)}`);
      if (!Array.isArray(details) || details.length === 0) {
        return { merges: undefined, hydrated: false };
      }
      const savedMerges: Record<string, any[]> = {};
      details.forEach((row: any) => {
        if (Array.isArray(row.merged_bins) && row.merged_bins.length > 0) {
          savedMerges[row.group_id] = row.merged_bins;
        }
      });
      if (Object.keys(savedMerges).length === 0) {
        return { merges: undefined, hydrated: false };
      }
      const fallbackResult = await runFineBinPassThrough(col, varType, savedMerges);
      if (fallbackResult) {
        return { merges: fallbackResult.merges, hydrated: true };
      }
    } catch (e) {
      console.warn(`Fine-bin rehydrate failed for ${col}:`, e);
    }
    return { merges: undefined, hydrated: false };
  };
  const loadSavedData = async () => {
    if (!recordId) return;
    try {
      console.log(`[SelectedColumnsPage] 🔄 Loading saved data for record ${recordId}`);
      const recordData = await authGet(`/api/record/${recordId}`);

      // CRITICAL: Load ALL record-specific data to ensure complete isolation
      // Load dataset path from record
      if (recordData.dataset_path) {
        setDatasetPath(recordData.dataset_path);
      }

      // CRITICAL: Load target variable - this was missing!
      const targetVar = recordData.target_variable || '';
      console.log(`[SelectedColumnsPage] ✅ Loading target_variable: "${targetVar}" for record ${recordId}`);
      setTargetVariable(targetVar);

      // CRITICAL: Load discrete and continuous columns - these were missing!
      const discreteCols = Array.isArray(recordData.discrete_columns) ? recordData.discrete_columns : [];
      const continuousCols = Array.isArray(recordData.continuous_columns) ? recordData.continuous_columns : [];
      console.log(`[SelectedColumnsPage] ✅ Loading columns: ${discreteCols.length} discrete, ${continuousCols.length} continuous for record ${recordId}`);
      setDiscreteColumns(discreteCols);
      setContinuousColumns(continuousCols);

      // CRITICAL: Build set of valid columns for this record to filter selectedColumns
      const validColumnsForRecord = new Set([...discreteCols, ...continuousCols]);
      console.log(`[SelectedColumnsPage] ✅ Valid columns for record ${recordId}: ${validColumnsForRecord.size} total`);

      if (recordData.binning_data) {
        const lookup = buildTypeLookup(discreteCols, continuousCols);
        const normalized = buildBinningState(recordData.binning_data, lookup);
        syncBinningFromState(normalized);
      }

      // CRITICAL: Filter selected_columns to only include columns that exist in this record
      // This prevents features from other records appearing in binning
      if (Array.isArray(recordData.selected_columns)) {
        const filteredSelected = recordData.selected_columns.filter((col: string) => 
          validColumnsForRecord.has(col)
        );
        
        // Log if any columns were filtered out
        const filteredOut = recordData.selected_columns.filter((col: string) => 
          !validColumnsForRecord.has(col)
        );
        if (filteredOut.length > 0) {
          console.log(`[SelectedColumnsPage] ⚠️ Filtered out ${filteredOut.length} columns not in this record:`, filteredOut);
        }
        
        console.log(`[SelectedColumnsPage] ✅ Setting selectedColumns: ${filteredSelected.length} columns for record ${recordId}`);
        setSelectedColumns(filteredSelected);
        // Load selectedForUnivariate from database for Classification checkboxes
        setSelectedForUnivariate(filteredSelected);
      } else {
        // If no selected_columns, clear it
        setSelectedColumns([]);
        setSelectedForUnivariate([]);
      }

      let modelReadySelections: string[] = [];
      if (Array.isArray(recordData.dashboard_selected_columns)) {
        modelReadySelections = recordData.dashboard_selected_columns
          .map((value: any) => String(value).trim())
          .filter(Boolean);
      }
      let finalSelections: string[] = [];
      if (Array.isArray(recordData.final_selected_columns)) {
        finalSelections = recordData.final_selected_columns
          .map((value: any) => String(value).trim())
          .filter(Boolean);
      }

      try {
        const featureList = await authGet(`/api/dataset/${recordId}/features`);
        if (Array.isArray(featureList)) {
            const modelReadyFromDb = featureList
              .filter((feature: any) => feature?.model_ready)
              .map((feature: any) => String(feature.name).trim())
              .filter(Boolean);
            if (modelReadyFromDb.length > 0) {
              modelReadySelections = modelReadyFromDb;
            }

            const finalSelectedFromDb = featureList
              .filter((feature: any) => feature?.final_selected)
              .map((feature: any) => String(feature.name).trim())
              .filter(Boolean);
            if (finalSelectedFromDb.length > 0) {
              finalSelections = finalSelectedFromDb;
            }
          }
      } catch (err) {
        console.error('Failed to load feature selections from database:', err);
      }

      setSelectedForModeling(modelReadySelections);
      setSelectedForFinalModeling(finalSelections);
      
      console.log(`[SelectedColumnsPage] ✅ Successfully loaded all data for record ${recordId}`);
    } catch (e) {
      console.error(`[SelectedColumnsPage] ❌ Error loading saved data for record ${recordId}:`, e);
    }
  };
  const handleColumnClick = async (col: string) => {
    // Allow re-fetch if coming from auto mode or if data is missing
    if (col === activeColumn && fineBinResults[col] && fineBinResults[col].length > 0) {
      return; // Prevent re-fetching if already active and has data
    }
    setActiveColumn(col);
    
    try {
      const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';

      // First, try to load saved fine bins from database
      const { merges, hydrated } = await loadSavedFineBins(col, varType);

      if (hydrated) {
        await new Promise(resolve => setTimeout(resolve, 300));
        return;
      }

      if (merges && Object.keys(merges).length > 0) {
        // Data exists in database, bins were loaded by loadSavedFineBins
        const mergePayload = merges;

        // Fetch WOE/IV using existing bins
        const updatedWoe = await fetchWoeIv(col, mergePayload, false);

        if (updatedWoe) {
          setWoeReadyColumns((prev) => new Set(prev).add(col));
        }
        await new Promise(resolve => setTimeout(resolve, 300));
      } else {
        // No saved data - calculate from scratch and store
        const data = await authPost('/api/univariate-analysis', {
            discrete: varType === 'discrete' ? [col] : [],
            continuous: varType === 'continuous' ? [col] : [],
            target: targetVariable,
            record_id: recordId, // Pass record_id to persist results
        });
        const coarseStats = normalizeBinArray(data[col]?.stats || data[col] || []);
        setUnivariateResults((prev) => ({ ...prev, [col]: { ...(data[col] || {}), stats: coarseStats } }));
        setCoarseBinResults((prev) => ({ ...prev, [col]: coarseStats }));
        setFineBinResults((prev) => ({ ...prev, [col]: coarseStats }));

        // Precompute bin scoring metrics for the initial fine/coarse bins
        try {
          await calculateAllBinMetrics(col, coarseStats);
        } catch (e) {
          console.error('Error calculating bin metrics:', e);
        }

        setBinMergeHistory((prev) => ({ ...prev, [col]: prev[col] || {} }));
        setSelectedFineBins((prev) => ({ ...prev, [col]: [] }));

        // Calculate and store WOE/IV
        const updatedWoe = await fetchWoeIv(col, undefined, false);

        if (updatedWoe) {
          setWoeReadyColumns((prev) => new Set(prev).add(col));
        }
        
        await new Promise(resolve => setTimeout(resolve, 300));
      }
    } catch (err) {
      console.error('Error in handleColumnClick:', err);
      await new Promise(resolve => setTimeout(resolve, 1000));
      alert('Error fetching coarse bin results');
    }
  };
  const toggleFineBinSelection = (col: string, binLabel: string) => {
    const normalized = String(binLabel);
    setSelectedFineBins((prev) => {
      const current = prev[col] || [];
      const exists = current.includes(normalized);
      const updated = exists ? current.filter((label) => label !== normalized) : [...current, normalized];
      return { ...prev, [col]: updated };
    });
  };
  const runBinning = async (col: string) => {
    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
    const selectedLabels = Array.from(new Set((selectedFineBins[col] || []).map(String).filter(Boolean)));

    if (selectedLabels.length < 2) {
      showNotification('Select at least two bins to merge.');
      return;
    }

    const history = binMergeHistory[col] || {};

    // Expand selected labels using history to get underlying bin labels
    const expandedSelection = Array.from(new Set(
      selectedLabels.flatMap(label => {
        const underlying = history[label];
        if (Array.isArray(underlying) && underlying.length > 0) {
          return underlying.map(String).filter(Boolean);
        }
        return [String(label).trim()];
      })
    ));

    if (expandedSelection.length < 2) {
      showNotification('Selected bins do not resolve to at least two distinct bins to merge.');
      return;
    }

    // Remove any old merges that overlap with the new merge
    const filteredHistoryEntries = Object.entries(history).filter(([, bins]) => {
      if (!Array.isArray(bins)) return true;
      return !bins.some(b => expandedSelection.includes(String(b).trim()));
    });
    const filteredHistory = Object.fromEntries(filteredHistoryEntries);

    // Create merge key - use sorted labels for consistency
    const sortedExpanded = [...expandedSelection].sort((a, b) => a.localeCompare(b));
    const mergeKey = varType === 'continuous'
      ? `Merged_${Object.keys(filteredHistory).length + 1}`
      : sortedExpanded.join(', ');  // For discrete, use comma-separated labels

    const payloadMerges = { ...filteredHistory, [mergeKey]: sortedExpanded };

    try {
      // Re-run coarse binning to get latest stats
      const coarseData = await authPost('/api/univariate-analysis', {
          discrete: varType === 'discrete' ? [col] : [],
          continuous: varType === 'continuous' ? [col] : [],
          target: targetVariable,
          record_id: recordId,
      });
      const coarseStats = normalizeBinArray(coarseData[col]?.stats || coarseData[col] || []);
      const updatedUnivariate = {
        ...univariateResults,
        [col]: { ...(coarseData[col] || {}), stats: coarseStats },
      };
      const updatedCoarse = { ...coarseBinResults, [col]: coarseStats };
      setUnivariateResults(updatedUnivariate);
      setCoarseBinResults(updatedCoarse);

      // Run fine binning
      const fineData = await authPost('/api/fine-bin', {
          variable: col,
          target: targetVariable,
          type: varType,
          bin_merges: payloadMerges,
          record_id: recordId,
          dashboard_selected_columns: selectedForModeling,
      });

      if (!fineData.success) throw new Error(fineData.error);

      const mergesReturned = fineData.bin_merges || payloadMerges;
      const normalizedFine = normalizeBinArray(fineData.stats || []);
      const updatedFine = { ...fineBinResults, [col]: normalizedFine };
      const updatedHistory = { ...binMergeHistory, [col]: mergesReturned };
      setFineBinResults(updatedFine);
      setBinMergeHistory(updatedHistory);
      setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

      // Recalculate bin scoring metrics (G/B odd, index, combined index, etc.) for the updated bins
      try {
        await calculateAllBinMetrics(col, normalizedFine);
      } catch (e) {

      }

      const latestWoe = await fetchWoeIv(col, mergesReturned, false);
      if (latestWoe) {
        setWoeReadyColumns(prev => new Set(prev).add(col));
      }

      await persistFineBinColumn(col, mergesReturned, {
        univariateResults: updatedUnivariate,
        fineBinResults: updatedFine,
        crosstabResults: updatedCoarse,
        woeIvResults: latestWoe ?? woeIvResultsRef.current,
      });
      showNotification(`Bins merged successfully for ${col}. ${normalizedFine.length} bins remaining.`);
    } catch (err) {
      console.error('Error running binning:', err);
      const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred';
      alert(`Error running binning: ${errorMessage}`);
      showNotification(`Failed to merge bins for ${col}: ${errorMessage}`);
    }
  };
  // const undoBinMerge = (col: string) => {
  // if (binMergeStack[col]) {
  // setBinMergeHistory((prev) => ({
  // ...prev,
  // [col]: typeof binMergeStack[col] === 'object' && !Array.isArray(binMergeStack[col]) ? binMergeStack[col] : {},
  // }));
  // setBinMergeStack((prev) => {
  // const newStack = { ...prev };
  // delete newStack[col];
  // return newStack;
  // });
  // showNotification(`Undo last merge for ${col}`);
  // // Re-run fine binning with previous history
  // runBinning(col);
  // } else {
  // showNotification(`No undo available for ${col}`);
  // }
  // };
  // Unmerge a specific merged fine bin for a column and refresh results
  const unmergeFineBin = async (col: string, mergedLabelRaw: any) => {
    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
    const history = binMergeHistory[col] || {};
    const mergedLabel = String(mergedLabelRaw);

    let keyToRemove: string | null = null;

    if (varType === 'discrete') {
      // Match exactly on the merged key (e.g., "A, B, C")
      const normalizedTarget = mergedLabel.split(',').map(s => s.trim()).sort().join(', ');
      keyToRemove = Object.keys(history).find(k => {
        const normalizedKey = k.split(',').map(s => s.trim()).sort().join(', ');
        return normalizedKey === normalizedTarget;
      }) || (history[mergedLabel] ? mergedLabel : null);
    } else {
      keyToRemove = mergedLabel;
    }

    if (!keyToRemove || !history[keyToRemove]) {
      showNotification(`Could not find merge for '${mergedLabel}'`);
      return;
    }

    const newHistory = { ...history };
    delete newHistory[keyToRemove];

    // Re-run fine binning
    try {
      const data = await authPost('/api/fine-bin', {
          variable: col,
          target: targetVariable,
          type: varType,
          bin_merges: newHistory,
          record_id: recordId,
          dashboard_selected_columns: selectedForModeling,
      });
      
      if (!data.success) {
        showNotification(`Error: ${data.error || 'Fine binning returned no results'}`);
        return;
      }

    const normalizedStats = normalizeBinArray(data.stats || []);
    const updatedFine = { ...fineBinResults, [col]: normalizedStats };
    const updatedHistory = { ...binMergeHistory, [col]: data.bin_merges || newHistory };
    setFineBinResults(updatedFine);
    setBinMergeHistory(updatedHistory);
    setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

    // Recalculate metrics for the updated bins
    try {
      await calculateAllBinMetrics(col, normalizedStats);
    } catch (e) {

    }

    const latestWoe = await fetchWoeIv(col, data.bin_merges || newHistory, false);
    if (latestWoe) {
      setWoeReadyColumns(prev => new Set(prev).add(col));
    }
    await persistFineBinColumn(col, data.bin_merges || newHistory, {
      fineBinResults: updatedFine,
      woeIvResults: latestWoe ?? woeIvResultsRef.current,
      crosstabResults: coarseBinResults,
      univariateResults,
    });

    showNotification(`Unmerged '${mergedLabel}'`);
    } catch (err) {
      console.error('Error unmerging fine bin:', err);
      showNotification(`Error: ${err instanceof Error ? err.message : 'Failed to unmerge fine bin'}`);
    }
  };
  const resetFineBinning = async (col: string) => {
    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';

    try {
      // Call backend API to reset binning and delete all binning data including merged_bins
      const resetData = await authPost('/api/reset-bins', {
          variable: col,
          target: targetVariable,
          type: varType,
          record_id: recordId,
      });
      
      // Reset UI state
      const clearedFine = { ...fineBinResults, [col]: [] };
      const clearedHistory = { ...binMergeHistory, [col]: {} };
      setFineBinResults(clearedFine);
      setBinMergeHistory(clearedHistory);
      setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

      // Get the coarse bins from the reset response
      const newStats = normalizeBinArray(resetData?.stats || []);
      const updatedUnivariate = { ...univariateResults, [col]: { stats: newStats } };
      const updatedCoarse = { ...coarseBinResults, [col]: newStats };
      const updatedFine = { ...clearedFine, [col]: newStats };
      setUnivariateResults(updatedUnivariate);
      setCoarseBinResults(updatedCoarse);
      setFineBinResults(updatedFine);

      // Recompute metrics for reset bins
      try {
        await calculateAllBinMetrics(col, newStats);
      } catch (e) {
        console.error('Error calculating bin metrics:', e);
      }

      // Fetch fresh WOE/IV data
      const latestWoe = await fetchWoeIv(col, {}, false);
      if (latestWoe) {
        setWoeReadyColumns(prev => new Set(prev).add(col));
      }

      // Update WOE/IV results
      setWoeIvResults((prev) => {
        const updated = { ...prev };
        if (latestWoe && latestWoe[col]) {
          updated[col] = latestWoe[col];
        } else {
          delete updated[col];
        }
        return updated;
      });

      showNotification(`Binning reset for ${col}`);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to reset binning';
      console.error('Error resetting binning:', err);
      showNotification(`Error resetting binning: ${errorMessage}`);
      alert(`Error resetting binning: ${errorMessage}`);
    }
  };

  const runAutoMonotonicBinning = async (
    col: string,
    options: { silent?: boolean; onError?: (message: string) => void } = {}
  ): Promise<boolean> => {
    const { silent = false, onError } = options;
    if (!col) return false;
    const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';

    try {
      if (!silent) {
        showNotification(`Running auto-monotonic binning for ${col}...`);
      }

      // Call the auto-monotonic-binning API
      const data = await authPost('/api/auto-monotonic-binning', {
          variable: col,
          target: targetVariable,
          type: varType,
          direction: null,  // Auto-detect direction
          method: 'exhaustive',  // Use exhaustive algorithm
          record_id: recordId,
          dashboard_selected_columns: selectedForModeling,
      });

      if (!data.success) {
        throw new Error(data.error || 'Auto-binning failed');
      }

      // Update UI with results
      const normalizedAutoStats = normalizeBinArray(data.stats || []);
      const updatedFine = { ...fineBinResults, [col]: normalizedAutoStats };
      const updatedHistory = { ...binMergeHistory, [col]: data.bin_merges || {} };
      setFineBinResults(updatedFine);
      setBinMergeHistory(updatedHistory);
      setSelectedFineBins(prev => ({ ...prev, [col]: [] }));

      // Recalculate bin scoring metrics
      try {
        await calculateAllBinMetrics(col, normalizedAutoStats);
      } catch (e) {
        console.error('Error calculating bin metrics:', e);
      }

      // Always refresh WOE/IV from the backend to ensure we have the latest data
      // This ensures the auto binning section shows updated WOE/IV after auto fine binning
      const latestWoe = await fetchWoeIv(col, data.bin_merges || {}, false);
      
      // Also update local state with the response data as a fallback
      updateLocalWoeState(col, data.woe_iv);

      await persistFineBinColumn(col, data.bin_merges || {}, {
        fineBinResults: updatedFine,
        crosstabResults: coarseBinResults,
        univariateResults,
        woeIvResults: latestWoe ?? woeIvResultsRef.current,
      });

      // FIX: Only select if feature is BOTH model_ready AND monotonic
      // Use is_monotonic from response to ensure we only select truly monotonic features
      if (data.model_ready && data.is_monotonic && data.variable === col) {
        // Feature is model_ready AND monotonic according to the response
        setSelectedForModeling((prev) => {
          const newSet = new Set([...prev, col]);
          const updated = Array.from(newSet);
          console.log(`[runAutoMonotonicBinning] Feature ${col} is model_ready AND monotonic (from response), added to selectedForModeling`);
          return updated;
        });
      } else if (data.model_ready && !data.is_monotonic) {
        console.log(`[runAutoMonotonicBinning] Feature ${col} is model_ready but NOT monotonic, skipping selection`);
      }

      // After autobinning, fetch sorted features to update order and sync model_ready checkboxes
      // FIX: Add a small delay to ensure database is fully updated before fetching
      if (recordId) {
        // Wait a bit for database to be fully updated
        await new Promise(resolve => setTimeout(resolve, 500));
        
        try {
          // Fetch sorted features for reordering
          const sortData = await authGet(`/api/dataset/${recordId}/features-sorted`);
          const sortedFeatureNames = sortData.sorted_feature_names || [];
            
            if (sortedFeatureNames.length > 0) {
              // Reorder selectedColumns to match the sorted order
              const currentSelectedSet = new Set(selectedColumns);
              const sortedSelected = sortedFeatureNames.filter((name: string) => currentSelectedSet.has(name));
              const unsortedSelected = selectedColumns.filter((name: string) => !sortedFeatureNames.includes(name));
              const reorderedColumns = [...sortedSelected, ...unsortedSelected];
              setSelectedColumns(reorderedColumns);
            }
          
          // Fetch features to sync model_ready checkboxes (with retry if needed)
          // FIX: Retry once if model_ready status doesn't match response
          let retryCount = 0;
          const maxRetries = 2;
          while (retryCount < maxRetries) {
            const featureList = await authGet(`/api/dataset/${recordId}/features`);
            if (Array.isArray(featureList)) {
                const currentFeature = featureList.find((f: any) => f.name === col);
                // FIX: Only select features that are BOTH model_ready AND monotonic
                // Check is_monotonic from fine binning metadata
                const modelReadyFeatures = featureList
                  .filter((feature: any) => {
                    // Feature must be model_ready
                    if (!feature?.model_ready) return false;
                    // Feature must also be monotonic (check is_monotonic from binning_steps)
                    // The features API should include is_monotonic from fine binning step
                    const isMonotonic = feature?.is_monotonic === true || feature?.is_monotonic === 1;
                    if (!isMonotonic) {
                      console.log(`[runAutoMonotonicBinning] Feature ${feature.name} is model_ready but NOT monotonic, skipping`);
                      return false;
                    }
                    return true;
                  })
                  .map((feature: any) => String(feature.name).trim())
                  .filter(Boolean);
                
                // Check if the current feature's model_ready status matches the response
                if (data.model_ready && currentFeature && !currentFeature.model_ready && retryCount < maxRetries - 1) {
                  // Status doesn't match, wait and retry
                  console.log(`[runAutoMonotonicBinning] Model_ready status mismatch for ${col}, retrying...`);
                  await new Promise(resolve => setTimeout(resolve, 500));
                  retryCount++;
                  continue;
                }
                
                if (modelReadyFeatures.length > 0) {
                  // Update selectedForModeling to include all model_ready features
                  setSelectedForModeling((prev) => {
                    const newSet = new Set([...prev, ...modelReadyFeatures]);
                    const updated = Array.from(newSet);
                    console.log(`[runAutoMonotonicBinning] Synced ${modelReadyFeatures.length} model_ready features after binning ${col}:`, modelReadyFeatures);
                    return updated;
                  });
                } else {
                  console.log(`[runAutoMonotonicBinning] No model_ready features found after binning ${col}`);
                }
                break; // Exit retry loop
              }
            retryCount++;
            if (retryCount < maxRetries) {
              await new Promise(resolve => setTimeout(resolve, 500));
            }
          }
        } catch (err) {
          console.error('Error fetching sorted features or model_ready status:', err);
        }
      }

      // Show success message with details
      const message = `Auto-binning completed for ${col}: ${data.num_merges} merges performed, ` +
        `${data.num_bins_original} → ${data.num_bins_final} bins, ` +
        `WOE trend: ${data.direction}, monotonic: ${data.is_monotonic ? 'Yes' : 'No'}`;

      if (!silent) {
        showNotification(message);
      }
      return true;

    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error('Auto-binning error:', err);
      onError?.(message);
      if (!silent) {
        showNotification(`Error in auto-binning: ${message}`);
        alert('Error running auto-monotonic binning');
      }
      return false;
    }
  };


  // Function to fetch sorted features and update selectedColumns order
  const fetchAndSortFeatures = async () => {
    if (!recordId) return;
    
    try {
      const data = await authGet(`/api/dataset/${recordId}/features-sorted`);
      const sortedFeatureNames = data.sorted_feature_names || [];
      
      if (sortedFeatureNames.length > 0) {
        // Reorder selectedColumns to match the sorted order
        // Keep existing selectedColumns but reorder them
        const currentSelectedSet = new Set(selectedColumns);
        const sortedSelected = sortedFeatureNames.filter((name: string) => currentSelectedSet.has(name));
        const unsortedSelected = selectedColumns.filter((name: string) => !sortedFeatureNames.includes(name));
        
        // Combine: sorted selected first, then unsorted selected
        const reorderedColumns = [...sortedSelected, ...unsortedSelected];
        setSelectedColumns(reorderedColumns);
      }
    } catch (err) {
      console.error('Error fetching sorted features:', err);
    }
  };

  // Function to sync model_ready checkboxes from database
  const syncModelReadyCheckboxes = async () => {
    if (!recordId) return;
    
    try {
      const featureList = await authGet(`/api/dataset/${recordId}/features`);
      if (Array.isArray(featureList)) {
          const modelReadyFeatures = featureList
            .filter((feature: any) => feature?.model_ready)
            .map((feature: any) => String(feature.name).trim())
            .filter(Boolean);
          
          // Replace selectedForModeling with exact model_ready set to mirror database
          setSelectedForModeling(() => {
            const unique = Array.from(new Set(modelReadyFeatures));
            console.log(`[syncModelReadyCheckboxes] Updated checkbox state to ${unique.length} model_ready features:`, unique);
            return unique;
          });
        } else {
          setSelectedForModeling([]);
          console.log('[syncModelReadyCheckboxes] Feature response not array; cleared selections');
        }
    } catch (err) {
      console.error('Error syncing model_ready checkboxes:', err);
    }
  };

  // Function to mark all monotonic features as model_ready
  const markMonotonicAsModelReady = async () => {
    if (!recordId) return;
    
    try {
      const data = await authPost(`/api/dataset/${recordId}/mark-monotonic-as-model-ready`, {});
      
      if (data.success) {
        console.log(`[markMonotonicAsModelReady] Successfully marked ${data.count} monotonic features as model_ready:`, data.features);
        if (data.count === 0) {
          console.warn(`[markMonotonicAsModelReady] No monotonic features found to mark as model_ready`);
        }
      } else {
        console.error(`[markMonotonicAsModelReady] Failed:`, data.error || data.message);
      }
    } catch (err) {
      console.error('[markMonotonicAsModelReady] Error marking monotonic features as model_ready:', err);
    }
  };

  const runAllAutoMonotonicFineBinning = async () => {
    if (!targetVariable) {
      showNotification('Please select a target variable first');
      return;
    }

    const columnsToProcess = selectedColumns.filter(col => col !== targetVariable);
    
    if (columnsToProcess.length === 0) {
      showNotification('No columns to process');
      return;
    }

    // Set loading state to hide feature boxes and show loading circle
    setIsLoadingAllAutoMonotonic(true);
    
    let successCount = 0;
    let errorCount = 0;
    
    try {
      for (const col of columnsToProcess) {
        try {
          const success = await runAutoMonotonicBinning(col, { silent: true });
          if (success) {
            successCount++;
          } else {
            errorCount++;
          }
        } catch (err) {
          console.error(`Error processing ${col}:`, err);
          errorCount++;
        }
      }
      
      // After all autobinning is complete, fetch sorted features, mark monotonic as model_ready, and sync checkboxes
      console.log('[runAllAutoMonotonicFineBinning] Starting post-processing: marking monotonic features and syncing checkboxes...');
      await fetchAndSortFeatures();
      
      // Small delay to ensure all database writes from individual binning operations are complete
      await new Promise(resolve => setTimeout(resolve, 500));
      
      console.log('[runAllAutoMonotonicFineBinning] Marking all monotonic features as model_ready...');
      await markMonotonicAsModelReady();
      
      // Small delay to ensure database update is complete before syncing
      await new Promise(resolve => setTimeout(resolve, 300));
      
      console.log('[runAllAutoMonotonicFineBinning] Syncing model_ready checkboxes...');
      await syncModelReadyCheckboxes();
      console.log('[runAllAutoMonotonicFineBinning] Post-processing complete');
      
      showNotification(
        `All Auto Monotonic Fine Binning completed: ${successCount} successful, ${errorCount} errors`
      );
    } finally {
      // Reset loading state to show updated feature boxes
      setIsLoadingAllAutoMonotonic(false);
    }
  };

  const fetchAllAutoBinningData = async () => {
    // Prevent concurrent loads
    if (isLoadingAutoBinning.current) return;
    isLoadingAutoBinning.current = true;

    try {
      if (!targetVariable) {
        isLoadingAutoBinning.current = false;
        return;
      }

      // Simply ensure WOE/IV data is loaded for all selected columns
      const columnsToProcess = selectedColumns.filter(col => {
        const existing = woeIvResults[col];
        return !existing || !Array.isArray(existing.stats) || existing.stats.length === 0;
      });

      if (columnsToProcess.length === 0) {
        await new Promise(resolve => setTimeout(resolve, 500));
        isLoadingAutoBinning.current = false;
        return;
      }

      // Fetch WOE/IV for all missing columns
      // Process columns sequentially
      for (let i = 0; i < columnsToProcess.length; i++) {
        const col = columnsToProcess[i];
        try {
          const woeData = await fetchWoeIv(col, undefined, false);
          if (woeData && woeData[col]) {
            setWoeReadyColumns((prev) => new Set(prev).add(col));
          }
        } catch (e) {
          console.error(`Error fetching WOE/IV for ${col}:`, e);
        }
      }

      await new Promise(resolve => setTimeout(resolve, 500));

    } finally {
      isLoadingAutoBinning.current = false;
    }
  };


  const handleConfigureManually = async (col: string) => {
    setBinningMode('manual');
    // Load the column data if not already loaded or if it's a different column
    if (col !== activeColumn || !fineBinResults[col] || fineBinResults[col].length === 0) {
      await handleColumnClick(col);
    } else {
      setActiveColumn(col);
    }
  };

  const handleSwitchToAutoBinning = async () => {
    setBinningMode('auto');
    setIsLoadingCoarseBins(true);
    
    try {
      if (!targetVariable) {
        setIsLoadingCoarseBins(false);
        return;
      }

      // Get columns that need coarse bins calculated
      const columnsNeedingCoarseBins = selectedColumns.filter(col => {
        const hasCoarseBins = Array.isArray(coarseBinResults[col]) && coarseBinResults[col].length > 0;
        return !hasCoarseBins && col !== targetVariable;
      });

      if (columnsNeedingCoarseBins.length > 0) {
        // Fetch coarse bins for all columns that need them
        const discreteCols = columnsNeedingCoarseBins.filter(col => 
          (discreteColumns || []).includes(col)
        );
        const continuousCols = columnsNeedingCoarseBins.filter(col => 
          (continuousColumns || []).includes(col)
        );

        if (discreteCols.length > 0 || continuousCols.length > 0) {
          const data = await authPost('/api/univariate-analysis', {
              discrete: discreteCols,
              continuous: continuousCols,
              target: targetVariable,
              record_id: recordId,
          });
          
          // Update coarse bin results for all columns
          const updatedCoarse: Record<string, NormalizedBin[]> = { ...coarseBinResults };
          const updatedUnivariate: Record<string, any> = { ...univariateResults };
          
          columnsNeedingCoarseBins.forEach((col) => {
            const coarseStats = normalizeBinArray(data[col]?.stats || data[col] || []);
            if (coarseStats.length > 0) {
              updatedCoarse[col] = coarseStats;
              updatedUnivariate[col] = { ...(data[col] || {}), stats: coarseStats };
            }
          });

          setCoarseBinResults(updatedCoarse);
          setUnivariateResults(updatedUnivariate);
        }
      }

      // Now fetch WOE/IV data for all columns
      await fetchAllAutoBinningData();
    } catch (err) {
      console.error('Error loading coarse bins for auto mode:', err);
    } finally {
      setIsLoadingCoarseBins(false);
    }
  };

  type PersistStateOverrides = {
    univariateResults?: Record<string, any>;
    fineBinResults?: Record<string, any[]>;
    crosstabResults?: Record<string, any[]>;
    woeIvResults?: Record<string, any>;
    selectedColumns?: string[];
    dashboardSelectedColumns?: string[];
  };

  const persistFineBinColumn = async (
    col: string,
    merges: Record<string, any[]>,
    overrides: PersistStateOverrides = {}
  ): Promise<number | undefined> => {
    let current = recordId;
    try {
      const payloadSelectedColumns = overrides.selectedColumns ?? selectedColumns ?? [];
      const payloadDashboard = overrides.dashboardSelectedColumns ?? selectedForModeling ?? [];

      const up = await authPost('/api/upsert-single-record', {
          dataset_path: datasetPath || undefined,
          discrete_columns: discreteColumns || [],
          continuous_columns: continuousColumns || [],
          selected_columns: payloadSelectedColumns,
          dashboard_selected_columns: payloadDashboard,
          target_variable: targetVariable || '',
          record_id: recordId,
      });
      if (!up.error && typeof up.id !== 'undefined') {
        current = up.id;
        setRecordId(up.id);
      }
      if (current) {
        await authPost('/api/finebin-details', { record_id: current, column_name: col, bin_merges: merges });
      }
    } catch (e) {

    }
    return current;
  };
  const persistDashboardSelectedColumns = async (
    newSelection: string[],
    forceSync = false
  ): Promise<number | undefined> => {
    const performPersist = async () => {
      const data = await authPost('/api/upsert-single-record', {
          dataset_path: datasetPath || undefined,
          discrete_columns: discreteColumns || [],
          continuous_columns: continuousColumns || [],
          selected_columns: selectedColumns,
          dashboard_selected_columns: newSelection,
          target_variable: targetVariable || '',
          record_id: recordId || undefined,
      });
      if (!data.error && data.id) {
        setRecordId(data.id);
        return data.id as number;
      }
      return recordId || undefined;
    };

    if (forceSync) {
      try {
        return await performPersist();
      } catch (error) {
        console.error('Failed to persist selected columns:', error);
        return recordId || undefined;
      }
    }

    setTimeout(() => {
      performPersist().catch((error) => {
        console.error('Failed to persist selected columns:', error);
      });
    }, 0);

    return recordId || undefined;
  };

  const queueModelingPersist = async (
    col: string,
    shouldSelect: boolean,
    newSelection: string[]
  ): Promise<number | undefined> => {
    let datasetId = recordId;
    if (!datasetId) {
      datasetId = await persistDashboardSelectedColumns(newSelection, true);
    } else {
      persistDashboardSelectedColumns(newSelection);
    }
    if (!datasetId) return undefined;
    try {
      await authPost('/api/update-feature-modeling', {
          feature_name: col,
          record_id: datasetId,
          is_selected: shouldSelect,
      });
    } catch (err) {
      console.error('Failed to update feature modeling:', err);
    }
    return datasetId;
  };

  const queueFinalPersist = async (
    col: string,
    shouldSelect: boolean,
    newSelection: string[],
    datasetIdOverride?: number
  ) => {
    let datasetId = datasetIdOverride ?? recordId;
    if (!datasetId) {
      datasetId = await persistDashboardSelectedColumns(newSelection, true);
    }
    if (!datasetId) return;
    try {
      await authPost('/api/update-feature-final-selected', {
          feature_name: col,
          record_id: datasetId,
          is_selected: shouldSelect,
      });
    } catch (err) {
      console.error('Failed to update feature final_selected:', err);
    }
  };

  const toggleSelectedForModeling = (col: string) => {
    // This is for Column Selection & Binning step (step 1) - updates model_ready
    setSelectedForModeling((prev) => {
      const isCurrentlySelected = prev.includes(col);
      const newSelection = isCurrentlySelected
        ? prev.filter((c) => c !== col)
        : [...prev, col];

      // Update UI immediately (optimistic update)
      showNotification(`${col} ${isCurrentlySelected ? 'deselected' : 'selected'} for modeling.`);

      queueModelingPersist(col, !isCurrentlySelected, newSelection).catch(() => { });
      return newSelection;
    });
  };

  const toggleSelectedForFinalModeling = (col: string) => {
    // This is for Model Training step (step 3) - updates final_selected only
    // Does NOT affect selectedForModeling (model_ready) to keep features visible in binning section
    setSelectedForFinalModeling((prev) => {
      // Determine current selection state: if prev is empty, fall back to selectedForModeling
      // This matches the checkbox logic: (selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling).includes(variable)
      const effectiveSelection = prev.length > 0 ? prev : selectedForModeling;
      const isCurrentlySelected = effectiveSelection.includes(col);
      
      // Build new selection based on current state
      let newSelection: string[];
      if (prev.length === 0) {
        // Initializing from empty: start with all selectedForModeling, then toggle the clicked item
        if (isCurrentlySelected) {
          // Remove from selection
          newSelection = selectedForModeling.filter((c) => c !== col);
        } else {
          // Add to selection (shouldn't happen if initialized correctly, but handle it)
          newSelection = [...selectedForModeling, col];
        }
      } else {
        // Normal toggle: add or remove from existing selection
        if (isCurrentlySelected) {
          newSelection = prev.filter((c) => c !== col);
        } else {
          newSelection = [...prev, col];
        }
      }

      // DO NOT update selectedForModeling - it should remain unchanged
      // selectedForModeling represents model_ready features and should stay visible in binning section

      // Cache the new selection
      saveCachedFinalSelected(newSelection);

      // Update UI immediately (optimistic update)
      showNotification(`${col} ${isCurrentlySelected ? 'deselected' : 'selected'} for final model training.`);

      queueModelingPersist(col, !isCurrentlySelected, newSelection)
        .then((datasetId) =>
          queueFinalPersist(col, !isCurrentlySelected, newSelection, datasetId)
        )
        .catch(() => {
          queueFinalPersist(col, !isCurrentlySelected, newSelection);
        });

      return newSelection;
    });
  };

  // Toggle selection for chart export
  const toggleSelectedForExport = (col: string) => {
    setSelectedForExport((prev) => {
      if (prev.includes(col)) {
        return prev.filter((c) => c !== col);
      } else {
        return [...prev, col];
      }
    });
  };

  // Select all charts for export
  const selectAllForExport = () => {
    const columnsToSelect = selectedColumns.filter(col => col !== targetVariable);
    setSelectedForExport(columnsToSelect);
  };

  // Deselect all charts for export
  const deselectAllForExport = () => {
    setSelectedForExport([]);
  };

  // Select only model-ready columns (auto-selected after auto monotonic fine binning) for export
  const selectModelReadyForExport = () => {
    const modelReadyColumns = selectedForModeling.filter(col => col !== targetVariable && selectedColumns.includes(col));
    setSelectedForExport(modelReadyColumns);
  };

  // Export selected charts as PDF
  const exportSelectedCharts = async (format: 'pdf' | 'png' = 'pdf') => {
    if (selectedForExport.length === 0) {
      showNotification('Please select at least one chart to export.');
      return;
    }

    setIsExportingCharts(true);
    showNotification(`Exporting ${selectedForExport.length} chart(s) as ${format.toUpperCase()}...`);

    try {
      const chartElements: HTMLDivElement[] = [];
      
      // Collect all selected chart elements
      for (const col of selectedForExport) {
        const element = chartCardRefs.current[col];
        if (element) {
          chartElements.push(element);
        }
      }

      if (chartElements.length === 0) {
        showNotification('No chart elements found to export.');
        setIsExportingCharts(false);
        return;
      }

      // Helper function to get IV strength classification
      const getIVStrength = (iv: number): { label: string; color: number[] } => {
        if (iv < 0.02) return { label: 'Not Predictive', color: [200, 80, 80] };
        if (iv < 0.1) return { label: 'Weak Predictor', color: [230, 150, 50] };
        if (iv < 0.3) return { label: 'Medium Predictor', color: [100, 180, 100] };
        if (iv < 0.5) return { label: 'Strong Predictor', color: [50, 150, 200] };
        return { label: 'Very Strong Predictor', color: [130, 80, 200] };
      };

      // Helper function to check monotonicity
      const checkMonotonicity = (woeValues: number[]): { isMonotonic: boolean; direction: string } => {
        if (woeValues.length < 2) return { isMonotonic: true, direction: 'N/A' };
        let increasing = true;
        let decreasing = true;
        for (let i = 1; i < woeValues.length; i++) {
          if (woeValues[i] < woeValues[i - 1]) increasing = false;
          if (woeValues[i] > woeValues[i - 1]) decreasing = false;
        }
        if (increasing) return { isMonotonic: true, direction: 'Increasing' };
        if (decreasing) return { isMonotonic: true, direction: 'Decreasing' };
        return { isMonotonic: false, direction: 'Non-Monotonic' };
      };

      if (format === 'pdf') {
        // Create PDF document in landscape for better chart display
        const pdf = new jsPDF('p', 'mm', 'a4');
        const pageWidth = pdf.internal.pageSize.getWidth();
        const pageHeight = pdf.internal.pageSize.getHeight();
        const margin = 15;
        const usableWidth = pageWidth - margin * 2;
        
        // Title Page
        pdf.setFillColor(26, 26, 46);
        pdf.rect(0, 0, pageWidth, 60, 'F');
        
        pdf.setFontSize(24);
        pdf.setTextColor(255, 255, 255);
        pdf.text('WOE Analysis Report', margin, 30);
        
        pdf.setFontSize(12);
        pdf.setTextColor(200, 200, 200);
        pdf.text('Auto Monotonic Fine Binning Results', margin, 40);
        
        pdf.setFontSize(10);
        pdf.setTextColor(100, 100, 100);
        pdf.text(`Generated: ${new Date().toLocaleDateString()} at ${new Date().toLocaleTimeString()}`, margin, 75);
        pdf.text(`Total Features Exported: ${selectedForExport.length}`, margin, 82);
        pdf.text(`Target Variable: ${targetVariable || 'N/A'}`, margin, 89);
        
        // Summary Section
        pdf.setFontSize(14);
        pdf.setTextColor(40, 40, 40);
        pdf.text('Summary Statistics', margin, 105);
        
        pdf.setDrawColor(200, 200, 200);
        pdf.line(margin, 108, pageWidth - margin, 108);
        
        let summaryY = 118;
        const continuousCount = selectedForExport.filter(col => (continuousColumns || []).includes(col)).length;
        const discreteCount = selectedForExport.length - continuousCount;
        
        pdf.setFontSize(10);
        pdf.setTextColor(80, 80, 80);
        pdf.text(`• Continuous Variables: ${continuousCount}`, margin + 5, summaryY);
        summaryY += 7;
        pdf.text(`• Discrete Variables: ${discreteCount}`, margin + 5, summaryY);
        summaryY += 12;
        
        // Feature Overview Table Header
        pdf.setFontSize(11);
        pdf.setTextColor(40, 40, 40);
        pdf.text('Feature Overview:', margin, summaryY);
        summaryY += 8;
        
        // Table headers
        pdf.setFillColor(240, 240, 240);
        pdf.rect(margin, summaryY - 4, usableWidth, 8, 'F');
        pdf.setFontSize(9);
        pdf.setTextColor(60, 60, 60);
        pdf.text('Feature', margin + 2, summaryY);
        pdf.text('Type', margin + 55, summaryY);
        pdf.text('Bins', margin + 85, summaryY);
        pdf.text('Total IV', margin + 105, summaryY);
        pdf.text('IV Strength', margin + 130, summaryY);
        pdf.text('Monotonic', margin + 165, summaryY);
        summaryY += 8;
        
        // Table rows
        for (const col of selectedForExport) {
          const woeData = woeIvResults[col];
          const woeStats: NormalizedBin[] = woeData?.stats ?? [];
          const totalIV = woeStats.reduce((sum: number, s: NormalizedBin) => sum + (Number(s.IV) || 0), 0);
          const isContinuous = (continuousColumns || []).includes(col);
          const woeValues = woeStats.map(s => Number(s.WOE ?? 0));
          const monotonicity = checkMonotonicity(woeValues);
          const ivStrength = getIVStrength(totalIV);
          
          if (summaryY > pageHeight - 30) {
            pdf.addPage();
            summaryY = 20;
          }
          
          pdf.setFontSize(8);
          pdf.setTextColor(80, 80, 80);
          pdf.text(col.length > 20 ? col.substring(0, 18) + '...' : col, margin + 2, summaryY);
          pdf.text(isContinuous ? 'Continuous' : 'Discrete', margin + 55, summaryY);
          pdf.text(String(woeStats.length), margin + 85, summaryY);
          pdf.text(totalIV.toFixed(4), margin + 105, summaryY);
          
          pdf.setTextColor(ivStrength.color[0], ivStrength.color[1], ivStrength.color[2]);
          pdf.text(ivStrength.label, margin + 130, summaryY);
          
          pdf.setTextColor(monotonicity.isMonotonic ? 50 : 180, monotonicity.isMonotonic ? 150 : 80, monotonicity.isMonotonic ? 50 : 80);
          pdf.text(monotonicity.direction, margin + 165, summaryY);
          
          summaryY += 6;
        }
        
        // Individual Feature Pages
        for (let i = 0; i < chartElements.length; i++) {
          pdf.addPage();
          const element = chartElements[i];
          const colName = selectedForExport[i];
          const woeData = woeIvResults[colName];
          const woeStats: NormalizedBin[] = woeData?.stats ?? [];
          const isContinuous = (continuousColumns || []).includes(colName);
          
          // Calculate statistics
          const totalIV = woeStats.reduce((sum: number, s: NormalizedBin) => sum + (Number(s.IV) || 0), 0);
          const totalGood = woeStats.reduce((sum: number, s: NormalizedBin) => sum + (Number(s.Good) || 0), 0);
          const totalBad = woeStats.reduce((sum: number, s: NormalizedBin) => sum + (Number(s.Bad) || 0), 0);
          const totalCount = totalGood + totalBad;
          const overallBadRate = totalCount > 0 ? (totalBad / totalCount * 100) : 0;
          const woeValues = woeStats.map(s => Number(s.WOE ?? 0));
          const monotonicity = checkMonotonicity(woeValues);
          const ivStrength = getIVStrength(totalIV);
          
          // Feature Header
          pdf.setFillColor(26, 26, 46);
          pdf.rect(0, 0, pageWidth, 25, 'F');
          
          pdf.setFontSize(16);
          pdf.setTextColor(255, 255, 255);
          pdf.text(`${i + 1}. ${colName}`, margin, 16);
          
          pdf.setFontSize(10);
          pdf.setTextColor(150, 150, 150);
          pdf.text(isContinuous ? 'Continuous Variable' : 'Discrete Variable', pageWidth - margin - 35, 16);
          
          let yPos = 35;
          
          // Key Metrics Cards
          pdf.setFillColor(245, 245, 250);
          pdf.roundedRect(margin, yPos, 40, 22, 3, 3, 'F');
          pdf.roundedRect(margin + 45, yPos, 40, 22, 3, 3, 'F');
          pdf.roundedRect(margin + 90, yPos, 40, 22, 3, 3, 'F');
          pdf.roundedRect(margin + 135, yPos, 50, 22, 3, 3, 'F');
          
          pdf.setFontSize(8);
          pdf.setTextColor(100, 100, 100);
          pdf.text('Total IV', margin + 5, yPos + 8);
          pdf.text('Number of Bins', margin + 50, yPos + 8);
          pdf.text('Bad Rate', margin + 95, yPos + 8);
          pdf.text('Monotonicity', margin + 140, yPos + 8);
          
          pdf.setFontSize(12);
          pdf.setTextColor(ivStrength.color[0], ivStrength.color[1], ivStrength.color[2]);
          pdf.text(totalIV.toFixed(4), margin + 5, yPos + 18);
          
          pdf.setTextColor(60, 60, 60);
          pdf.text(String(woeStats.length), margin + 50, yPos + 18);
          pdf.text(`${overallBadRate.toFixed(2)}%`, margin + 95, yPos + 18);
          
          pdf.setTextColor(monotonicity.isMonotonic ? 50 : 180, monotonicity.isMonotonic ? 150 : 80, monotonicity.isMonotonic ? 50 : 80);
          pdf.text(monotonicity.direction, margin + 140, yPos + 18);
          
          yPos += 30;
          
          // IV Strength indicator
          pdf.setFontSize(9);
          pdf.setTextColor(ivStrength.color[0], ivStrength.color[1], ivStrength.color[2]);
          pdf.text(`IV Classification: ${ivStrength.label}`, margin, yPos);
          yPos += 10;
          
          // Chart Section
          pdf.setFontSize(11);
          pdf.setTextColor(40, 40, 40);
          pdf.text('WOE Trend Chart', margin, yPos);
          yPos += 3;
          
          try {
            const originalBackground = element.style.background;
            element.style.background = '#1a1a2e';
            
            const canvas = await html2canvas(element, {
              backgroundColor: '#1a1a2e',
              scale: 2.5, // Higher quality
              logging: false,
              useCORS: true,
              allowTaint: true,
            });
            
            element.style.background = originalBackground;
            
            const imgData = canvas.toDataURL('image/png');
            
            // Calculate balanced dimensions - maintain aspect ratio
            const aspectRatio = canvas.width / canvas.height;
            const maxChartWidth = usableWidth * 0.9;
            const maxChartHeight = 55;
            
            let chartWidth = maxChartWidth;
            let chartHeight = chartWidth / aspectRatio;
            
            if (chartHeight > maxChartHeight) {
              chartHeight = maxChartHeight;
              chartWidth = chartHeight * aspectRatio;
            }
            
            // Center the chart
            const chartX = margin + (usableWidth - chartWidth) / 2;
            
            pdf.addImage(imgData, 'PNG', chartX, yPos, chartWidth, chartHeight);
            yPos += chartHeight + 8;
          } catch (err) {
            console.error(`Error capturing chart for ${colName}:`, err);
            yPos += 60;
          }
          
          // Detailed Binning Table
          pdf.setFontSize(11);
          pdf.setTextColor(40, 40, 40);
          pdf.text('Binning Details', margin, yPos);
          yPos += 6;
          
          // Table header
          pdf.setFillColor(50, 50, 70);
          pdf.rect(margin, yPos - 3, usableWidth, 7, 'F');
          pdf.setFontSize(7);
          pdf.setTextColor(255, 255, 255);
          
          const colWidths = [30, 20, 20, 22, 22, 20, 22, 24];
          let xPos = margin + 2;
          const headers = ['Bin', 'Good', 'Bad', 'Total', 'Bad Rate%', 'Freq%', 'WOE', 'IV'];
          headers.forEach((header, idx) => {
            pdf.text(header, xPos, yPos + 2);
            xPos += colWidths[idx];
          });
          yPos += 7;
          
          // Table rows
          pdf.setFontSize(7);
          woeStats.forEach((bin, idx) => {
            const binLabel = getBinLabelValue(bin, idx);
            const good = Number(bin.Good ?? 0);
            const bad = Number(bin.Bad ?? 0);
            const total = Number(bin.Total ?? good + bad);
            const badRate = total > 0 ? (bad / total * 100) : 0;
            const freqPct = totalCount > 0 ? (total / totalCount * 100) : 0;
            const woe = Number(bin.WOE ?? 0);
            const iv = Number(bin.IV ?? 0);
            
            // Alternating row colors
            if (idx % 2 === 0) {
              pdf.setFillColor(248, 248, 252);
              pdf.rect(margin, yPos - 3, usableWidth, 6, 'F');
            }
            
            pdf.setTextColor(60, 60, 60);
            xPos = margin + 2;
            
            const displayLabel = binLabel.length > 12 ? binLabel.substring(0, 10) + '..' : binLabel;
            pdf.text(displayLabel, xPos, yPos);
            xPos += colWidths[0];
            pdf.text(String(good), xPos, yPos);
            xPos += colWidths[1];
            pdf.text(String(bad), xPos, yPos);
            xPos += colWidths[2];
            pdf.text(String(total), xPos, yPos);
            xPos += colWidths[3];
            
            // Color code bad rate
            pdf.setTextColor(badRate > overallBadRate ? 200 : 80, badRate > overallBadRate ? 80 : 150, 80);
            pdf.text(badRate.toFixed(2), xPos, yPos);
            xPos += colWidths[4];
            
            pdf.setTextColor(60, 60, 60);
            pdf.text(freqPct.toFixed(2), xPos, yPos);
            xPos += colWidths[5];
            
            // Color code WOE
            pdf.setTextColor(woe >= 0 ? 50 : 180, woe >= 0 ? 150 : 80, 50);
            pdf.text(woe.toFixed(4), xPos, yPos);
            xPos += colWidths[6];
            
            pdf.setTextColor(60, 60, 60);
            pdf.text(iv.toFixed(4), xPos, yPos);
            
            yPos += 6;
          });
          
          // Totals row
          pdf.setFillColor(230, 230, 240);
          pdf.rect(margin, yPos - 3, usableWidth, 7, 'F');
          pdf.setFontSize(7);
          pdf.setTextColor(40, 40, 40);
          xPos = margin + 2;
          pdf.text('TOTAL', xPos, yPos);
          xPos += colWidths[0];
          pdf.text(String(totalGood), xPos, yPos);
          xPos += colWidths[1];
          pdf.text(String(totalBad), xPos, yPos);
          xPos += colWidths[2];
          pdf.text(String(totalCount), xPos, yPos);
          xPos += colWidths[3];
          pdf.text(overallBadRate.toFixed(2), xPos, yPos);
          xPos += colWidths[4];
          pdf.text('100.00', xPos, yPos);
          xPos += colWidths[5];
          pdf.text('-', xPos, yPos);
          xPos += colWidths[6];
          pdf.setTextColor(ivStrength.color[0], ivStrength.color[1], ivStrength.color[2]);
          pdf.text(totalIV.toFixed(4), xPos, yPos);
          
          yPos += 12;
          
          // Insights Section
          pdf.setFontSize(10);
          pdf.setTextColor(40, 40, 40);
          pdf.text('Key Insights', margin, yPos);
          yPos += 5;
          
          pdf.setFontSize(8);
          pdf.setTextColor(80, 80, 80);
          
          // Generate insights
          const insights: string[] = [];
          
          // IV insight
          insights.push(`• Information Value (${totalIV.toFixed(4)}) indicates this is a ${ivStrength.label.toLowerCase()}.`);
          
          // Monotonicity insight
          if (monotonicity.isMonotonic) {
            insights.push(`• WOE trend is ${monotonicity.direction.toLowerCase()}, showing good risk differentiation.`);
          } else {
            insights.push(`• WOE trend is non-monotonic - consider reviewing bin boundaries for better risk ordering.`);
          }
          
          // Find highest and lowest WOE bins
          if (woeStats.length > 0) {
            const sortedByWOE = [...woeStats].sort((a, b) => (Number(b.WOE) || 0) - (Number(a.WOE) || 0));
            const highestWOE = sortedByWOE[0];
            const lowestWOE = sortedByWOE[sortedByWOE.length - 1];
            insights.push(`• Lowest risk bin: "${getBinLabelValue(highestWOE)}" (WOE: ${Number(highestWOE.WOE || 0).toFixed(4)})`);
            insights.push(`• Highest risk bin: "${getBinLabelValue(lowestWOE)}" (WOE: ${Number(lowestWOE.WOE || 0).toFixed(4)})`);
          }
          
          // Bin distribution insight
          const maxFreqBin = woeStats.reduce((max, bin) => {
            const freq = Number(bin.Total ?? 0);
            const maxFreq = Number(max.Total ?? 0);
            return freq > maxFreq ? bin : max;
          }, woeStats[0]);
          if (maxFreqBin) {
            const maxFreqPct = totalCount > 0 ? (Number(maxFreqBin.Total ?? 0) / totalCount * 100) : 0;
            insights.push(`• Most populated bin: "${getBinLabelValue(maxFreqBin)}" (${maxFreqPct.toFixed(1)}% of records)`);
          }
          
          insights.forEach(insight => {
            pdf.text(insight, margin + 3, yPos);
            yPos += 5;
          });
        }

        pdf.save(`woe-analysis-report-${new Date().toISOString().split('T')[0]}.pdf`);
        showNotification(`Successfully exported ${selectedForExport.length} chart(s) as PDF!`);
      } else {
        // Export as individual PNG files
        for (let i = 0; i < chartElements.length; i++) {
          const element = chartElements[i];
          const colName = selectedForExport[i];
          
          try {
            const originalBackground = element.style.background;
            element.style.background = '#1a1a2e';
            
            const canvas = await html2canvas(element, {
              backgroundColor: '#1a1a2e',
              scale: 2,
              logging: false,
              useCORS: true,
              allowTaint: true,
            });
            
            element.style.background = originalBackground;
            
            // Create download link
            const link = document.createElement('a');
            link.download = `woe-chart-${colName}-${new Date().toISOString().split('T')[0]}.png`;
            link.href = canvas.toDataURL('image/png');
            link.click();
            
            // Small delay between downloads to prevent browser blocking
            await new Promise(resolve => setTimeout(resolve, 200));
          } catch (err) {
            console.error(`Error capturing chart for ${colName}:`, err);
          }
        }
        showNotification(`Successfully exported ${selectedForExport.length} chart(s) as PNG!`);
      }
    } catch (error) {
      console.error('Export error:', error);
      showNotification('Error exporting charts. Please try again.');
    } finally {
      setIsExportingCharts(false);
    }
  };

  const prevSelectedColumnsRef = useRef<string[]>(selectedColumns);

  useEffect(() => {
    const prevSelected = prevSelectedColumnsRef.current || [];
    const removedColumns = prevSelected.filter((col) => !selectedColumns.includes(col));

    if (removedColumns.length > 0) {
      setWoeIvResults((prev) => {
        const next = { ...prev };
        removedColumns.forEach((col) => delete next[col]);
        return next;
      });
      setWoeReadyColumns((prev) => {
        const next = new Set(prev);
        removedColumns.forEach((col) => next.delete(col));
        return next;
      });
      setSelectedForModeling((prev) => prev.filter((col) => !removedColumns.includes(col)));
      // Notification removed per user request
    }

    prevSelectedColumnsRef.current = selectedColumns;
  }, [selectedColumns]);

  useEffect(() => {
    woeIvResultsRef.current = woeIvResults;
  }, [woeIvResults]);
  const fetchWoeIv = async (
    col: string,
    merges?: Record<string, any[]>,
    addToModeling: boolean = true,
    options?: { recordIdOverride?: number },
  ): Promise<Record<string, any> | null> => {
    try {
      const varType = (continuousColumns || []).includes(col) ? 'continuous' : 'discrete';
      const resolvedRecordId = options?.recordIdOverride ?? recordId;
      const body: any = {
        variables: [col],
        target: targetVariable,
        type: varType  // Add this!
      };
      if (resolvedRecordId) body.record_id = resolvedRecordId;
      if (merges && Object.keys(merges).length > 0) {
        body.bin_merges = merges;
      }


      const data = await authPost('/api/woe-iv', body);


      if (!data.error && data[col]) {
        const normalizedEntry: { iv?: number; stats: NormalizedBin[] } = {
          iv: typeof data[col].iv === 'number' ? data[col].iv : undefined,
          stats: normalizeBinArray(data[col]?.stats || data[col]?.bins || []),
        };
        const mergedResults = { ...woeIvResultsRef.current, [col]: normalizedEntry };
        woeIvResultsRef.current = mergedResults;
        setWoeIvResults(mergedResults);
        setWoeReadyColumns((prev) => {
          const updated = new Set(prev);
          updated.add(col);
          return updated;
        });
        if (addToModeling) {
          setSelectedForModeling((prev) => [...new Set([...prev, col])]);
        }
        return mergedResults;
      } else {

      }
    } catch (e) {

    }
    return null;
  };

  // Show woeIvResults for the active column whenever it changes (helps debugging)
  useEffect(() => {
    if (!activeColumn) return;
    try {
      const w = woeIvResults[activeColumn];
      if (w) {
        try {
        } catch (e) {
          // ignore stringify errors
        }
      } else {
      }
    } catch (e) {

    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeColumn, woeIvResults]);
  const canGoNext = () => {
    switch (currentStep) {
      case 0: // Classification - need at least one column (discrete or continuous) and target variable
        return (discreteColumns.length > 0 || continuousColumns.length > 0) && targetVariable !== '';
      case 1: // Data Preprocessing - preprocess_selection is automatically set to true after calculations complete
        return preprocessSelectionSaved;
      case 2: // Binning - need at least one WOE-ready column
        return woeReadyColumns.size > 0;
      case 3: // Models - need at least one WOE-ready column
        return woeReadyColumns.size > 0;
      case 4: // Score Card - last step, no next
        return false;
      default:
        return false;
    }
  };
  // CRITICAL: Clear all state when recordId changes to ensure complete isolation between records
  // This runs BEFORE loadSavedData to prevent old data from persisting
  const prevRecordIdRef = useRef<number | undefined>(recordId);
  useEffect(() => {
    // If recordId changed (including from undefined to a value, or from one record to another)
    if (prevRecordIdRef.current !== recordId) {
      console.log(`[SelectedColumnsPage] 🔄 Record ID changed: ${prevRecordIdRef.current} → ${recordId}`);
      
      // Clear all record-specific state when switching records
      // This ensures old data from previous record doesn't persist
      console.log('[SelectedColumnsPage] 🧹 Clearing all state before loading new record');
      setTargetVariable('');
      setDiscreteColumns([]);
      setContinuousColumns([]);
      setSelectedColumns([]);
      setSelectedForUnivariate([]);
      setUnivariateResults({});
      setCoarseBinResults({});
      setFineBinResults({});
      setWoeIvResults({});
      setSelectedForModeling([]);
      setSelectedForFinalModeling([]);
      setWoeReadyColumns(new Set());
      
      // Update ref for next comparison
      prevRecordIdRef.current = recordId;
    }
  }, [recordId]);

  useEffect(() => {
    // Only fetch record when recordId changes, not in every render or loop
    if (recordId) {
      console.log(`[SelectedColumnsPage] 🔄 Loading data for record ${recordId}`);
      loadSavedData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordId]);

  // Load selected columns from database when on Data Preprocessing step
  // Check preprocess_selection flag - if true, load from DB; if false, no polling needed
  useEffect(() => {
    const loadPreprocessingSelectedColumns = async () => {
      if (currentStep === 1 && recordId) {
        try {
          // First check preprocess_selection status
          const recordData = await authGet(`/api/record/${recordId}`);
          
          let shouldLoadFromDb = false;
          if (recordData.preprocess_selection === true) {
            shouldLoadFromDb = true;
            setPreprocessSelectionSaved(true);
          }
          
          // Only load features if preprocess_selection is true
          // If false, calculations will determine selections, no need to poll
          if (shouldLoadFromDb) {
            const featuresData = await authGet(`/api/dataset/${recordId}/features`);
            // Load selected features from database (not stored in state as not used elsewhere)
            if (Array.isArray(featuresData)) {
              featuresData
                .filter((f: any) => f.selected === true)
                .map((f: any) => f.name);
            }
          }
        } catch (error) {
          console.error('Error loading preprocessing selected columns:', error);
        }
      }
    };

    // Only load once when step changes or recordId changes
    // No polling - use preprocess_selection flag to determine if DB load is needed
    loadPreprocessingSelectedColumns();
  }, [currentStep, recordId]);
  // Load model_ready checkboxes when moving to Classification section (step 0)
  useEffect(() => {
    if (currentStep === 0 && recordId) {
      authGet(`/api/dataset/${recordId}/features`)
        .then((features: any[]) => {
          const modelReadyNames = features
            .filter((f: any) => f.model_ready)
            .map((f: any) => String(f.name).trim())
            .filter(Boolean);
          if (modelReadyNames.length > 0) {
            setSelectedForModeling(modelReadyNames);
          }
        })
        .catch(err => console.error('Failed to load model_ready features:', err));
    }
  }, [currentStep, recordId]);

  // Sync model_ready to final_selected and load final_selected checkboxes when navigating to Models step (step 2)
  useEffect(() => {
    if (currentStep === 2 && recordId) {
      // First sync model_ready to final_selected
      authPost('/api/sync-model-ready-to-final-selected', {
          record_id: recordId
      }).then(async () => {
          // After syncing, load final_selected values to initialize selectedForFinalModeling
          try {
          const features = await authGet(`/api/dataset/${recordId}/features`);
            const finalSelectedNames = features
              .filter((f: any) => f.final_selected)
              .map((f: any) => String(f.name).trim())
              .filter(Boolean);
            if (finalSelectedNames.length > 0) {
              setSelectedForFinalModeling(finalSelectedNames);
              setSelectedForModeling(finalSelectedNames); // Also update selectedForModeling for compatibility
            }
          } catch (err) {
            console.error('Failed to load final_selected features:', err);
        }
      }).catch(err => console.error('Failed to sync model_ready to final_selected:', err));
    }
  }, [currentStep, recordId]);

  useEffect(() => {
    // Only trigger WOE/IV fetch when entering step 2 (Binning), 3 (Models), or 4 (Score Card), not in a loop
    if (currentStep === 2 || currentStep === 3 || currentStep === 4) {
      const cols: string[] = selectedColumns;
      const missing = cols.filter((c) => !woeIvResults[c]);
      if (missing.length > 0) {
        missing.forEach((col) => fetchWoeIv(col, undefined, false));
      }
    }
  }, [currentStep]);

  // Track if we've initialized selectedForFinalModeling for the current step 3 session
  const hasInitializedFinalModelingRef = useRef<boolean>(false);
  const lastStep3RecordIdRef = useRef<number | undefined>(undefined);

  // Load cached VIF and significance data from localStorage
  const loadCachedVIFAndSignificance = (): boolean => {
    if (!recordId) return false;
    
    try {
      const cacheKey = `vif_significance_${recordId}`;
      const cached = localStorage.getItem(cacheKey);
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed.vifData && parsed.significanceData) {
          console.log('[VIF] Loaded cached VIF and significance data');
          setVifData(parsed.vifData);
          setSignificanceData(parsed.significanceData);
          setHasLRCompleted(true);
          return true;
        }
      }
    } catch (error) {
      console.error('[VIF] Error loading cached data:', error);
    }
    return false;
  };

  // Save VIF and significance data to localStorage
  const saveCachedVIFAndSignificance = (vifMap: Record<string, number | null>, significanceMap: Record<string, { pValue: number | null; level: string }>) => {
    if (!recordId) return;
    
    try {
      const cacheKey = `vif_significance_${recordId}`;
      localStorage.setItem(cacheKey, JSON.stringify({
        vifData: vifMap,
        significanceData: significanceMap,
        timestamp: Date.now()
      }));
      console.log('[VIF] Saved VIF and significance data to cache');
    } catch (error) {
      console.error('[VIF] Error saving cached data:', error);
    }
  };

  // Track previous step before it changes
  useEffect(() => {
    // This runs AFTER the render but BEFORE the main useEffect below
    // So when currentStep changes to 3, previousStepRef.current still has the old value
    if (currentStep !== 3) {
      previousStepRef.current = currentStep;
    }
  }, [currentStep]);

  // Initialize selectedForFinalModeling and calculate VIF when entering models section
  useEffect(() => {
    if (currentStep === 3 && targetVariable && recordId && selectedForModeling.length > 0) {
      // Reset initialization flag if recordId changed or we're entering step 3 for the first time
      const isNewSession = lastStep3RecordIdRef.current !== recordId || !hasInitializedFinalModelingRef.current;
      
      if (isNewSession) {
        hasInitializedFinalModelingRef.current = false;
        lastStep3RecordIdRef.current = recordId;
      }
      
      // Load final_selected from database or cache when entering models section
      // This preserves user's previous selections (checked/unchecked state)
      const loadFinalSelected = async () => {
        // First, try to load from cache (for when coming from scorecard)
        const previousStep = previousStepRef.current;
        if (previousStep === 4) {
          // Coming from scorecard - prefer cache over database
          const cachedFinalSelected = loadCachedFinalSelected();
          if (cachedFinalSelected && cachedFinalSelected.length > 0) {
            console.log('[Models] Coming from scorecard, loaded final_selected from cache:', cachedFinalSelected);
            setSelectedForFinalModeling(cachedFinalSelected);
            hasInitializedFinalModelingRef.current = true;
            return;
          }
        }

        // Try database first
        try {
          const featureList = await authGet(`/api/dataset/${recordId}/features`);
          if (Array.isArray(featureList)) {
              const finalSelectedFeatures = featureList
                .filter((feature: any) => feature?.final_selected)
                .map((feature: any) => String(feature.name).trim())
                .filter(Boolean);
              
              if (finalSelectedFeatures.length > 0) {
                // Use final_selected from database if available
                console.log('[Models] Loaded final_selected from database:', finalSelectedFeatures);
                setSelectedForFinalModeling(finalSelectedFeatures);
                // Cache it for future use
                saveCachedFinalSelected(finalSelectedFeatures);
                hasInitializedFinalModelingRef.current = true;
                return;
              }
            }
        } catch (err) {
          console.error('[Models] Error loading final_selected from database:', err);
        }

        // If no database result, try cache
        const cachedFinalSelected = loadCachedFinalSelected();
        if (cachedFinalSelected && cachedFinalSelected.length > 0) {
          console.log('[Models] Loaded final_selected from cache:', cachedFinalSelected);
          setSelectedForFinalModeling(cachedFinalSelected);
          hasInitializedFinalModelingRef.current = true;
          return;
        }

        // Last resort: initialize with all model_ready features if not yet initialized
        if (!hasInitializedFinalModelingRef.current) {
          console.log('[Models] No final_selected in DB or cache, initializing with all model_ready features:', selectedForModeling);
          setSelectedForFinalModeling([...selectedForModeling]);
          saveCachedFinalSelected([...selectedForModeling]);
          hasInitializedFinalModelingRef.current = true;
        } else {
          // Already initialized - preserve existing state (user's current selections)
          console.log('[Models] Already initialized, preserving existing selectedForFinalModeling state');
        }
      };
      
      if (!hasInitializedFinalModelingRef.current) {
        loadFinalSelected();
      }
      
      // Only calculate VIF when coming from binning (step 2), not from scorecard (step 4)
      // previousStepRef.current contains the step BEFORE currentStep changed to 3
      const previousStep = previousStepRef.current;
      console.log('[VIF] Entering step 3, previous step was:', previousStep);
      if (previousStep === 2) {
        // Coming from binning - calculate VIF and significance
        console.log('[VIF] Coming from binning, calculating VIF for all model_ready features:', selectedForModeling);
        calculateVIF();
      } else if (previousStep === 4) {
        // Coming from scorecard - load cached VIF and significance data
        console.log('[VIF] Coming from scorecard, loading cached VIF and significance data');
        loadCachedVIFAndSignificance();
      } else {
        // First time entering or from other step - check if we have cached data
        const cachedData = loadCachedVIFAndSignificance();
        if (!cachedData) {
          // No cached data, calculate VIF
          console.log('[VIF] No cached data found, calculating VIF for all model_ready features:', selectedForModeling);
          calculateVIF();
        }
      }

      // Load cached model results when entering models section
      // This prevents recomputation when switching between models and scorecard
      // Only load if results are not already set
      if (!logisticResults) {
        const cachedLR = loadCachedModelResults('logistic');
        if (cachedLR) {
          setLogisticResults(cachedLR);
        }
      }
      if (!randomForestResults) {
        const cachedRF = loadCachedModelResults('random_forest');
        if (cachedRF) {
          setRandomForestResults(cachedRF);
        }
      }
      if (!xgboostResults) {
        const cachedXGB = loadCachedModelResults('xgboost');
        if (cachedXGB) {
          setXgboostResults(cachedXGB);
        }
      }
      if (!stackingResults) {
        const cachedStacking = loadCachedModelResults('stacking');
        if (cachedStacking) {
          setStackingResults(cachedStacking);
        }
      }
    } else if (currentStep !== 3) {
      // Reset flag when leaving step 3
      hasInitializedFinalModelingRef.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep, targetVariable, recordId, selectedForModeling]);

  const calculateVIF = async () => {
    if (!targetVariable || !recordId) {
      console.log('[VIF] Missing targetVariable or recordId');
      return;
    }
    
    // Always calculate VIF for all model_ready features (selectedForModeling)
    // This ensures VIF is available for all features shown in the sidebar
    if (selectedForModeling.length === 0) {
      console.log('[VIF] No model_ready features to calculate VIF for');
      return;
    }

    console.log('[VIF] Starting VIF calculation for all model_ready features:', selectedForModeling);
    setIsCalculatingVIF(true);
    setHasLRCompleted(false);
    try {
      const data = await authPost('/api/logistic-regression', {
          selected_variables: selectedForModeling, // Use all model_ready features
          target: targetVariable,
          woe_transformed_data: Object.fromEntries(
            Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
          ),
          record_id: recordId
      });
      console.log('[VIF] Response received:', data);
      
      // Initialize maps with all requested features (set to null initially)
      const vifMap: Record<string, number | null> = {};
      const significanceMap: Record<string, { pValue: number | null; level: string }> = {};
      
      // Initialize all features with null values
      selectedForModeling.forEach((varName: string) => {
        vifMap[varName] = null;
        significanceMap[varName] = { pValue: null, level: 'Low' };
      });
      
      // Populate VIF data from response
      if (data.success && data.vif_data) {
        data.vif_data.forEach((item: { variable: string; vif: number | null }) => {
          // Remove _WOE suffix if present
          const varName = item.variable.replace('_WOE', '');
          vifMap[varName] = item.vif;
          console.log(`[VIF] Mapped ${item.variable} -> ${varName}: ${item.vif}`);
        });
        console.log('[VIF] Final VIF map:', vifMap);
        setVifData(vifMap);
      } else {
        console.log('[VIF] No VIF data in response or request failed');
        // Still set the map with null values so UI shows something
        setVifData(vifMap);
      }

      // Extract and process significance data from p_values
      if (data.success && data.p_values) {
        data.p_values.forEach((item: { variable: string; p_value: number | null; significance: string }) => {
          // Skip Intercept
          if (item.variable === 'Intercept') return;
          
          // Remove _WOE suffix if present
          const varName = item.variable.replace('_WOE', '');
          const pValue = item.p_value;
          
          // Determine significance level: High (p < 0.01), Medium (0.01 ≤ p < 0.05), Low (p ≥ 0.05)
          let level = 'Low';
          if (pValue !== null && pValue !== undefined) {
            if (pValue < 0.01) {
              level = 'High';
            } else if (pValue < 0.05) {
              level = 'Medium';
            } else {
              level = 'Low';
            }
          }
          
          significanceMap[varName] = {
            pValue: pValue,
            level: level
          };
          console.log(`[Significance] Mapped ${item.variable} -> ${varName}: p=${pValue}, level=${level}`);
        });
        console.log('[Significance] Final significance map:', significanceMap);
        setSignificanceData(significanceMap);
        
        // Save to cache
        saveCachedVIFAndSignificance(vifMap, significanceMap);
        
        // Mark LR as completed
        setHasLRCompleted(true);
        
        await autoSelectFeaturesFromDiagnostics(vifMap, significanceMap);
      } else {
        console.log('[Significance] No p_values in response or request failed');
        // Still set the map with null values so UI shows something for all features
        setSignificanceData(significanceMap);
        // Save to cache even if incomplete
        saveCachedVIFAndSignificance(vifMap, significanceMap);
        setHasLRCompleted(true);
      }
      
      // Log summary
      console.log(`[VIF] Processed ${Object.keys(vifMap).length} features for VIF`);
      console.log(`[Significance] Processed ${Object.keys(significanceMap).length} features for significance`);
      
      // Log dropped variables if any
      if (data.dropped_variables && data.dropped_variables.length > 0) {
        console.log('[VIF] Some features were dropped and may not have VIF/p-values:', data.dropped_variables);
      }
    } catch (error) {
      console.error('[VIF] Error calculating VIF:', error);
      setHasLRCompleted(false);
    } finally {
      setIsCalculatingVIF(false);
    }
  };

  const AUTO_VIF_THRESHOLD = 10;

  const autoSelectFeaturesFromDiagnostics = async (
    vifMap: Record<string, number | null>,
    significanceMap: Record<string, { pValue: number | null; level: string }>
  ) => {
    if (selectedForModeling.length === 0) return;

    const previousSelection =
      selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling;

    const recommendedSelection = selectedForModeling.filter((variable) => {
      const vifValue = vifMap[variable];
      const significanceInfo = significanceMap[variable];
      const hasVif = typeof vifValue === 'number' && Number.isFinite(vifValue);
      const isHighVif = hasVif && (vifValue ?? 0) >= AUTO_VIF_THRESHOLD;
      const isLowSignificance =
        !!significanceInfo &&
        significanceInfo.pValue !== null &&
        significanceInfo.pValue !== undefined &&
        significanceInfo.level === 'Low';
      return !(isHighVif || isLowSignificance);
    });

    if (recommendedSelection.length === 0) {
      console.log('[Auto Selection] No features met quality criteria; preserving previous selections.');
      return;
    }

    const prevSet = new Set(previousSelection);
    const nextSet = new Set(recommendedSelection);
    const hasLengthChange = previousSelection.length !== recommendedSelection.length;
    const hasMembershipChange = previousSelection.some((col) => !nextSet.has(col)) || recommendedSelection.some((col) => !prevSet.has(col));
    if (!hasLengthChange && !hasMembershipChange) {
      console.log('[Auto Selection] Recommended selection matches current state; no changes applied.');
      return;
    }

    setSelectedForFinalModeling(recommendedSelection);
    showNotification(
      `Auto-selected ${recommendedSelection.length} variable${recommendedSelection.length === 1 ? '' : 's'} based on VIF & P-Value diagnostics.`
    );

    const columnsToEvaluate = Array.from(new Set([...previousSelection, ...recommendedSelection]));
    const persistPromises: Promise<void>[] = [];
    columnsToEvaluate.forEach((col) => {
      const shouldSelect = nextSet.has(col);
      const wasSelected = prevSet.has(col);
      if (shouldSelect === wasSelected) return;
      persistPromises.push(queueFinalPersist(col, shouldSelect, recommendedSelection));
    });

    if (persistPromises.length > 0) {
      try {
        await Promise.all(persistPromises);
        console.log('[Auto Selection] Final selection persisted to database.');
      } catch (err) {
        console.error('[Auto Selection] Failed to persist final selection:', err);
      }
    }
  };

  const getVIFStatus = (vif: number | null): { status: string; color: string } => {
    if (vif === null || vif === undefined) return { status: 'N/A', color: '#8b949e' };
    if (vif < 5) return { status: 'Low', color: '#52c41a' };
    if (vif < 10) return { status: 'Moderate', color: '#fa8c16' };
    return { status: 'High', color: '#ff4d4f' };
  };

  const getSignificanceStatus = (level: string): { status: string; color: string } => {
    switch (level) {
      case 'High':
        return { status: 'High', color: '#52c41a' }; // Green
      case 'Medium':
        return { status: 'Medium', color: '#fa8c16' }; // Orange/Yellow
      case 'Low':
        return { status: 'Low', color: '#ff4d4f' }; // Red
      default:
        return { status: 'N/A', color: '#8b949e' };
    }
  };

  // Removed useEffect for auto binning mode - now handled by handleSwitchToAutoBinning

  // Add/remove no-scroll class on body/html when component mounts/unmounts
  useEffect(() => {
    document.body.classList.add('no-scroll');
    document.documentElement.classList.add('no-scroll');
    const rootElement = document.getElementById('root');
    if (rootElement) {
      rootElement.classList.add('no-scroll');
    }

    return () => {
      document.body.classList.remove('no-scroll');
      document.documentElement.classList.remove('no-scroll');
      const rootElementCleanup = document.getElementById('root');
      if (rootElementCleanup) {
        rootElementCleanup.classList.remove('no-scroll');
      }
    };
  }, []);

  return (
    <div className="selected-columns-page">
      <Navbar developerMode={developerMode} onDeveloperModeChange={setDeveloperMode} currentStep={currentStep} />
      <div className="page-container">
        <div className="progress-header">
          <div className="progress-bar" role="navigation" aria-label="Analysis steps">
            {['Classification', 'Data Preprocessing', 'Binning', 'Models', 'Score Card'].map((step, index) => (
              <button
                key={step}
                className={`progress-step ${currentStep === index ? 'active' : ''} ${currentStep > index ? 'completed' : ''}`}
                onClick={() => {
                  if (index <= currentStep) {
                    setCurrentStep(index);
                  }
                }}
                disabled={index > currentStep}
                aria-current={currentStep === index ? 'step' : undefined}
                aria-label={`${step} step`}
              >
                <span className="progress-number">{index + 1}</span>
                <span>{step}</span>
              </button>
            ))}
          </div>
          <div className="progress-actions">
            <button
              className="progress-action-btn previous-button"
              disabled={currentStep === 0}
              onClick={() => setCurrentStep((prev) => Math.max(0, prev - 1))}
              aria-label="Go to previous step"
            >
              Previous
            </button>
            <button
              className="progress-action-btn next-button"
              disabled={currentStep === 4 || !canGoNext()} // Updated to 4 since you have 5 steps (0-4)
              onClick={() => {
                if (currentStep < 4) {
                  if (currentStep === 1) {
                    // From Data Preprocessing, go to Binning (may need special handling)
                    handleProceedToFeatureSelection();
                  } else {
                    // For other steps, just increment
                    setCurrentStep((prev) => Math.min(4, prev + 1));
                  }
                }
              }}
              aria-label="Go to next step"
            >
              Next
            </button>
          </div>
        </div>
        {notification && <div className="notification" role="alert">{notification}</div>}
        <div className={`main-content-wrapper ${currentStep === 0 || currentStep === 1 || currentStep === 4 || (currentStep === 2 && binningMode === 'auto') ? 'full-width' : ''}`}>
          {/* Show sidebar for Binning step (Step 2) in manual mode and Models step (Step 3) */}
          {(currentStep === 2 && binningMode === 'manual') && (
            <aside className="column-selection-section" aria-label="Scrollable column selection panel">
              <h3>Columns Dashboard</h3>
              <div className="sidebar-controls">
                <input
                  type="text"
                  placeholder="Search columns..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="search-input"
                />
                {/* Sorting controls and recommendation button removed */}
              </div>
              <div className="columns-grid" aria-label="List of selectable columns">
                {(() => {
                  try {

                  } catch { }
                  return null;
                })()}
                {filteredColumns.map((col: string) => {
                  const isChecked = selectedForModeling.includes(col);
                  try {

                  } catch { }
                  return (
                    <div
                      key={col}
                      className={`column-card ${col === activeColumn ? 'active' : ''}`}
                      onClick={() => handleColumnClick(col)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => e.key === 'Enter' && handleColumnClick(col)}
                      aria-label={`Select column ${col}`}
                    >
                      <div className="column-card-content">
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={(e) => {
                            e.stopPropagation();
                            toggleSelectedForModeling(col);
                          }}
                          className="column-checkbox"
                          id={`checkbox-${col}`}
                          aria-label={`Include ${col} in modeling`}
                        />
                        <div className="column-info">
                          <h4 className="column-name">{col}</h4>
                          <small>{(discreteColumns || []).includes(col) ? 'Discrete' : 'Continuous'}</small>
                        </div>
                        {/* IV badge removed from column cards; moved into binning area */}
                        {/* Drop button removed as requested */}
                        {/* Compare button removed with WOE/IV section */}
                      </div>
                    </div>
                  );
                })}
              </div>
            </aside>
          )}
          
          {/* Show sidebar for Models step (Step 3) */}
          {currentStep === 3 && (
            <aside className="column-selection-section" aria-label="Selected Variables panel">
              <h3>Selected Variables</h3>
              <div className="variables-list-sidebar">
                {selectedForModeling.filter((col: string) => col !== targetVariable).map((variable: string) => {
                  const isSelected = (currentStep === 3 && selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling).includes(variable);
                  const vif = vifData[variable] ?? null;
                  const vifStatus = getVIFStatus(vif);
                  const pValue =
                    significanceData[variable]?.pValue !== null && significanceData[variable]?.pValue !== undefined
                      ? significanceData[variable].pValue
                      : null;
                  const significanceStatus = getSignificanceStatus(significanceData[variable]?.level || 'Low');
                  return (
                    <div
                      key={variable}
                      className={`variable-item-sidebar ${activeColumn === variable ? 'active' : ''}`}
                      onClick={() => setActiveColumn(variable)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => e.key === 'Enter' && setActiveColumn(variable)}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={(e) => {
                          e.stopPropagation();
                          toggleSelectedForFinalModeling(variable);
                        }}
                        className="column-checkbox"
                        onClick={(e) => e.stopPropagation()}
                      />
                      <div className="variable-info-sidebar">
                        <span className="variable-name-sidebar">{variable}</span>
                        {isCalculatingVIF ? (
                          <span className="vif-loading">Calculating VIF...</span>
                        ) : (
                          <>
                            <div className="vif-info">
                              <span className="metric-label">Multicollinearity (VIF):&nbsp;</span>
                              <span className="metric-value">{vif !== null && vif !== undefined ? vif.toFixed(2) : 'N/A'}</span>
                              <span className="metric-status" style={{ color: vifStatus.color }}>
                                {vifStatus.status}
                              </span>
                            </div>
                            <div className="significance-info">
                              <span className="metric-label">Significance (P-Value):&nbsp;</span>
                              <span className="metric-value">{pValue !== null ? pValue.toFixed(4) : 'N/A'}</span>
                              <span className="metric-status" style={{ color: significanceStatus.color }}>
                                {significanceStatus.status}
                              </span>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="sidebar-action-buttons">
                {selectedModel === 'logistic' && (
                  <button
                    className="run-regression-btn-sidebar"
                    onClick={() => {
                      setTriggerLogisticRegression(prev => prev + 1);
                    }}
                    disabled={
                      isCalculatingVIF || 
                      !hasLRCompleted ||
                      (currentStep === 3 && selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling).length === 0 ||
                      Object.keys(vifData).length === 0 ||
                      Object.keys(significanceData).length === 0 ||
                      !Object.values(vifData).some(v => v !== null) ||
                      !Object.values(significanceData).some(s => s.pValue !== null)
                    }
                  >
                    {isCalculatingVIF ? 'Calculating VIF...' : 'Run Logistic Regression'}
                  </button>
                )}
                {selectedModel === 'random_forest' && (
                  <button
                    className="run-regression-btn-sidebar"
                    onClick={() => {
                      setTriggerRandomForest(prev => prev + 1);
                    }}
                    disabled={
                      isCalculatingVIF || 
                      !hasLRCompleted ||
                      (currentStep === 3 && selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling).length === 0 ||
                      Object.keys(vifData).length === 0 ||
                      Object.keys(significanceData).length === 0 ||
                      !Object.values(vifData).some(v => v !== null) ||
                      !Object.values(significanceData).some(s => s.pValue !== null)
                    }
                  >
                    Run Random Forest
                  </button>
                )}
                {selectedModel === 'xgboost' && (
                  <button
                    className="run-regression-btn-sidebar"
                    onClick={() => {
                      setTriggerXGBoost(prev => prev + 1);
                    }}
                    disabled={
                      isCalculatingVIF || 
                      !hasLRCompleted ||
                      (currentStep === 3 && selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling).length === 0 ||
                      Object.keys(vifData).length === 0 ||
                      Object.keys(significanceData).length === 0 ||
                      !Object.values(vifData).some(v => v !== null) ||
                      !Object.values(significanceData).some(s => s.pValue !== null)
                    }
                  >
                    Run XGBoost
                  </button>
                )}
                {selectedModel === 'stacking' && (
                  <button
                    className="auto-monotonic-btn"
                    onClick={() => {
                      setTriggerStacking(prev => prev + 1);
                    }}
                    disabled={
                      isCalculatingVIF || 
                      !hasLRCompleted ||
                      (currentStep === 3 && selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling).length === 0 ||
                      Object.keys(vifData).length === 0 ||
                      Object.keys(significanceData).length === 0 ||
                      !Object.values(vifData).some(v => v !== null) ||
                      !Object.values(significanceData).some(s => s.pValue !== null)
                    }
                  >
                    <span className="btn-icon">⚡</span>
                    Run Stacking Ensemble
                  </button>
                )}
              </div>
            </aside>
          )}

          <section className="content-section">
            {/* Step 0: Classification */}
            {currentStep === 0 && (
              <div className="column-selection-step" style={{ width: '100%' }}>
                <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', marginTop: '24px', marginBottom: '16px', position: 'relative' }}>
                  {isLoadingAIClassification && (
                    <div className="loading-overlay">
                      <div className="loading-spinner"></div>
                      <p>Running AI classification...</p>
                    </div>
                  )}
                  <button
                    className="auto-monotonic-btn"
                    disabled={isLoadingAIClassification}
                    onClick={async () => {
                      try {
                        const colsToClassify = columns;
                        if (!colsToClassify || colsToClassify.length === 0) {
                          alert('No columns to classify');
                          return;
                        }

                        setIsLoadingAIClassification(true);

                        let sampleData: Record<string, any[]> = {};
                        try {
                          const sampleResp = await authPost('/api/csv-samples', { columns: colsToClassify, sample_size: 20, record_id: recordId });
                          if (sampleResp && typeof sampleResp === 'object') {
                            sampleData = sampleResp as Record<string, any[]>;
                          }
                        } catch (e) {
                          console.warn('Could not fetch CSV samples:', e);
                        }
                        // Ensure all columns have sample data (even if empty)
                        colsToClassify.forEach(col => {
                          if (!sampleData[col]) {
                            sampleData[col] = [];
                          }
                        });

                        const data = await authPost('/api/ai-classify-columns', { columns: colsToClassify, sampleData, record_id: recordId });
                        if (data && !data.error) {
                          let discreteCount = 0;
                          let continuousCount = 0;
                          Object.entries(data).forEach(([col, typ]) => {
                            if (col && (typ === 'discrete' || typ === 'continuous')) {
                              handleTypeChange(col, typ as string);
                              if (typ === 'discrete') discreteCount++;
                              else continuousCount++;
                            }
                          });
                          alert(`AI classification complete!\nClassified ${discreteCount} discrete and ${continuousCount} continuous variables.`);
                        } else {
                          const errorMsg = data?.error || 'Unknown error';
                          console.error('AI classification failed:', errorMsg, data);
                          alert(`AI classification failed: ${errorMsg}`);
                        }
                      } catch (e) {
                        console.error('AI classification error:', e);
                        alert(`AI classification failed: ${e instanceof Error ? e.message : String(e)}`);
                      } finally {
                        setIsLoadingAIClassification(false);
                      }
                    }}
                  >
                    <span className="btn-icon">⚡</span>
                    <span className="btn-text">{isLoadingAIClassification ? 'Classifying...' : 'AI Recommendation on Classification of Discrete and Continuous'}</span>
                  </button>
                </div>
                <div style={{ width: '100%', flex: 1, display: 'flex', flexDirection: 'column' }}>
                  <ColumnPanels
                    columns={columns}
                    paginatedColumns={paginatedColumns}
                    discreteColumns={discreteColumns}
                    continuousColumns={continuousColumns}
                    targetVariable={targetVariable}
                    targetCounts={targetCounts}
                    handleTypeChange={handleTypeChange}
                    setTargetVariable={setTargetVariable}
                    currentPage={currentPage}
                    totalPages={totalPages}
                    onNextPage={handleNextPage}
                    onPrevPage={handlePrevPage}
                    assignRemainingToContinuous={assignRemainingToContinuous}
                    selectedForUnivariate={selectedForUnivariate}
                    toggleSelectedForUnivariate={toggleSelectedForUnivariate}
                    toggleSelectAllDiscrete={toggleSelectAllDiscrete}
                    toggleSelectAllContinuous={toggleSelectAllContinuous}
                    handleFineBin={async () => { }}
                    datasetPath={datasetPath}
                    recordId={recordId}
                    showCheckboxes={false}
                    columnListRef={columnListRef as React.RefObject<HTMLDivElement>}
                  />
                </div>
              </div>
            )}

            {/* Step 1: Data Preprocessing */}
            {currentStep === 1 && (
              <div className="preprocessing-step" style={{ width: '100%' }}>
                <PreprocessingDetails
                  datasetId={recordId}
                  onPreprocessingComplete={(newDatasetId?: number) => {
                    if (newDatasetId) {
                      setRecordId(newDatasetId);
                    }
                    setCurrentStep(2);
                    showNotification('Data preprocessing completed successfully!');
                    loadSavedData();
                  }}
                  onPreprocessSelectionSaved={() => {
                    setPreprocessSelectionSaved(true);
                  }}
                />
              </div>
            )}

            {currentStep === 2 && (
              <div className="binning-mode-toggle">
                <div className="mode-toggle-group">
                  <button
                    className={`mode-toggle-btn ${binningMode === 'auto' ? 'active' : ''}`}
                    onClick={handleSwitchToAutoBinning}
                  >
                    Auto Binning
                  </button>
                  <button
                    className={`mode-toggle-btn ${binningMode === 'manual' ? 'active' : ''}`}
                    onClick={() => setBinningMode('manual')}
                  >
                    Manual Binning
                  </button>
                </div>
                {binningMode === 'auto' && (
                  <div className="all-auto-monotonic-container">
                    <button
                      className="all-auto-monotonic-btn"
                      onClick={runAllAutoMonotonicFineBinning}
                      disabled={
                        isLoadingAllAutoMonotonic ||
                        isLoadingCoarseBins ||
                        selectedColumns.some(col => {
                          if (col === targetVariable) return false;
                          return !Array.isArray(coarseBinResults[col]) || coarseBinResults[col].length === 0;
                        })
                      }
                      aria-label="Run auto-monotonic fine binning for all columns"
                      title="Automatically merge bins to achieve monotonic WOE trend for all columns"
                    >
                      <span className="btn-icon">⚡</span>
                      All Auto Monotonic Fine binning
                    </button>
                    <div className="export-controls-divider" />
                    <div className="export-controls-group">
                      <button
                        className="export-select-btn"
                        onClick={selectedForExport.length === selectedColumns.filter(c => c !== targetVariable).length ? deselectAllForExport : selectAllForExport}
                        title={selectedForExport.length === selectedColumns.filter(c => c !== targetVariable).length ? 'Deselect all charts' : 'Select all charts for export'}
                      >
                        {selectedForExport.length === selectedColumns.filter(c => c !== targetVariable).length ? '☐ Deselect All' : '☑ Select All'}
                      </button>
                      <button
                        className="export-select-btn model-ready-select-btn"
                        onClick={selectModelReadyForExport}
                        title={`Select only model-ready columns for export (${selectedForModeling.filter(c => c !== targetVariable && selectedColumns.includes(c)).length} columns)`}
                        disabled={selectedForModeling.filter(c => c !== targetVariable && selectedColumns.includes(c)).length === 0}
                      >
                        <span className="btn-icon">✓</span>
                        Select Model Ready ({selectedForModeling.filter(c => c !== targetVariable && selectedColumns.includes(c)).length})
                      </button>
                      <span className="export-count-badge">
                        {selectedForExport.length} selected
                      </span>
                      <button
                        className="export-btn export-pdf-btn"
                        onClick={() => exportSelectedCharts('pdf')}
                        disabled={selectedForExport.length === 0 || isExportingCharts}
                        title="Export selected charts as PDF"
                      >
                        <span className="btn-icon">📄</span>
                        {isExportingCharts ? 'Exporting...' : 'Export PDF'}
                      </button>
                      <button
                        className="export-btn export-png-btn"
                        onClick={() => exportSelectedCharts('png')}
                        disabled={selectedForExport.length === 0 || isExportingCharts}
                        title="Export selected charts as PNG images"
                      >
                        <span className="btn-icon">🖼️</span>
                        {isExportingCharts ? 'Exporting...' : 'Export PNGs'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
            {currentStep === 2 && binningMode === 'auto' && (
              <div className="auto-binning-container">
                {isLoadingAllAutoMonotonic ? (
                  <div className="fine-binning-loading">
                    <div className="fine-binning-spinner"></div>
                    <p>Applying auto monotonic fine binning to all features...</p>
                  </div>
                ) : isLoadingCoarseBins || selectedColumns.some(col => {
                  if (col === targetVariable) return false;
                  return !Array.isArray(coarseBinResults[col]) || coarseBinResults[col].length === 0;
                }) ? (
                  <div className="coarse-bins-loading">
                    <div className="coarse-bins-spinner"></div>
                    <p>Calculating coarse bins...</p>
                  </div>
                ) : (
                  <div className="auto-binning-grid">
                    {selectedColumns.map((col) => {
                      const woeData = woeIvResults[col];
                      const isLoading = loadingColumns.has(col);
                      const isSelected = selectedForModeling.includes(col);
                      const isExportSelected = selectedForExport.includes(col);

                      // Create a stable ref object for this column
                      if (!chartCardRefs.current[col]) {
                        chartCardRefs.current[col] = null;
                      }

                      return (
                        <AutoBinningCard
                          key={col}
                          col={col}
                          woeData={woeData}
                          isLoading={isLoading}
                          isSelected={isSelected}
                          isSelectedForExport={isExportSelected}
                          onToggle={toggleSelectedForModeling}
                          onToggleExport={toggleSelectedForExport}
                          onConfigureManually={handleConfigureManually}
                          continuousColumns={continuousColumns || []}
                          cardRef={{
                            get current() { return chartCardRefs.current[col]; },
                            set current(el) { chartCardRefs.current[col] = el; }
                          } as React.RefObject<HTMLDivElement | null>}
                        />
                      );
                    })}
                  </div>
                )}
              </div>
            )}
            {currentStep === 2 && binningMode === 'manual' && activeColumn && (() => {
              const isContinuousColumn = (continuousColumns || []).includes(activeColumn);
              const coarseRows: NormalizedBin[] = coarseBinResults[activeColumn] || [];
              const fineRowSource = fineBinResults[activeColumn];
              const fineRows: NormalizedBin[] =
                Array.isArray(fineRowSource) && fineRowSource.length > 0
                  ? fineRowSource
                  : coarseRows;
              const history = binMergeHistory[activeColumn] || {};
              const selectedLabels = selectedFineBins[activeColumn] || [];
              const selectedCount = selectedLabels.length;
              const woeStats: NormalizedBin[] = woeIvResults[activeColumn]?.stats || [];

              const metricsArray = binScoringMetrics[activeColumn] || [];
              const metricsAggregate = metricsArray.reduce(
                (acc, metric) => {
                  const g = Number(metric?.good_count ?? 0);
                  const b = Number(metric?.bad_count ?? 0);
                  acc.good += Number.isFinite(g) ? g : 0;
                  acc.bad += Number.isFinite(b) ? b : 0;
                  return acc;
                },
                { good: 0, bad: 0 }
              );

              const totalsRecord = binScoringTotals[activeColumn];
              const totalGoodForDerived = Number.isFinite(Number(totalsRecord?.total_good)) && totalsRecord?.total_good !== undefined
                ? Number(totalsRecord.total_good)
                : metricsAggregate.good;
              const totalBadForDerived = Number.isFinite(Number(totalsRecord?.total_bad)) && totalsRecord?.total_bad !== undefined
                ? Number(totalsRecord.total_bad)
                : metricsAggregate.bad;

              const computeDerivedStatsForCounts = (goodCount: number, badCount: number, totalCount: number) => {
                const safeGood = Number.isFinite(goodCount) ? goodCount : 0;
                const safeBad = Number.isFinite(badCount) ? badCount : 0;
                const safeTotal = Number.isFinite(totalCount) ? totalCount : safeGood + safeBad;

                const distGoodPct = totalGoodForDerived > 0 ? (safeGood / totalGoodForDerived) * 100 : 0;
                const distBadPct = totalBadForDerived > 0 ? (safeBad / totalBadForDerived) * 100 : 0;

                let woeValue = 0;
                let ivValue = 0;
                if (distGoodPct > 0 && distBadPct > 0) {
                  const ratio = distGoodPct / distBadPct;
                  const lnRatio = Math.log(ratio);
                  if (Number.isFinite(lnRatio)) {
                    const woeScaled = lnRatio * 100;
                    const ivRaw = ((distGoodPct - distBadPct) * lnRatio) / 100;
                    woeValue = Number(woeScaled.toFixed(1));
                    ivValue = Number(ivRaw.toFixed(4));
                  }
                }

                return {
                  goodCount: safeGood,
                  badCount: safeBad,
                  totalCount: safeTotal,
                  distGoodPct,
                  distBadPct,
                  woeValue,
                  ivValue,
                };
              };
              const standardizeKey = (value: string) => normalizeDisplayLabel(value).toLowerCase();

              const formatWoeKeyDisplay = (rawKey?: string | null) => {
                if (!rawKey) return '—';
                let working = String(rawKey).trim();
                const computedPrefix = working.startsWith('computed:');
                if (computedPrefix) {
                  working = working.slice('computed:'.length).trim();
                }
                const digitsOnly = working.match(/^\d+$/);
                if (digitsOnly) {
                  working = `Bin_${digitsOnly[0]}`;
                } else if (/^bin[\s_\-]*\d+$/i.test(working)) {
                  const match = working.match(/\d+/);
                  if (match) working = `Bin_${match[0]}`;
                } else if (working.includes(',')) {
                  const parts = working.split(',').map(p => p.trim()).filter(Boolean);
                  const normalized = parts.map(part => (part.match(/^\d+$/) ? `Bin_${part}` : part));
                  working = normalized.join('_');
                }
                return computedPrefix ? `computed:${working}` : working;
              };

              const woeLookup = (() => {
                const map = new Map<string, any>();
                const variantsFor = (raw: string) => {
                  const out = new Set<string>();
                  const s = String(raw).trim();
                  if (!s) return Array.from(out);
                  const base = s;
                  out.add(base);
                  // common variants: remove 'bin' prefix, replace underscores/spaces, numeric only
                  const noPrefix = base.replace(/^bin[\s_\-]*/i, '');
                  out.add(noPrefix);
                  out.add(base.replace(/[_\s\-]+/g, ' '));
                  out.add(base.replace(/[_\s\-]+/g, '_'));
                  out.add(base.replace(/[_\s\-]+/g, '-'));
                  // numeric-only variant if digits exist
                  const m = base.match(/(\d+)/);
                  if (m) out.add(m[1]);
                  return Array.from(out).map(x => standardizeKey(String(x)));
                };

                woeStats.forEach((row: NormalizedBin) => {
                  const candidates = [row.Bin, row.Range];
                  candidates.forEach((candidate) => {
                    if (candidate === null || candidate === undefined) return;
                    const variants = variantsFor(String(candidate));
                    variants.forEach(v => {
                      if (!map.has(v)) map.set(v, row);
                    });
                  });
                });
                return map;
              })();

              // Helper to find binScoringMetrics entry for a displayed label.
              // Handles merged labels like 'Bin_2_Bin_3' by splitting into components
              // and attempting to match by numeric parts or normalized equality.
              const findBinMetric = (labelRaw: any, labelDisplay?: string) => {
                const metrics = binScoringMetrics[activeColumn] || [];
                if (!metrics || metrics.length === 0) return null;
                const rawStr = String(labelRaw);
                // 1) exact match
                let m = metrics.find((mm: any) => String(mm.bin_name) === rawStr);
                if (m) return m;

                // 2) normalized key match
                const standardize = (v: string) => String(v).replace(/[_\s\-]+/g, ' ').trim().toLowerCase();
                const target = standardize(rawStr);
                m = metrics.find((mm: any) => standardize(String(mm.bin_name)) === target);
                if (m) return m;

                // 3) split merged labels into components and match by numeric parts
                const parts = rawStr.split(/[_\s,\-]+/).map(p => p.trim()).filter(Boolean);
                const numericParts = parts.flatMap(p => (p.match(/\d+/g) || []));
                if (numericParts.length > 0) {
                  // try to find a metric that contains all numericParts
                  m = metrics.find((mm: any) => {
                    const mmNums: string[] = (String(mm.bin_name).match(/\d+/g) || []) as string[];
                    return numericParts.every((np: string) => mmNums.includes(np));
                  });
                  if (m) return m;

                  // try partial match: any overlap
                  m = metrics.find((mm: any) => {
                    const mmNums: string[] = (String(mm.bin_name).match(/\d+/g) || []) as string[];
                    return numericParts.some((np: string) => mmNums.includes(np));
                  });
                  if (m) return m;
                }

                // 4) try matching by whether metric bin_name contains the display label
                if (labelDisplay) {
                  const disp = standardize(String(labelDisplay));
                  m = metrics.find((mm: any) => standardize(String(mm.bin_name)).includes(disp) || disp.includes(standardize(String(mm.bin_name))));
                  if (m) return m;
                }

                return null;
              };

              const getWoeRow = (label: string, range?: string, rawLabel?: any) => {
                if (!label && !range) return null;
                const tryKeys = (val?: string) => {
                  if (!val) return null;
                  const candidates = [] as string[];
                  const raw = String(val);
                  candidates.push(standardizeKey(raw));
                  // try removing common 'Bin' prefixes
                  candidates.push(standardizeKey(raw.replace(/^bin[\s_\-]*/i, '')));
                  // try numeric-only suffix
                  const m = raw.match(/(\d+)/);
                  if (m) candidates.push(standardizeKey(m[1]));
                  // try replacing underscores/spaces
                  candidates.push(standardizeKey(raw.replace(/[_\s\-]+/g, ' ')));
                  candidates.push(standardizeKey(raw.replace(/[_\s\-]+/g, '_')));
                  for (const k of candidates) {
                    const found = woeLookup.get(k);
                    if (found) return found;
                  }
                  return null;
                };

                // direct label match
                const direct = tryKeys(label);
                if (direct) return direct;
                // try range string
                const rangeMatch = tryKeys(range);
                if (rangeMatch) return rangeMatch;

                // fallback to scanning woeStats by normalized equality as last resort
                const scanned = woeStats.find((row: NormalizedBin) => {
                  const rowLabel = row.Bin ?? row.Range ?? '';
                  return normalizeDisplayLabel(String(rowLabel)) === normalizeDisplayLabel(label) ||
                    normalizeDisplayLabel(String(rowLabel)) === normalizeDisplayLabel(range || '');
                });
                if (scanned) return scanned;

                // absolute fallback: compute WOE/IV from binScoringMetrics when possible
                const metric = rawLabel !== undefined ? findBinMetric(rawLabel, label) : findBinMetric(label, label);
                const totals = binScoringTotals[activeColumn];
                if (metric && totals && (totals.total_good || totals.total_bad)) {
                  const goodValue = Number(metric.good_count || 0);
                  const badValue = Number(metric.bad_count || 0);
                  const totalValue = Number(metric.total_count || (goodValue + badValue));
                  const distGoodFrac = goodValue / Math.max(1, Number(totals.total_good));
                  const distBadFrac = badValue / Math.max(1, Number(totals.total_bad));
                  let woeVal = 0;
                  if (distGoodFrac > 0 && distBadFrac > 0) {
                    woeVal = Math.log(distGoodFrac / distBadFrac);
                  } else if (distGoodFrac > 0 && distBadFrac === 0) {
                    woeVal = Math.log(distGoodFrac / (1e-9));
                  } else if (distGoodFrac === 0 && distBadFrac > 0) {
                    woeVal = Math.log((1e-9) / distBadFrac);
                  }
                  const ivContribution = (distGoodFrac - distBadFrac) * woeVal;
                  const computedRow = {
                    WOE: woeVal,
                    IV: ivContribution,
                    'Dist_Good_%': distGoodFrac * 100,
                    'Dist_Bad_%': distBadFrac * 100,
                    Good: goodValue,
                    Bad: badValue,
                    Total: totalValue,
                    __computed: true
                  };
                  const key = standardizeKey(String(rawLabel ?? label));
                  if (!woeLookup.has(key)) {
                    woeLookup.set(key, computedRow);
                  }
                  return computedRow;
                }

                return null;
              };

              // Return the standardized key that matched in woeLookup (or null)
              const getMatchedKey = (label?: string, range?: string, rawLabel?: any) => {
                const tryKeys = (val?: string) => {
                  if (!val) return null;
                  const candidates = [] as string[];
                  const raw = String(val);
                  candidates.push(standardizeKey(raw));
                  candidates.push(standardizeKey(raw.replace(/^bin[\s_\-]*/i, '')));
                  const m = raw.match(/(\d+)/);
                  if (m) candidates.push(standardizeKey(m[1]));
                  candidates.push(standardizeKey(raw.replace(/[_\s\-]+/g, ' ')));
                  candidates.push(standardizeKey(raw.replace(/[_\s\-]+/g, '_')));
                  for (const k of candidates) {
                    if (woeLookup.has(k)) return k;
                  }
                  return null;
                };

                const d = tryKeys(label);
                if (d) return d;
                const r = tryKeys(range);
                if (r) return r;

                if (rawLabel !== undefined) {
                  const metric = findBinMetric(rawLabel, label);
                  const totals = binScoringTotals[activeColumn];
                  if (metric && totals && (totals.total_good || totals.total_bad)) {
                    return `computed:${standardizeKey(String(rawLabel))}`;
                  }
                }

                return null;
              };

              const pickNumeric = (...values: any[]) => {
                for (const value of values) {
                  if (value === null || value === undefined || value === '') continue;
                  const num = Number(value);
                  if (Number.isFinite(num)) {
                    return num;
                  }
                }
                return 0;
              };

              const getBinIdentifiers = (bin: NormalizedBin, idx: number) => {
                const raw = getBinLabelValue(bin, idx);
                const rangeValue = getRangeText(bin);
                return { labelValRaw: raw, labelVal: raw, rangeValue };
              };

              // === SORT BINS ===
              // === SORT BINS ===
              const sortedRows = [...fineRows].sort((a: NormalizedBin, b: NormalizedBin) => {
                // For discrete columns, sort by bin number (Bin_1, Bin_2, Bin_3, etc.)
                if (!isContinuousColumn) {
                  const labelA = getBinLabelValue(a, 0);
                  const labelB = getBinLabelValue(b, 0);

                  // Extract numeric parts from bin labels
                  const numA = getNumericOrderFromLabel(labelA);
                  const numB = getNumericOrderFromLabel(labelB);

                  // If both have numeric parts, sort numerically
                  if (numA !== null && numB !== null) {
                    return numA - numB;
                  }

                  // If only one has numeric part, put numeric first
                  if (numA !== null && numB === null) return -1;
                  if (numA === null && numB !== null) return 1;

                  // Fallback: alphabetical sort
                  return labelA.localeCompare(labelB);
                }

                // For continuous columns, use existing logic (sort by min value)
                const minA = getMinFromBin(a);
                const minB = getMinFromBin(b);
                if (!Number.isNaN(minA) && !Number.isNaN(minB)) {
                  return Number(minA) - Number(minB);
                }

                const labelA = getBinLabelValue(a, 0);
                const labelB = getBinLabelValue(b, 0);
                const numA = getNumericOrderFromLabel(labelA);
                const numB = getNumericOrderFromLabel(labelB);
                if (numA !== null && numB !== null) {
                  return numA - numB;
                }
                return labelA.localeCompare(labelB);
              });
              // === CHART DATA (WOE/IV from backend) ===
              const chartRows = sortedRows.map((bin: any, idx: number) => {
                const { labelValRaw, labelVal, rangeValue } = getBinIdentifiers(bin, idx);
                const woeData = getWoeRow(labelVal, rangeValue, labelValRaw) || {};

                // Prefer authoritative counts from binScoringMetrics when available
                const binMetrics = findBinMetric(labelValRaw, labelVal);
                const goodCount = binMetrics?.good_count ?? pickNumeric(woeData.Good, bin.Good, bin.good_count);
                const badCount = binMetrics?.bad_count ?? pickNumeric(woeData.Bad, bin.Bad, bin.bad_count);
                const totalCount = binMetrics?.total_count ?? pickNumeric(woeData.Total, bin.Total, bin.total_count, (goodCount + badCount));
                const derived = computeDerivedStatsForCounts(Number(goodCount), Number(badCount), Number(totalCount));

                return {
                  Bin: labelVal,
                  Range: rangeValue || (typeof woeData.Range === 'string' ? woeData.Range : ''),
                  WOE: derived.woeValue,
                  IV: derived.ivValue,
                  Good: derived.goodCount,
                  Bad: derived.badCount,
                  Total: derived.totalCount,
                };
              });

              return (
                <div className="binning-section" aria-label="Binning controls and results">
                  <div className="results-container">
                    <h3>Binning - {activeColumn}</h3>

                    <div className="table-container">
                      <table className="cross-tab-table" aria-label={`Fine binning workspace for ${activeColumn}`}>
                        <thead>
                          <tr>
                            <th>Select</th>
                            <th>Bin</th>
                            {isContinuousColumn ? (
                              <>
                                <th>Min</th>
                                <th>Max</th>
                              </>
                            ) : (
                              <th>Range</th>
                            )}
                            <th>0 (Good)</th>
                            <th>1 (Bad)</th>
                            <th>Total</th>
                            <th>0/1 (G/B)</th>
                            <th>Bad Rate (%)</th>
                            <th>Freq%</th>
                            <th>G/B Odd</th>
                            <th>Index</th>
                            <th>G/B Index</th>
                            <th>Dist Good (%)</th>
                            <th>Dist Bad (%)</th>
                            <th>WOE</th>
                            <th>IV</th>
                            <th>Actions</th>
                            <th>Metrics</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sortedRows.length === 0 ? (
                            <tr>
                              <td colSpan={isContinuousColumn ? 17 : 16} style={{ textAlign: 'center', padding: '16px' }}>
                                No binning results available.
                              </td>
                            </tr>
                          ) : (
                            sortedRows.map((bin: NormalizedBin, idx: number) => {
                              const { labelValRaw, labelVal, rangeValue } = getBinIdentifiers(bin, idx);
                              const minVal = getMinFromBin(bin);
                              const maxVal = getMaxFromBin(bin);
                              const minDisplay = minVal !== null && minVal !== undefined ? minVal : (isContinuousColumn ? 'N/A' : '—');
                              const maxDisplay = maxVal !== null && maxVal !== undefined ? maxVal : (isContinuousColumn ? 'N/A' : '—');

                              const normalizedLabel = normalizeDisplayLabel(labelVal);
                              const rawWoe = getWoeRow(labelVal, rangeValue, labelValRaw) || getWoeRow(normalizedLabel, rangeValue, labelValRaw) || {};
                              const fallbackMetrics = findBinMetric(labelValRaw, labelVal);

                              const goodValue = pickNumeric(
                                fallbackMetrics?.good_count,
                                rawWoe.Good,
                                bin.Good,
                                bin.good_count
                              );
                              const badValue = pickNumeric(
                                fallbackMetrics?.bad_count,
                                rawWoe.Bad,
                                bin.Bad,
                                bin.bad_count
                              );
                              const totalValue = pickNumeric(
                                fallbackMetrics?.total_count,
                                rawWoe.Total,
                                bin.Total,
                                bin.total_count,
                                goodValue + badValue
                              );

                              const derived = computeDerivedStatsForCounts(Number(goodValue), Number(badValue), Number(totalValue));
                              const displayWoeData = {
                                ...rawWoe,
                                Good: derived.goodCount,
                                Bad: derived.badCount,
                                Total: derived.totalCount,
                                'Dist_Good_%': derived.distGoodPct,
                                'Dist_Bad_%': derived.distBadPct,
                                WOE: derived.woeValue,
                                IV: derived.ivValue,
                              };

                              const badRateRaw =
                                typeof bin['Bad Rate'] === 'number'
                                  ? bin['Bad Rate']
                                  : (typeof bin.bad_rate === 'number' ? bin.bad_rate : null);
                              const freqRaw =
                                typeof bin['Freq%'] === 'number'
                                  ? bin['Freq%']
                                  : (typeof bin.freq_percent === 'number' ? bin.freq_percent : null);

                              const isMergedLabel = Boolean(history[labelVal]);
                              const isSelected = selectedLabels.includes(labelVal);

                              // Build table cells programmatically to avoid accidental
                              // whitespace-only text nodes between JSX elements which
                              // can cause hydration errors when rendering <tr> children.
                              const cells: any[] = [];
                              // Checkbox cell
                              cells.push(
                                <td key={`chk-${labelVal}-${idx}`}>
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={(ev) => {
                                      ev.stopPropagation();
                                      toggleFineBinSelection(activeColumn, labelVal);
                                    }}
                                    aria-label={`Select bin ${labelVal} for ${activeColumn}`}
                                  />
                                </td>
                              );

                              // Label cell
                              cells.push(
                                <td key={`label-${labelVal}-${idx}`} title={rangeValue.length > 0 ? rangeValue : undefined} style={{ maxWidth: '160px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                  {labelVal}
                                </td>
                              );

                              // Min/Max or Discrete dropdown
                              if (isContinuousColumn) {
                                cells.push(<td key={`min-${labelVal}-${idx}`}>{minDisplay}</td>);
                                cells.push(<td key={`max-${labelVal}-${idx}`}>{maxDisplay}</td>);
                              } else {
                                cells.push(
                                  <td key={`disc-${labelVal}-${idx}`}>
                                    <DiscreteValuesDropdown rangeValue={rangeValue} />
                                  </td>
                                );
                              }

                              // Good / Bad / Total
                              cells.push(<td key={`good-${labelVal}-${idx}`} style={{ color: 'green', fontWeight: 'bold' }}>{goodValue}</td>);
                              cells.push(<td key={`bad-${labelVal}-${idx}`} style={{ color: 'red', fontWeight: 'bold' }}>{badValue}</td>);
                              cells.push(<td key={`total-${labelVal}-${idx}`}>{totalValue}</td>);

                              // 0/1 Ratio
                              cells.push(
                                <td key={`ratio-${labelVal}-${idx}`}>
                                  {(() => {
                                    const binMetrics = findBinMetric(labelValRaw, labelVal);
                                    return binMetrics?.zero_one_ratio || '—';
                                  })()}
                                </td>
                              );

                              // Bad Rate and Freq
                              cells.push(<td key={`br-${labelVal}-${idx}`}>{badRateRaw !== null && badRateRaw !== undefined ? badRateRaw.toFixed(4) : '0.0000'}</td>);
                              cells.push(<td key={`freq-${labelVal}-${idx}`}>{freqRaw !== null && freqRaw !== undefined ? freqRaw.toFixed(2) : '0.00'}</td>);

                              // G/B Odd
                              cells.push(
                                <td key={`gbodd-${labelVal}-${idx}`}>
                                  {(() => {
                                    const binMetrics = findBinMetric(labelValRaw, labelVal);
                                    return binMetrics?.gb_odd || '—';
                                  })()}
                                </td>
                              );

                              // G/B Index
                              cells.push(
                                <td key={`gbindex-${labelVal}-${idx}`}>
                                  {(() => {
                                    const binMetrics = findBinMetric(labelValRaw, labelVal);
                                    return (
                                      <span style={{
                                        color: binMetrics?.gb_index === 'G' ? 'green' : 'red',
                                        fontWeight: 'bold'
                                      }}>
                                        {binMetrics?.gb_index || '—'}
                                      </span>
                                    );
                                  })()}
                                </td>
                              );

                              // Combined Index
                              cells.push(
                                <td key={`combined-${labelVal}-${idx}`}>
                                  {(() => {
                                    const binMetrics = findBinMetric(labelValRaw, labelVal);
                                    return (
                                      <span style={{
                                        color: binMetrics?.gb_index === 'G' ? 'green' : 'red',
                                        fontWeight: 'bold'
                                      }}>
                                        {binMetrics?.combined_index || '—'}
                                      </span>
                                    );
                                  })()}
                                </td>
                              );

                              // Dist Good/Bad, WOE, IV
                              cells.push(<td key={`distgood-${labelVal}-${idx}`}>{formatToFourDecimals(displayWoeData['Dist_Good_%'] || 0)}</td>);
                              cells.push(<td key={`distbad-${labelVal}-${idx}`}>{formatToFourDecimals(displayWoeData['Dist_Bad_%'] || 0)}</td>);
                              cells.push(<td key={`woe-${labelVal}-${idx}`}>{formatToFourDecimals(displayWoeData.WOE || 0)}</td>);
                              cells.push(<td key={`iv-${labelVal}-${idx}`}>{formatToFourDecimals(displayWoeData.IV || 0)}</td>);

                              const matchedKey = getMatchedKey(labelVal, rangeValue, labelValRaw);
                              const metricsBin = fallbackMetrics; // reuse previously resolved metric
                              const displayMatchedKey = matchedKey ? formatWoeKeyDisplay(matchedKey) : '—';
                              const displayMetricName = metricsBin?.bin_name ? formatWoeKeyDisplay(String(metricsBin.bin_name)) : '—';

                              // Actions cell (Unmerge)
                              cells.push(
                                <td key={`actions-${labelVal}-${idx}`}>
                                  {isMergedLabel ? (
                                    <button
                                      className="unmerge-btn compact"
                                      onClick={() => unmergeFineBin(activeColumn, labelVal)}
                                      aria-label={`Unmerge ${labelVal}`}
                                      title="Unmerge"
                                    >
                                      <span style={{ fontSize: '12px', fontWeight: 600, padding: '2px 8px', borderRadius: '6px', background: 'var(--bg-quaternary)', color: 'var(--fg-accent-red)', border: '1px solid var(--border-secondary)', boxShadow: 'var(--shadow-light)', transition: 'all 0.2s' }}>
                                        Unmerge
                                      </span>
                                    </button>
                                  ) : null}
                                </td>
                              );

                              // Metrics summary (woeKey, matched metric, Dist Good %)
                              cells.push(
                                <td key={`metrics-${labelVal}-${idx}`} style={{ fontSize: '11px', whiteSpace: 'nowrap' }}>
                                  <div>
                                    <div style={{ color: matchedKey ? '#9ae6b4' : '#fca5a5' }}><strong>woeKey:</strong> {displayMatchedKey}</div>
                                    <div style={{ color: metricsBin ? '#c7d2fe' : '#fef3c7' }}><strong>metric:</strong> {displayMetricName}</div>
                                  </div>
                                </td>
                              );

                              return (
                                <tr
                                  key={`${labelVal}-${idx}`}
                                  className={`bin-row ${isSelected ? 'selected' : ''}`}
                                  style={{ backgroundColor: isMergedLabel ? 'var(--merged-bin-bg, #21262d)' : 'transparent' }}
                                  role="button"
                                  tabIndex={0}
                                  onClick={(e) => {
                                    const target = e.target as HTMLElement;
                                    if (target.closest('button') || target.closest('input') || target.closest('a')) return;
                                    toggleFineBinSelection(activeColumn, labelVal);
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      const target = e.target as HTMLElement;
                                      if (target.closest('button') || target.closest('input') || target.closest('a')) return;
                                      e.preventDefault();
                                      toggleFineBinSelection(activeColumn, labelVal);
                                    }
                                  }}
                                >
                                  {cells}
                                </tr>
                              );
                            })
                          )}
                        </tbody>
                        {/* === TOTALS ROW (Use authoritative data from backend) === */}
                        <tfoot>
                          {(() => {
                            // Calculate totals from authoritative backend data
                            let totalBad = 0;
                            let totalGood = 0;
                            let totalTotal = 0;
                            let sumFreq = 0;
                            let freqProvided = false;

                            let totalIvContribution = 0;
                            sortedRows.forEach((bin: any, idx: number) => {
                              const { labelValRaw, labelVal, rangeValue } = getBinIdentifiers(bin, idx);

                              const binMetrics = findBinMetric(labelValRaw, labelVal);
                              const woeTotalsRow = getWoeRow(labelVal, rangeValue, labelValRaw);

                              const good = Number(
                                binMetrics?.good_count ??
                                woeTotalsRow?.Good ??
                                0
                              );
                              const bad = Number(
                                binMetrics?.bad_count ??
                                woeTotalsRow?.Bad ??
                                0
                              );
                              const total = Number(
                                binMetrics?.total_count ??
                                woeTotalsRow?.Total ??
                                good + bad
                              );

                              const derived = computeDerivedStatsForCounts(good, bad, total);

                              totalBad += derived.badCount;
                              totalGood += derived.goodCount;
                              totalTotal += derived.totalCount;
                              totalIvContribution += derived.ivValue;

                              const freq = typeof bin['Freq%'] === 'number' ? bin['Freq%'] : (typeof bin.Freq === 'number' ? bin.Freq : null);
                              if (freq !== null) {
                                sumFreq += freq;
                                freqProvided = true;
                              }
                            });

                            const badRatePercent = totalTotal > 0 ? (totalBad / totalTotal) * 100 : 0;
                            const freqPercent = freqProvided ? sumFreq : (totalTotal > 0 ? 100 : 0);

                            // Calculate overall 0/1 ratio (Good/Bad)
                            const overallZeroOneRatio = totalBad > 0 ? totalGood / totalBad : 'Inf';
                            const totalIv = Number(totalIvContribution.toFixed(4));

                            return (
                              <tr className="totals-row">
                                <td><strong>Total</strong></td>
                                <td />
                                {isContinuousColumn ? (
                                  <>
                                    <td />
                                    <td />
                                  </>
                                ) : (
                                  <td />
                                )}
                                <td style={{ color: 'green', fontWeight: 'bold' }}>{totalGood}</td>
                                <td style={{ color: 'red', fontWeight: 'bold' }}>{totalBad}</td>
                                <td>{totalTotal}</td>
                                <td>{overallZeroOneRatio === 'Inf' ? 'Inf' : overallZeroOneRatio.toFixed(4)}</td>
                                <td>{badRatePercent.toFixed(2)}</td>
                                <td>{freqPercent.toFixed(2)}</td>

                                {/* 3 empty cells for G/B Odd, G/B Index, and Index */}
                                <td />
                                <td />
                                <td />

                                <td />
                                <td />
                                <td />
                                <td className="iv-total">{formatToFourDecimals(totalIv)}</td>
                                <td />
                                <td />
                              </tr>
                            );
                          })()}
                        </tfoot>
                      </table>
                    </div>

                    <div className="binning-controls">
                      <button
                        className="fine-bin-btn"
                        onClick={() => runBinning(activeColumn)}
                        aria-label={`Run binning for ${activeColumn}`}
                        disabled={selectedCount < 2}
                        title={selectedCount < 2 ? 'Select at least two bins to merge' : undefined}
                      >
                        Fine Binning on Selected
                      </button>
                      <button
                        className="auto-monotonic-btn"
                        onClick={() => runAutoMonotonicBinning(activeColumn)}
                        aria-label={`Run auto-monotonic binning for ${activeColumn}`}
                        title="Automatically merge bins to achieve monotonic WOE trend"
                      >
                        <span className="btn-icon">⚡</span>
                        Auto Monotonic Binning
                      </button>
                      <button
                        className="reset-bin-btn"
                        onClick={() => resetFineBinning(activeColumn)}
                        aria-label={`Reset binning for ${activeColumn}`}
                      >
                        Reset Binning
                      </button>
                    </div>
                  </div>

                  {/* WOE/IV Charts */}
                  {woeIvResults[activeColumn] && (
                    <div className="woe-iv-embedded" style={{ marginTop: '24px' }}>
                      <h3>WOE by Bin</h3>
                      <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={chartRows} margin={{ top: 20, right: 30, bottom: 40, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="Bin" angle={-30} textAnchor="end" interval={0} />
                          <YAxis />
                          <Tooltip />
                          <Legend />
                          <Line type="monotone" dataKey="WOE" stroke="#39ff14" strokeWidth={2} dot={{ r: 3, fill: '#39ff14' }} />
                        </LineChart>
                      </ResponsiveContainer>

                      <h3 style={{ marginTop: '20px' }}>IV Contribution by Bin</h3>
                      <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={chartRows} margin={{ top: 20, right: 30, bottom: 40, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="Bin" angle={-30} textAnchor="end" interval={0} />
                          <YAxis />
                          <Tooltip />
                          <Bar dataKey="IV" fill="#8884d8" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              );
            })()}
            {currentStep === 3 && (
              <div className="model-selection">
                {developerMode && (
                  <div className="model-buttons">
                    <button
                      className={`model-btn ${selectedModel === 'logistic' ? 'active' : ''}`}
                      onClick={() => setSelectedModel('logistic')}
                    >
                      Logistic Regression
                    </button>
                    <button
                      className={`model-btn ${selectedModel === 'random_forest' ? 'active' : ''}`}
                      onClick={() => setSelectedModel('random_forest')}
                    >
                      Random Forest
                    </button>
                    <button
                      className={`model-btn ${selectedModel === 'xgboost' ? 'active' : ''}`}
                      onClick={() => setSelectedModel('xgboost')}
                    >
                      XGBoost
                    </button>
                    <button
                      className={`model-btn ${selectedModel === 'stacking' ? 'active' : ''}`}
                      onClick={() => setSelectedModel('stacking')}
                    >
                      Stacking
                    </button>
                  </div>
                )}

                {selectedModel === 'logistic' && (
                  <LogisticRegressionResults
                    selectedVariables={currentStep === 3 && selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling}
                    allSelectedVariables={selectedColumns}
                    targetVariable={targetVariable}
                    woeTransformedData={Object.fromEntries(
                      Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
                    )}
                    onColumnSelect={(column) => setActiveColumn(column)}
                    onToggleSelect={toggleSelectedForFinalModeling}
                    selectedColumn={activeColumn}
                    onGenerateScoreCard={(modelType) => {
                      setSelectedModelForScorecard(modelType);
                      gotoScoreCardAndGenerate();
                    }}
                    generatingScoreCard={generatingScoreCard}
                    onGotoScoreCard={gotoScoreCardAndGenerate}
                    onResultsUpdate={handleLogisticResults}
                    recordId={recordId}
                    triggerRegression={triggerLogisticRegression}
                    initialResults={logisticResults}
                  />
                )}

                {selectedModel === 'random_forest' && (
                  <RandomForestResults
                    selectedVariables={currentStep === 3 && selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling}
                    allSelectedVariables={selectedColumns}
                    targetVariable={targetVariable}
                    woeTransformedData={Object.fromEntries(
                      Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
                    )}
                    onColumnSelect={(column) => setActiveColumn(column)}
                    onToggleSelect={toggleSelectedForFinalModeling}
                    selectedColumn={activeColumn}
                    onGenerateScoreCard={(modelType) => {
                      setSelectedModelForScorecard(modelType);
                      gotoScoreCardAndGenerate();
                    }}
                    generatingScoreCard={generatingScoreCard}
                    onGotoScoreCard={gotoScoreCardAndGenerate}
                    onResultsUpdate={handleRandomForestResults}
                    recordId={recordId}
                    triggerRegression={triggerRandomForest}
                    initialResults={randomForestResults}
                  />
                )}

                {selectedModel === 'xgboost' && (
                  <XGBoostResults
                    selectedVariables={currentStep === 3 && selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling}
                    allSelectedVariables={selectedColumns}
                    targetVariable={targetVariable}
                    woeTransformedData={Object.fromEntries(
                      Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
                    )}
                    onColumnSelect={(column) => setActiveColumn(column)}
                    onToggleSelect={toggleSelectedForFinalModeling}
                    selectedColumn={activeColumn}
                    onGenerateScoreCard={(modelType) => {
                      setSelectedModelForScorecard(modelType);
                      gotoScoreCardAndGenerate();
                    }}
                    generatingScoreCard={generatingScoreCard}
                    onGotoScoreCard={gotoScoreCardAndGenerate}
                    onResultsUpdate={handleXGBoostResults}
                    recordId={recordId}
                    triggerRegression={triggerXGBoost}
                    initialResults={xgboostResults}
                  />
                )}

                {selectedModel === 'stacking' && (
                  <StackingResults
                    selectedVariables={currentStep === 3 && selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling}
                    allSelectedVariables={selectedColumns}
                    targetVariable={targetVariable}
                    woeTransformedData={Object.fromEntries(
                      Object.entries(woeIvResults).map(([key, value]) => [key, value.stats || []])
                    )}
                    onColumnSelect={(column) => setActiveColumn(column)}
                    onToggleSelect={toggleSelectedForFinalModeling}
                    selectedColumn={activeColumn}
                    onGenerateScoreCard={(modelType) => {
                      setSelectedModelForScorecard(modelType);
                      gotoScoreCardAndGenerate();
                    }}
                    generatingScoreCard={generatingScoreCard}
                    onGotoScoreCard={gotoScoreCardAndGenerate}
                    onResultsUpdate={handleStackingResults}
                    recordId={recordId}
                    triggerRegression={triggerStacking}
                    initialResults={stackingResults}
                  />
                )}
              </div>
            )}
            {currentStep === 4 && (
              <>
                {/* Model Selection for Score Card - Outside main box */}
                {developerMode && (
                  <div className="scorecard-model-selection" style={{ marginBottom: '16px' }}>
                    <div className="model-buttons">
                      <button
                        className={`model-btn ${selectedModelForScorecard === 'logistic' ? 'active' : ''}`}
                        onClick={() => setSelectedModelForScorecard('logistic')}
                      >
                        Logistic Regression
                      </button>
                      <button
                        className={`model-btn ${selectedModelForScorecard === 'random_forest' ? 'active' : ''}`}
                        onClick={() => setSelectedModelForScorecard('random_forest')}
                      >
                        Random Forest
                      </button>
                      <button
                        className={`model-btn ${selectedModelForScorecard === 'xgboost' ? 'active' : ''}`}
                        onClick={() => setSelectedModelForScorecard('xgboost')}
                      >
                        XGBoost
                      </button>
                      <button
                        className={`model-btn ${selectedModelForScorecard === 'stacking' ? 'active' : ''}`}
                        onClick={() => setSelectedModelForScorecard('stacking')}
                      >
                        Stacking Ensemble
                      </button>
                    </div>
                  </div>
                )}

                <div className="scorecard-container">
                  {/* Left Box: Controls, Risk Scale, KS Chart */}
                  <div className="scorecard-middle-box">
                    {/* Score Range Toggle */}
                    <div className="scorecard-controls" style={{ marginBottom: '8px' }}>
                      <div style={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        gap: '12px',
                        padding: '8px 12px',
                        backgroundColor: 'var(--bg-secondary)',
                        borderRadius: '8px',
                        border: '1px solid var(--border-secondary)'
                      }}>
                        <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--fg-primary)' }}>Score Range:</span>
                        <div style={{ display: 'flex', gap: '4px' }}>
                          <button
                            onClick={() => setInvertScoreRange(false)}
                            style={{
                              padding: '6px 12px',
                              fontSize: '12px',
                              fontWeight: invertScoreRange ? 400 : 600,
                              backgroundColor: !invertScoreRange ? 'var(--fg-accent-green)' : 'var(--bg-tertiary)',
                              color: !invertScoreRange ? 'white' : 'var(--fg-secondary)',
                              border: 'none',
                              borderRadius: '6px',
                              cursor: 'pointer',
                              transition: 'all 0.2s'
                            }}
                            title="Standard: 0-600 (Higher score = Lower risk)"
                          >
                            0-600 ↑
                          </button>
                          <button
                            onClick={() => setInvertScoreRange(true)}
                            style={{
                              padding: '6px 12px',
                              fontSize: '12px',
                              fontWeight: invertScoreRange ? 600 : 400,
                              backgroundColor: invertScoreRange ? 'var(--fg-accent-red)' : 'var(--bg-tertiary)',
                              color: invertScoreRange ? 'white' : 'var(--fg-secondary)',
                              border: 'none',
                              borderRadius: '6px',
                              cursor: 'pointer',
                              transition: 'all 0.2s'
                            }}
                            title="Inverted: 600-0 (Higher score = Higher risk)"
                          >
                            600-0 ↓
                          </button>
                        </div>
                        <span style={{ 
                          fontSize: '11px', 
                          color: 'var(--fg-muted)',
                          fontStyle: 'italic'
                        }}>
                          {invertScoreRange 
                            ? '(Higher score = Higher risk)' 
                            : '(Higher score = Lower risk)'
                          }
                        </span>
                      </div>
                    </div>
                    <div className="scorecard-controls">
                      <button
                        className="auto-monotonic-btn scorecard-btn-small"
                        onClick={generateScoreCard}
                        disabled={generatingScoreCard || selectedForModeling.length === 0}
                        aria-label="Generate score card"
                      >
                        <span className="btn-icon">⚡</span>
                        {generatingScoreCard ? 'Generating...' : 'Generate Score Card'}
                      </button>
                      <button
                        className="auto-monotonic-btn scorecard-btn-small"
                        onClick={() => handleCreateRanges(selectedModelForScorecard)}
                        disabled={generatingScoreCard || createRangesLoading || !scoreCardData || !scoreCardData.scorecard_bins}
                        aria-label="Create ranges from training data"
                      >
                        <span className="btn-icon">⚡</span>
                        {createRangesLoading ? 'Creating...' : 'Create Ranges'}
                      </button>
                      <button
                        className="run-regression-btn scorecard-btn-small"
                        onClick={() => handleTestScoreCard(selectedModelForScorecard)}
                        disabled={generatingScoreCard || testScoreLoading || !scoreCardData || !scoreCardData.scorecard_bins}
                        aria-label="Test Score Card on Data"
                      >
                        {testScoreLoading ? 'Testing...' : 'Test Score Card'}
                      </button>
                    </div>
                    <div className="scorecard-controls scorecard-download-controls">
                      <button
                        className="run-regression-btn scorecard-btn-small"
                        onClick={handleDownloadScorecard}
                        disabled={!scoreCardData || !scoreCardData.scorecard_bins}
                        aria-label="Download score card"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '6px' }}>
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                          <polyline points="7 10 12 15 17 10"></polyline>
                          <line x1="12" y1="15" x2="12" y2="3"></line>
                        </svg>
                        Download Score Card
                      </button>
                    </div>

                        {/* Risk Scale */}
                        {((currentDataSource === 'training' && trainingScoreRiskBands && trainingScoreRiskBands.length > 0) || 
                          (currentDataSource === 'test' && testScoreRiskBands && testScoreRiskBands.length > 0)) && (
                          <div className="scorecard-risk-scale">
                            <h5 style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-primary)' }}>
                              Risk Scale ({currentDataSource === 'training' ? 'Training Data' : 'Test Data'})
                            </h5>
                            <div className="risk-bands-container">
                              {((currentDataSource === 'training' ? trainingScoreRiskBands : testScoreRiskBands) || []).map((band: any, idx: number) => (
                            <div 
                              key={idx} 
                              className="risk-band-item"
                              style={{ 
                                borderLeft: `4px solid ${band.color}`,
                                backgroundColor: `${band.color}15` // 15 = ~8% opacity
                              }}
                            >
                              <div className="risk-band-header">
                                <span className="risk-band-label" style={{ color: band.color }}>
                                  {band.label}
                                </span>
                                {band.description && (
                                  <span className="risk-band-desc">→ {band.description}</span>
                                )}
                              </div>
                              <div className="risk-band-range">
                                {Math.round(band.min)} - {Math.round(band.max)}
                              </div>
                              {band.bad_rate !== undefined && (
                                <div className="risk-band-stats">
                                  <span>Bad Rate: {band.bad_rate.toFixed(1)}%</span>
                                  <span>Count: {band.count}</span>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    
                    {/* KS Chart */}
                        {((currentDataSource === 'training' && trainingScoreKSData && trainingScoreKSData.ks_curve && trainingScoreKSData.ks_curve.length > 0) ||
                          (currentDataSource === 'test' && testScoreKSData && testScoreKSData.ks_curve && testScoreKSData.ks_curve.length > 0)) && (
                          <div className="scorecard-ks-chart">
                            <ScorecardKSChart 
                              ks_curve={(currentDataSource === 'training' ? trainingScoreKSData : testScoreKSData)?.ks_curve || []} 
                              ks_stat={(currentDataSource === 'training' ? trainingScoreKSData : testScoreKSData)?.ks_stat || 0}
                            />
                          </div>
                        )}
                  </div>

                  {/* Middle Box: Score Card (wider, scrollable) */}
                  <div className="scorecard-left-box">
                    {/* Show loading skeleton while generating */}
                    {generatingScoreCard && (
                      <div className="scorecard-results-loading">
                        <div className="scorecard-loading-skeleton">
                          <div className="skeleton-header" />
                          <div className="skeleton-row" />
                          <div className="skeleton-row" />
                          <div className="skeleton-row" />
                        </div>
                      </div>
                    )}

                    {/* Only show results when not generating and scoreCardData is loaded */}
                    {scoreCardData && !generatingScoreCard && (
                      <div className="scorecard-results">
                        <div className="table-container scorecard-scrollable">
                          <table className="scorecard-table" aria-label="Score card results">
                            <thead>
                              <tr>
                                <th>Bin #</th>
                                <th>Variable</th>
                                <th>Bin Range</th>
                                <th>WOE</th>
                                <th>
                                  {(selectedModelForScorecard === 'logistic' || selectedModelForScorecard === 'stacking')
                                    ? 'Coefficient (β)'
                                    : 'Feature Importance'}
                                </th>
                                <th>Score</th>
                              </tr>
                            </thead>
                            <tbody>
                              {scoreCardData.scorecard_bins && (() => {
                                const grouped: Record<string, any[]> = {};
                                const varsToUse = selectedForFinalModeling.length > 0 ? selectedForFinalModeling : selectedForModeling;
                                scoreCardData.scorecard_bins.forEach((b: any) => {
                                  if (varsToUse.includes(b.variable)) {
                                    grouped[b.variable] = grouped[b.variable] || [];
                                    grouped[b.variable].push(b);
                                  }
                                });
                                const rows: any[] = [];
                                Object.keys(grouped).forEach((variable, varIndex) => {
                                  const bins = grouped[variable];
                                  if (varIndex > 0) {
                                    rows.push(
                                      <tr key={`sep-${variable}`} className="variable-separator">
                                        <td colSpan={6} />
                                      </tr>
                                    );
                                  }
                                  for (let i = 0; i < bins.length; i++) {
                                    const bin = bins[i];
                                    rows.push(
                                      <tr key={`${variable}-${i}-${String(bin.bin_range)}`}>
                                        <td>{i + 1}</td>
                                        <td>{bin.variable}</td>
                                        <td>{bin.bin_range}</td>
                                        <td>{formatToFourDecimals(bin.woe)}</td>
                                        <td>
                                          {(selectedModelForScorecard === 'logistic' || selectedModelForScorecard === 'stacking')
                                            ? formatToFourDecimals(bin.coefficient)
                                            : formatToFourDecimals(bin.feature_importance)
                                          }
                                        </td>
                                        <td>{Math.round(bin.score)}</td>
                                      </tr>
                                    );
                                  }
                                });
                                return rows;
                              })()}
                            </tbody>
                          </table>
                        </div>
                        {/* Score Card Parameters - Individual Boxes */}
                        {scoreCardData.score_parameters && (
                          <div className="scorecard-parameters-boxes">
                            <div className="parameter-box">
                              <div className="parameter-label">Factor:</div>
                              <div className="parameter-value">{formatToFourDecimals(scoreCardData.score_parameters.factor)}</div>
                            </div>
                            <div className="parameter-box">
                              <div className="parameter-label">Offset:</div>
                              <div className="parameter-value">{formatToFourDecimals(scoreCardData.score_parameters.offset)}</div>
                            </div>
                            <div className="parameter-box">
                              <div className="parameter-label">Base Score (600 points):</div>
                              <div className="parameter-value">Good/Bad Odds 50:1</div>
                            </div>
                            <div className="parameter-box">
                              <div className="parameter-label">Score Range:</div>
                              <div className="parameter-value">
                                {scoreCardData.score_parameters.invert_score_range 
                                  ? `${scoreCardData.score_parameters.max_score} - ${scoreCardData.score_parameters.min_score}` 
                                  : `${scoreCardData.score_parameters.min_score} - ${scoreCardData.score_parameters.max_score}`
                                }
                                <span style={{ 
                                  fontSize: '10px', 
                                  marginLeft: '6px', 
                                  color: scoreCardData.score_parameters.invert_score_range ? 'var(--fg-accent-red)' : 'var(--fg-accent-green)',
                                  fontWeight: 500
                                }}>
                                  {scoreCardData.score_parameters.invert_score_range ? '(↓ risk)' : '(↑ good)'}
                                </span>
                              </div>
                            </div>
                            <div className="parameter-box">
                              <div className="parameter-label">Score Interpretation:</div>
                              <div className="parameter-value" style={{ 
                                fontSize: '12px',
                                color: scoreCardData.score_parameters.invert_score_range ? 'var(--fg-accent-red)' : 'var(--fg-accent-green)'
                              }}>
                                {scoreCardData.score_parameters.invert_score_range 
                                  ? 'Higher Score = Higher Risk' 
                                  : 'Higher Score = Lower Risk'
                                }
                              </div>
                            </div>
                            <div className="parameter-box">
                              <div className="parameter-label">Model Type:</div>
                              <div className="parameter-value">{selectedModelForScorecard.toUpperCase()}</div>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Right Box: Score Target Mapping (narrower) */}
                  <div className="scorecard-right-box">
                    {/* Score Results - Show training or test data based on currentDataSource */}
                    {((currentDataSource === 'training' && trainingScoreResults) || (currentDataSource === 'test' && testScoreResults)) && (
                      <div className="scorecard-test-results">
                        <div className="table-container scorecard-test-scrollable">
                          <table className="scorecard-table" aria-label="Score card results">
                            <thead>
                              <tr>
                                <th>#</th>
                                <th>Score</th>
                                <th>Target</th>
                              </tr>
                            </thead>
                            <tbody>
                              {((currentDataSource === 'training' ? trainingScoreResults : testScoreResults) || []).map((row: any, idx: number) => {
                                return (
                                  <tr key={idx}>
                                    <td>{idx + 1}</td>
                                    <td>{Math.round(row.score)}</td>
                                    <td style={{
                                      color: row.target === 0 ? '#2ea043' : row.target === 1 ? '#da3633' : undefined,
                                      fontWeight: row.target === 1 ? 'bold' : 'normal'
                                    }}>
                                      {row.target}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
          </section>
        </div >
        {/* Footer navigation removed per request: Next and Save moved beside progress bar */}

      </div >
    </div >
  );
};

// KS Chart component for Scorecard
interface ScorecardKSChartProps {
  ks_curve: Array<{ threshold: number | null; tpr: number | null; fpr: number | null; diff: number | null }>;
  ks_stat: number;
}

const ScorecardKSChart: React.FC<ScorecardKSChartProps> = ({ ks_curve, ks_stat }) => {
  if (!ks_curve || ks_curve.length === 0) return null;

  const _fmt = (n: number | null, d = 4) => n !== null ? Number(n).toFixed(d) : '0.0000';

  // Responsive sizing - use viewBox for scalability
  const width = 420;
  const height = 280;
  const margin = 35;
  const plotW = width - margin * 2;
  const plotH = height - margin * 2;

  // Filter out null values and create points
  const validCurve = ks_curve.filter(p => p.threshold !== null && p.tpr !== null && p.fpr !== null);
  if (validCurve.length === 0) return null;

  // Normalize thresholds to 0-1 range for plotting
  const thresholds = validCurve.map(p => p.threshold!);
  const minThresh = Math.min(...thresholds);
  const maxThresh = Math.max(...thresholds);
  const threshRange = maxThresh - minThresh || 1;

  const points = validCurve.map(p => ({
    x: margin + ((p.threshold! - minThresh) / threshRange) * plotW,
    fpr: margin + (1 - (p.fpr || 0)) * plotH,
    tpr: margin + (1 - (p.tpr || 0)) * plotH,
    diff: p.diff || 0,
    threshold: p.threshold!
  }));

  // Find max diff index
  const ksIndex = validCurve.reduce((acc, cur, idx) => 
    (cur.diff !== null && cur.diff > (validCurve[acc]?.diff || 0)) ? idx : acc, 0
  );
  const ksPoint = points[ksIndex];

  // Create paths
  const tprPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.tpr}`).join(' ');
  const fprPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.fpr}`).join(' ');

  return (
    <div className="ks-chart-container">
      <h5 style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-primary)' }}>KS Statistics</h5>
      <div className="ks-graph-wrapper">
        <svg viewBox={`0 0 ${width} ${height}`} className="roc-svg" preserveAspectRatio="xMidYMid meet">
        {/* Axes */}
        <line x1={margin} y1={margin} x2={margin} y2={margin + plotH} stroke="#f0f6fc" strokeWidth={1} />
        <line x1={margin} y1={margin + plotH} x2={margin + plotW} y2={margin + plotH} stroke="#f0f6fc" strokeWidth={1} />
        
        {/* Grid lines */}
        {[0, 0.2, 0.4, 0.6, 0.8, 1.0].map(val => (
          <g key={val}>
            <line
              x1={margin + val * plotW}
              y1={margin}
              x2={margin + val * plotW}
              y2={margin + plotH}
              stroke="#30363d"
              strokeWidth={0.5}
            />
            <line
              x1={margin}
              y1={margin + val * plotH}
              x2={margin + plotW}
              y2={margin + val * plotH}
              stroke="#30363d"
              strokeWidth={0.5}
            />
          </g>
        ))}
        
        {/* Paths */}
        <path d={tprPath} fill="none" stroke="#52c41a" strokeWidth={2} />
        <path d={fprPath} fill="none" stroke="#ff4d4f" strokeWidth={2} />
        
        {/* KS marker */}
        {ksPoint && (
          <g>
            <line 
              x1={ksPoint.x} 
              y1={margin} 
              x2={ksPoint.x} 
              y2={margin + plotH} 
              stroke="#58a6ff" 
              strokeDasharray="4,4" 
              strokeWidth={1.5}
            />
            <text 
              x={ksPoint.x} 
              y={margin - 8} 
              textAnchor="middle" 
              fill="#58a6ff" 
              fontSize="11"
              fontWeight="600"
            >
              KS={_fmt(ks_stat, 4)}
            </text>
          </g>
        )}
        
        {/* Labels */}
        <text x={margin + plotW / 2} y={height - 5} textAnchor="middle" fill="#8b949e" fontSize="10">Threshold</text>
        <text 
          x={10} 
          y={margin + plotH / 2} 
          textAnchor="middle" 
          fill="#8b949e" 
          fontSize="10"
          transform={`rotate(-90, 10, ${margin + plotH / 2})`}
        >
          Cumulative Distribution
        </text>
        
        {/* Legend */}
        <g transform={`translate(${margin + plotW - 100}, ${margin + 20})`}>
          <line x1={0} y1={0} x2={20} y2={0} stroke="#52c41a" strokeWidth={2} />
          <text x={25} y={4} fill="#f0f6fc" fontSize="10">TPR (Good)</text>
          <line x1={0} y1={15} x2={20} y2={15} stroke="#ff4d4f" strokeWidth={2} />
          <text x={25} y={19} fill="#f0f6fc" fontSize="10">FPR (Bad)</text>
        </g>
      </svg>
      </div>
    </div>
  );
};

export default SelectedColumnsPage;
