# Preprocessing Debug Logs

## ✅ Added Comprehensive Debug Logging

Debug logs have been added to the data preprocessing section to show row counts for each column at every stage of preprocessing.

## 📊 Debug Information Provided

### 1. **Column Row Counts Table**
At each preprocessing stage, you'll see a detailed table showing:
- **Column Name**: Name of each column
- **Non-Null Rows**: Number of rows with non-null values
- **Null Rows**: Number of rows with null/missing values
- **Null %**: Percentage of null values

### 2. **Stage-by-Stage Debug Output**

The preprocessing pipeline now logs detailed information at:

#### **Initial State**
- Total rows and columns before any preprocessing
- Per-column row counts and null percentages

#### **After Type Detection**
- Number of discrete vs continuous columns identified

#### **Before/After Missing Value Handling**
- Columns removed (with reasons)
- Missing values treated per column
- Method used for each column (Mode, Median, Missing category)
- Total columns remaining

#### **Before/After Duplicate Removal**
- Number of duplicate rows removed
- Row count before and after

#### **Before/After Outlier Handling**
- Outliers detected per continuous column
- Percentage of outliers per column
- Total outliers handled

#### **Before/After Categorical Encoding**
- Number of categories encoded per column
- Columns skipped (e.g., target variable)

#### **Final State**
- Total rows and columns after all preprocessing
- Per-column row counts and null percentages

## 🔍 Example Debug Output

```
================================================================================
[PREPROCESSING DEBUG] INITIAL STATE (Before Preprocessing)
================================================================================
Total Rows: 10000
Total Columns: 25

Row Counts Per Column:
Column Name                   Non-Null Rows        Null Rows            Null %         
-------------------------------------------------------------------------------------
age                           9500                 500                  5.00%
income                        9200                 800                  8.00%
credit_score                  10000                0                    0.00%
...
================================================================================

[HANDLE_MISSING] Starting with 10000 rows, 25 columns
[HANDLE_MISSING] Missing threshold: 50.0%
[HANDLE_MISSING] Treat -1 as missing: True
[HANDLE_MISSING] Removing 2 columns with >50.0% missing:
  - column_x: 60.0% missing (6000 rows)
  - column_y: 55.0% missing (5500 rows)
[HANDLE_MISSING] After column removal: 23 columns remain (8 discrete, 15 continuous)
[HANDLE_MISSING] Discrete column 'category_col': Filled 200 missing values (2.00%) using Mode (1)
[HANDLE_MISSING] Continuous column 'income': Filled 800 missing values (8.00%) using Median (45000.0000)
[HANDLE_MISSING] Completed: 10000 rows, 23 columns

================================================================================
[PREPROCESSING DEBUG] AFTER Missing Value Handling
================================================================================
Total Rows: 10000
Total Columns: 23

Row Counts Per Column:
Column Name                   Non-Null Rows        Null Rows            Null %         
-------------------------------------------------------------------------------------
age                           10000                0                    0.00%
income                        10000                0                    0.00%
...
================================================================================

[REMOVE_DUPLICATES] Starting with 10000 rows, 23 columns
[REMOVE_DUPLICATES] Removed 150 duplicate rows (10000 → 9850 rows, 1.50% reduction)

================================================================================
[PREPROCESSING DEBUG] AFTER Duplicate Removal
================================================================================
Total Rows: 9850
Total Columns: 23
...
```

## 📍 Where Debug Logs Appear

All debug logs are printed to:
- **Backend console/terminal** (where Flask app is running)
- **Backend log file** (if logging to file is configured)

## 🎯 Benefits

1. **Transparency**: See exactly what happens to each column at each step
2. **Debugging**: Quickly identify which columns lose rows or have issues
3. **Verification**: Verify that preprocessing steps are working correctly
4. **Data Quality**: Monitor data quality throughout the pipeline
5. **Troubleshooting**: Easily spot where data loss or issues occur

## 🔧 Functions Modified

1. **`preprocess_dataset()`** - Main preprocessing function
   - Added debug logs at start, after each step, and at end

2. **`handle_missing_values()`** - Missing value handling
   - Logs columns removed, missing values filled per column

3. **`remove_duplicates()`** - Duplicate removal
   - Logs number of duplicates removed

4. **`handle_outliers()`** - Outlier handling
   - Logs outliers detected and handled per column

5. **`encode_categorical_variables()`** - Categorical encoding
   - Logs encoding details per column

6. **`_debug_print_column_row_counts()`** - New helper function
   - Formats and prints column row count tables

## 📝 Usage

Debug logs are automatically enabled. When you run preprocessing:
1. Start your backend server
2. Trigger preprocessing (via API or frontend)
3. Check the backend console/terminal for detailed debug output

## 🎨 Output Format

- **Section Headers**: Clear separators with `===` lines
- **Column Tables**: Formatted tables with aligned columns
- **Step Logs**: Tagged with `[FUNCTION_NAME]` for easy filtering
- **Percentages**: Shown with 2 decimal places
- **Counts**: Shown as integers

## 💡 Tips

- Use `grep` to filter specific stages: `grep "PREPROCESSING DEBUG" backend.log`
- Use `grep` to filter specific functions: `grep "HANDLE_MISSING" backend.log`
- The debug output is verbose - redirect to a file if needed: `python app.py > preprocessing_debug.log 2>&1`

