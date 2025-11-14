"""
ARCHIVED: legacy DB helper module (db_old.py)

This module has been archived. Use `backend/db.py` for normalized database
operations (datasets, features, binning_steps, bins, merged_bins,
binning_totals). The legacy JSON-blob helpers were removed to prevent
storing structured objects as strings.
"""

def _archived_import_error():
    raise RuntimeError("The legacy module 'db_old' has been archived. Use 'backend/db.py' instead.")

_archived_import_error()