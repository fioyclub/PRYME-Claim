"""
Lazy Client Manager for Google API clients
Implements lazy loading to reduce memory usage during startup
"""

import logging
import gc
from typing import Optional
from config import Config
from sheets_client import SheetsClient
from drive_client import DriveClient

logger = logging.getLogger(__name__)


class LazyClientManager:
    """
    Manages Google API clients with lazy loading to reduce startup memory usage
    """
    
    def __init__(self, config: Config):
        """
        Initialize the lazy client manager
        
        Args:
            config: Configuration instance
        """
        self.config = config
        self._sheets_client: Optional[SheetsClient] = None
        self._drive_client: Optional[DriveClient] = None
        self._initialization_lock = False
        
        logger.info("LazyClientManager initialized - clients will be loaded on demand")
    
    def get_sheets_client(self) -> SheetsClient:
        """
        Get Google Sheets client, initializing if necessary
        
        Returns:
            SheetsClient instance
        """
        if self._sheets_client is None:
            self._initialize_sheets_client()
        return self._sheets_client
    
    def get_drive_client(self) -> DriveClient:
        """
        Get Google Drive client, initializing if necessary
        
        Returns:
            DriveClient instance
        """
        if self._drive_client is None:
            self._initialize_drive_client()
        return self._drive_client
    
    def _initialize_sheets_client(self):
        """Initialize Google Sheets client with memory monitoring"""
        if self._initialization_lock:
            return
        
        try:
            self._initialization_lock = True
            logger.info("Lazy loading Google Sheets client...")
            
            # Create token.json if it doesn't exist
            self._ensure_token_file()
            
            # Initialize with memory monitoring
            import psutil
            if psutil:
                process = psutil.Process()
                memory_before = process.memory_info().rss / 1024 / 1024
                logger.info(f"[MEMORY] Before Sheets client init: {memory_before:.2f} MB")
            
            self._sheets_client = SheetsClient(
                spreadsheet_id=self.config.GOOGLE_SPREADSHEET_ID
            )
            
            if psutil:
                memory_after = process.memory_info().rss / 1024 / 1024
                memory_diff = memory_after - memory_before
                logger.info(f"[MEMORY] After Sheets client init: {memory_after:.2f} MB (diff: {memory_diff:+.2f} MB)")
            
            logger.info("Google Sheets client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
            raise
        finally:
            self._initialization_lock = False
    
    def _initialize_drive_client(self):
        """Initialize Google Drive client with memory monitoring"""
        if self._initialization_lock:
            return
        
        try:
            self._initialization_lock = True
            logger.info("Lazy loading Google Drive client...")
            
            # Create token.json if it doesn't exist
            self._ensure_token_file()
            
            # Initialize with memory monitoring
            import psutil
            if psutil:
                process = psutil.Process()
                memory_before = process.memory_info().rss / 1024 / 1024
                logger.info(f"[MEMORY] Before Drive client init: {memory_before:.2f} MB")
            
            self._drive_client = DriveClient(
                root_folder_id=self.config.GOOGLE_DRIVE_FOLDER_ID
            )
            
            if psutil:
                memory_after = process.memory_info().rss / 1024 / 1024
                memory_diff = memory_after - memory_before
                logger.info(f"[MEMORY] After Drive client init: {memory_after:.2f} MB (diff: {memory_diff:+.2f} MB)")
            
            logger.info("Google Drive client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive client: {e}")
            raise
        finally:
            self._initialization_lock = False
    
    def _ensure_token_file(self):
        """Ensure token.json file exists"""
        import os
        if not os.path.exists("token.json"):
            logger.info("Creating token.json file from environment variable")
            with open("token.json", "w") as f:
                f.write(self.config.GOOGLE_TOKEN_JSON)
            logger.info("token.json file created successfully")
    
    def is_sheets_client_initialized(self) -> bool:
        """Check if Sheets client is initialized"""
        return self._sheets_client is not None
    
    def is_drive_client_initialized(self) -> bool:
        """Check if Drive client is initialized"""
        return self._drive_client is not None
    
    def cleanup_clients(self):
        """Clean up clients and free memory"""
        try:
            if self._sheets_client:
                del self._sheets_client
                self._sheets_client = None
                logger.info("Sheets client cleaned up")
            
            if self._drive_client:
                del self._drive_client
                self._drive_client = None
                logger.info("Drive client cleaned up")
            
            # Force garbage collection
            gc.collect()
            logger.info("Client cleanup completed with garbage collection")
            
        except Exception as e:
            logger.error(f"Error during client cleanup: {e}")
    
    def get_memory_usage(self) -> dict:
        """Get memory usage information"""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            return {
                'memory_mb': round(memory_mb, 2),
                'sheets_initialized': self.is_sheets_client_initialized(),
                'drive_initialized': self.is_drive_client_initialized()
            }
        except Exception as e:
            return {'error': str(e)}


# Global lazy client manager instance
_lazy_client_manager: Optional[LazyClientManager] = None


def get_lazy_client_manager(config: Config = None) -> LazyClientManager:
    """
    Get or create the global lazy client manager instance
    
    Args:
        config: Configuration instance (required for first call)
        
    Returns:
        LazyClientManager instance
    """
    global _lazy_client_manager
    
    if _lazy_client_manager is None:
        if config is None:
            raise ValueError("Config is required for first initialization")
        _lazy_client_manager = LazyClientManager(config)
    
    return _lazy_client_manager