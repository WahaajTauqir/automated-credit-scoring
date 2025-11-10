# System Architecture: Automated Monotonic Binning

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         FRONTEND                             │
│                    (React + TypeScript)                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────────────────────────────────┐     │
│  │  SelectedColumnsPage.tsx                          │     │
│  │  ┌─────────────────────────────────────────────┐ │     │
│  │  │  Column Card (age, income, etc.)            │ │     │
│  │  │  Click → Shows Binning Table                │ │     │
│  │  └─────────────────────────────────────────────┘ │     │
│  │                                                    │     │
│  │  ┌─────────────────────────────────────────────┐ │     │
│  │  │  Binning Table                              │ │     │
│  │  │  - Bin labels, Good/Bad counts              │ │     │
│  │  │  - WOE, IV values                           │ │     │
│  │  │  - G/B metrics                              │ │     │
│  │  └─────────────────────────────────────────────┘ │     │
│  │                                                    │     │
│  │  ┌─────────────────────────────────────────────┐ │     │
│  │  │  Binning Controls                           │ │     │
│  │  │  [Fine Binning on Selected]    (Green)     │ │     │
│  │  │  [⚡ Auto Monotonic Binning]   (Purple)    │ │     │
│  │  │  [Reset Binning]                (Red)       │ │     │
│  │  └─────────────────────────────────────────────┘ │     │
│  └───────────────────────────────────────────────────┘     │
│                           │                                  │
└───────────────────────────┼──────────────────────────────────┘
                            │
                    HTTP POST Request
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                         BACKEND                              │
│                      (Flask + Python)                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────────────────────────────────┐     │
│  │  app.py                                           │     │
│  │  /api/auto-monotonic-binning                      │     │
│  │                                                    │     │
│  │  1. Parse request                                 │     │
│  │  2. Load uploaded.csv                             │     │
│  │  3. Run coarse binning                            │     │
│  │  4. Extract Good/Bad counts                       │     │
│  │  5. Call auto_monotonic_binning()                 │     │
│  │  6. Apply merges via fine binning                 │     │
│  │  7. Save to database                              │     │
│  │  8. Return results                                │     │
│  └───────────────────────────────────────────────────┘     │
│                           │                                  │
│                           ▼                                  │
│  ┌───────────────────────────────────────────────────┐     │
│  │  auto_monotonic_binning.py                        │     │
│  │                                                    │     │
│  │  auto_monotonic_binning()                         │     │
│  │  ├─ greedy_merge_bins_woe()                       │     │
│  │  │  └─ Iteratively merge violations              │     │
│  │  ├─ exhaustive_merge_bins_woe()                   │     │
│  │  │  └─ Try multiple strategies                   │     │
│  │  ├─ compute_woe()                                 │     │
│  │  └─ is_monotonic()                                │     │
│  └───────────────────────────────────────────────────┘     │
│                           │                                  │
│                           ▼                                  │
│  ┌───────────────────────────────────────────────────┐     │
│  │  db.py                                            │     │
│  │  - save_finebin_details_db()                      │     │
│  │  - upsert_single_record_db()                      │     │
│  └───────────────────────────────────────────────────┘     │
│                           │                                  │
└───────────────────────────┼──────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                       DATABASE                               │
│                      (PostgreSQL)                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────────────────────────────────┐     │
│  │  records                                          │     │
│  │  - id (PK)                                        │     │
│  │  - dataset_path                                   │     │
│  │  - selected_columns                               │     │
│  │  - woe_iv_results                                 │     │
│  │  - ...                                            │     │
│  └───────────────────────────────────────────────────┘     │
│                                                              │
│  ┌───────────────────────────────────────────────────┐     │
│  │  finebin_details                                  │     │
│  │  - id (PK)                                        │     │
│  │  - record_id (FK)                                 │     │
│  │  - column_name                                    │     │
│  │  - group_id                                       │     │
│  │  - merged_bins (JSON)                             │     │
│  └───────────────────────────────────────────────────┘     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Detailed Flow Diagram

