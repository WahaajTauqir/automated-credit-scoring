"""
Cloud Storage Manager for Google Cloud Platform

This module provides a unified interface for file storage that works both locally
and with Google Cloud Storage. It automatically detects if Cloud Storage is
configured and uses it when available, falling back to local filesystem otherwise.
"""

import os
import tempfile
from typing import Optional
from pathlib import Path

# Try to import Google Cloud Storage
try:
    from google.cloud import storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    storage = None


class CloudStorageManager:
    """Manages file storage with automatic fallback to local filesystem."""
    
    def __init__(self):
        self.uploads_bucket = os.getenv('GCS_UPLOADS_BUCKET')
        self.artifacts_bucket = os.getenv('GCS_ARTIFACTS_BUCKET')
        self.use_gcs = GCS_AVAILABLE and (self.uploads_bucket or self.artifacts_bucket)
        
        if self.use_gcs:
            try:
                self.client = storage.Client()
                print(f"[STORAGE] Initialized Cloud Storage Manager")
                print(f"[STORAGE]   Uploads bucket: {self.uploads_bucket}")
                print(f"[STORAGE]   Artifacts bucket: {self.artifacts_bucket}")
            except Exception as e:
                print(f"[STORAGE] Warning: Failed to initialize GCS client: {e}")
                print(f"[STORAGE] Falling back to local filesystem")
                self.use_gcs = False
                self.client = None
        else:
            self.client = None
            if not GCS_AVAILABLE:
                print(f"[STORAGE] Google Cloud Storage not available (package not installed)")
            else:
                print(f"[STORAGE] Cloud Storage buckets not configured, using local filesystem")
    
    def upload_file(self, local_path: str, bucket_name: str, blob_name: str) -> str:
        """
        Upload a file to Cloud Storage or return local path.
        
        Parameters:
        -----------
        local_path : str
            Path to local file
        bucket_name : str
            Name of the bucket (or 'uploads'/'artifacts' for local)
        blob_name : str
            Name/path for the blob in the bucket
        
        Returns:
        --------
        str : URL or path to the uploaded file
        """
        if not self.use_gcs or not bucket_name:
            # Local filesystem - just return the path
            return local_path
        
        # Validate local file exists
        if not os.path.exists(local_path):
            print(f"[STORAGE] Error: Local file does not exist: {local_path}")
            return local_path
        
        try:
            bucket = self.client.bucket(bucket_name)
            # Check if bucket exists
            if not bucket.exists():
                print(f"[STORAGE] Error: Bucket does not exist: {bucket_name}")
                print(f"[STORAGE] Falling back to local path")
                return local_path
            
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(local_path)
            print(f"[STORAGE] Successfully uploaded {local_path} to gs://{bucket_name}/{blob_name}")
            return f"gs://{bucket_name}/{blob_name}"
        except Exception as e:
            print(f"[STORAGE] Error uploading to GCS: {e}")
            import traceback
            traceback.print_exc()
            print(f"[STORAGE] Falling back to local path")
            return local_path
    
    def download_file(self, bucket_name: str, blob_name: str, local_path: str) -> bool:
        """
        Download a file from Cloud Storage to local path.
        
        Parameters:
        -----------
        bucket_name : str
            Name of the bucket or 'gs://' path
        blob_name : str
            Name/path of the blob
        local_path : str
            Local path to save the file
        
        Returns:
        --------
        bool : True if successful, False otherwise
        """
        # Handle gs:// paths
        if blob_name.startswith('gs://'):
            parts = blob_name[5:].split('/', 1)
            bucket_name = parts[0]
            blob_name = parts[1] if len(parts) > 1 else ''
        
        if not self.use_gcs or not bucket_name:
            # Local filesystem - check if file exists
            if os.path.exists(blob_name):
                import shutil
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                shutil.copy2(blob_name, local_path)
                return True
            return False
        
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            
            # Create directory if needed
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            blob.download_to_filename(local_path)
            return True
        except Exception as e:
            print(f"[STORAGE] Error downloading from GCS: {e}")
            return False
    
    def file_exists(self, path: str) -> bool:
        """
        Check if a file exists (in GCS or local filesystem).
        
        Parameters:
        -----------
        path : str
            File path (can be gs:// path or local path)
        
        Returns:
        --------
        bool : True if file exists
        """
        # Handle gs:// paths
        if path.startswith('gs://'):
            try:
                parts = path[5:].split('/', 1)
                bucket_name = parts[0]
                blob_name = parts[1] if len(parts) > 1 else ''
                
                if not self.use_gcs:
                    return False
                
                bucket = self.client.bucket(bucket_name)
                blob = bucket.blob(blob_name)
                return blob.exists()
            except Exception:
                return False
        
        # Local filesystem
        return os.path.exists(path)
    
    def get_file_url(self, bucket_name: str, blob_name: str) -> str:
        """
        Get a public URL for a file in Cloud Storage.
        
        Parameters:
        -----------
        bucket_name : str
            Name of the bucket
        blob_name : str
            Name/path of the blob
        
        Returns:
        --------
        str : Public URL or local path
        """
        if not self.use_gcs or not bucket_name:
            return blob_name
        
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            return blob.public_url
        except Exception:
            return blob_name
    
    def save_to_temp(self, bucket_name: str, blob_name: str) -> Optional[str]:
        """
        Download a file from GCS to a temporary local file.
        
        Parameters:
        -----------
        bucket_name : str
            Name of the bucket or gs:// path
        blob_name : str
            Name/path of the blob
        
        Returns:
        --------
        str : Path to temporary file, or None if failed
        """
        # Handle gs:// paths
        if blob_name.startswith('gs://'):
            path = blob_name
        elif bucket_name and bucket_name.startswith('gs://'):
            path = f"{bucket_name}/{blob_name}"
        else:
            path = blob_name
        
        if path.startswith('gs://'):
            # Download from GCS
            parts = path[5:].split('/', 1)
            bucket_name = parts[0]
            blob_name = parts[1] if len(parts) > 1 else ''
            
            if not self.use_gcs:
                return None
            
            try:
                # Validate bucket exists
                bucket = self.client.bucket(bucket_name)
                if not bucket.exists():
                    print(f"[STORAGE] Error: Bucket does not exist: {bucket_name}")
                    return None
                
                # Check if blob exists
                blob = bucket.blob(blob_name)
                if not blob.exists():
                    print(f"[STORAGE] Error: Blob does not exist: gs://{bucket_name}/{blob_name}")
                    return None
                
                # Create temp file
                suffix = Path(blob_name).suffix if blob_name else '.tmp'
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp_path = tmp.name
                
                if self.download_file(bucket_name, blob_name, tmp_path):
                    return tmp_path
                else:
                    # Clean up temp file if download failed
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass
                return None
            except Exception as e:
                print(f"[STORAGE] Error downloading to temp: {e}")
                import traceback
                traceback.print_exc()
                return None
        else:
            # Local file - return as-is if exists
            if os.path.exists(path):
                return path
            return None


# Global storage manager instance
_storage_manager: Optional[CloudStorageManager] = None


def get_storage_manager() -> CloudStorageManager:
    """Get or create the global storage manager instance."""
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = CloudStorageManager()
    return _storage_manager