```
USER ACTION                    FRONTEND                    BACKEND                     ALGORITHM
    │                             │                          │                            │
    │ Click "⚡ Auto             │                          │                            │
    │ Monotonic Binning"         │                          │                            │
    ├──────────────────────────►│                          │                            │
    │                             │                          │                            │
    │                             │ showNotification()       │                            │
    │                             │ "Running auto-binning"   │                            │
    │                             │                          │                            │
    │                             │ POST /api/auto-...       │                            │
    │                             ├─────────────────────────►│                            │
    │                             │ {                        │                            │
    │                             │   variable: "age",       │                            │
    │                             │   target: "default",     │                            │
    │                             │   type: "continuous",    │                            │
    │                             │   method: "greedy"       │                            │
    │                             │ }                        │                            │
    │                             │                          │                            │
    │                             │                          │ Parse request              │
    │                             │                          │ Load CSV                   │
    │                             │                          │ Run coarse_bin_...()       │
    │                             │                          │                            │
    │                             │                          │ auto_monotonic_binning()   │
    │                             │                          ├───────────────────────────►│
    │                             │                          │                            │
    │                             │                          │                            │ Calculate initial WOE
    │                             │                          │                            │ [1.2, 0.8, 0.9, 0.3, -0.2]
    │                             │                          │                            │
    │                             │                          │                            │ Check monotonic?
    │                             │                          │                            │ No (0.8 → 0.9 violation)
    │                             │                          │                            │
    │                             │                          │                            │ Find first violation (i=1)
    │                             │                          │                            │ Merge bins[1] + bins[2]
    │                             │                          │                            │
    │                             │                          │                            │ New WOE: [1.2, 0.85, 0.3, -0.2]
    │                             │                          │                            │
    │                             │                          │                            │ Check monotonic?
    │                             │                          │                            │ Yes! ✓
    │                             │                          │                            │
    │                             │                          │ ◄──────────────────────────┤
    │                             │                          │ {                          │
    │                             │                          │   merged_good: [...],      │
    │                             │                          │   merged_bad: [...],       │
    │                             │                          │   merge_mapping: {...},    │
    │                             │                          │   is_monotonic: true,      │
    │                             │                          │   num_merges: 1            │
    │                             │                          │ }                          │
    │                             │                          │                            │
    │                             │                          │ Apply via fine_bin_...()   │
    │                             │                          │ Save to finebin_details    │
    │                             │                          │ Calculate WOE/IV           │
    │                             │                          │                            │
    │                             │ ◄────────────────────────┤                            │
    │                             │ {                        │                            │
    │                             │   success: true,         │                            │
    │                             │   stats: [...],          │                            │
    │                             │   bin_merges: {...},     │                            │
    │                             │   is_monotonic: true,    │                            │
    │                             │   num_merges: 1          │                            │
    │                             │ }                        │                            │
    │                             │                          │                            │
    │                             │ Update UI:               │                            │
    │                             │ - setFineBinResults()    │                            │
    │                             │ - setBinMergeHistory()   │                            │
    │                             │ - calculateMetrics()     │                            │
    │                             │ - fetchWoeIv()           │                            │
    │                             │                          │                            │
    │ ◄──────────────────────────┤                          │                            │
    │ See updated table           │                          │                            │
    │ See success notification    │                          │                            │
    │ "1 merge performed..."      │                          │                            │
    │                             │                          │                            │
```

## Component Interaction

```
┌──────────────────────────────────────────────────────────────┐
│                    COMPONENT HIERARCHY                        │
└──────────────────────────────────────────────────────────────┘

App.tsx
  └─ SelectedColumnsPage.tsx
       ├─ Navbar
       ├─ Progress Header
       │    ├─ Step 1: Column Selection & Binning ← WE ARE HERE
       │    ├─ Step 2: Logistic Regression
       │    └─ Step 3: Score Card
       │
       ├─ Column Selection Panel (Sidebar)
       │    └─ Column Cards (age, income, etc.)
       │         └─ Checkbox for modeling
       │
       └─ Content Section
            └─ Binning Section (when column selected)
                 ├─ Binning Table
                 │    ├─ Headers (Bin, Min, Max, Good, Bad, WOE, IV, ...)
                 │    ├─ Data Rows (sortable, clickable)
                 │    └─ Totals Row
                 │
                 ├─ Binning Controls
                 │    ├─ [Fine Binning on Selected]
                 │    ├─ [⚡ Auto Monotonic Binning] ← NEW BUTTON
                 │    └─ [Reset Binning]
                 │
                 └─ WOE/IV Charts
                      ├─ WOE by Bin (Line Chart)
                      └─ IV Contribution (Bar Chart)
```

## Data Flow

```
┌────────────────┐
│  uploaded.csv  │
└────────┬───────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│  COARSE BINNING                                        │
│  - Equal frequency (qcut) for continuous               │
│  - Bad rate grouping for discrete                      │
│  Result: 10-20 initial bins                            │
└────────┬───────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│  FINE BINNING (Manual)                                 │
│  - User selects bins                                   │
│  - Click "Fine Binning on Selected"                    │
│  - Merges selected bins                                │
└────────┬───────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│  AUTO MONOTONIC BINNING (New!)                         │
│  - Click "⚡ Auto Monotonic Binning"                   │
│  - Algorithm finds optimal merges                      │
│  - Achieves monotonicity automatically                 │
└────────┬───────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│  WOE/IV CALCULATION                                    │
│  - Calculate WOE for each bin                          │
│  - Calculate IV contribution                           │
│  - Verify monotonicity                                 │
└────────┬───────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│  DATABASE STORAGE                                      │
│  - Save bin merges to finebin_details                  │
│  - Update records with WOE/IV results                  │
│  - Preserve for later use                              │
└────────┬───────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│  MODEL BUILDING                                        │
│  - Use WOE-transformed features                        │
│  - Build logistic regression                           │
│  - Generate scorecard                                  │
└────────────────────────────────────────────────────────┘
```

## Algorithm Decision Tree

```
                    Start Auto-Binning
                            │
                            ▼
                  ┌─────────────────────┐
                  │ Calculate Initial   │
                  │ WOE values          │
                  └──────────┬──────────┘
                            │
                            ▼
                  ┌─────────────────────┐
                  │ Auto-detect         │
          ┌───────┤ Direction?          ├───────┐
          │       └─────────────────────┘       │
          │ Correlation > 0    Correlation < 0  │
          ▼                                     ▼
    Increasing                            Decreasing
          │                                     │
          └──────────────┬──────────────────────┘
                         │
                         ▼
                  ┌─────────────────────┐
                  │ Is already          │
            ┌─────┤ monotonic?          ├─────┐
            │     └─────────────────────┘     │
           Yes                               No
            │                                 │
            ▼                                 ▼
    ┌─────────────────┐         ┌─────────────────────┐
    │ Return original │         │ Find first          │
    │ bins            │         │ violation           │
    │ (0 merges)      │         └──────────┬──────────┘
    └─────────────────┘                    │
                                           ▼
                              ┌─────────────────────┐
                              │ Variable Type?      │
                        ┌─────┴─────────────────────┴─────┐
                        │                                 │
                   Continuous                        Discrete
                        │                                 │
                        ▼                                 ▼
            ┌───────────────────────┐       ┌───────────────────────┐
            │ Merge adjacent bins   │       │ Merge with best       │
            │ (i and i+1)           │       │ matching bin          │
            └───────────┬───────────┘       └───────────┬───────────┘
                        │                                 │
                        └──────────────┬──────────────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │ Recalculate WOE     │
                            └──────────┬──────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │ Is now monotonic?   │
                      ┌─────┴─────────────────────┴─────┐
                     Yes                               No
                      │                                 │
                      ▼                                 ▼
            ┌─────────────────┐           ┌─────────────────────┐
            │ Return merged   │           │ Continue merging    │
            │ bins            │           │ (goto Find first    │
            │                 │           │  violation)         │
            └─────────────────┘           └─────────────────────┘
```

## State Management Flow

```
React State Variables:

selectedColumns: string[]
  └─ All selected column names

activeColumn: string
  └─ Currently active column being viewed

fineBinResults: Record<string, any[]>
  └─ { "age": [...bins], "income": [...bins] }

binMergeHistory: Record<string, Record<string, any[]>>
  └─ { "age": { "Merged_1": ["Bin_2", "Bin_3"] } }

woeIvResults: Record<string, any>
  └─ { "age": { iv: 0.45, stats: [...] } }

binScoringMetrics: Record<string, any[]>
  └─ { "age": [{ bin_name: "Bin_1", gb_odd: 150, ... }] }

When "⚡ Auto Monotonic Binning" clicked:
  1. showNotification("Running...")
  2. API call to backend
  3. Backend returns merged bins
  4. Update fineBinResults[activeColumn] = new_stats
  5. Update binMergeHistory[activeColumn] = new_merges
  6. Call calculateAllBinMetrics(activeColumn, new_stats)
  7. Call fetchWoeIv(activeColumn, new_merges)
  8. Update woeIvResults[activeColumn] = new_woe_iv
  9. showNotification("Success: X merges...")
  10. React re-renders with new data
```

## Error Handling Flow

```
                User clicks button
                        │
                        ▼
                ┌────────────────┐
                │ Frontend       │
                │ validation     │
                └────────┬───────┘
                         │
            ┌────────────┴────────────┐
            │                         │
       Valid Input              Invalid Input
            │                         │
            ▼                         ▼
    Send to backend          Show error notification
            │                   "Missing required data"
            ▼
    ┌────────────────┐
    │ Backend        │
    │ validation     │
    └────────┬───────┘
             │
    ┌────────┴────────┐
    │                 │
Valid Data      Invalid Data
    │                 │
    ▼                 ▼
Run algorithm    Return 400 error
    │              "Missing fields"
    │                 │
    ▼                 └─────────────┐
┌────────────────┐                 │
│ Algorithm      │                 │
│ execution      │                 │
└────────┬───────┘                 │
         │                         │
    ┌────┴────┐                    │
    │         │                    │
Success    Error                   │
    │         │                    │
    ▼         ▼                    │
Return     Return 500              │
results    error                   │
    │      "Algorithm              │
    │       failed"                │
    │         │                    │
    └────┬────┴────────────────────┘
         │
         ▼
    Frontend receives response
         │
    ┌────┴────┐
    │         │
Success    Error
    │         │
    ▼         ▼
Update     Show error
UI         notification
```

---

This architecture ensures:
✅ Clean separation of concerns
✅ Robust error handling
✅ Efficient data flow
✅ Maintainable code structure
✅ Scalable for future enhancements
