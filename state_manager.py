"""
State management for the Telegram Claim Bot.

This module provides the StateManager class that handles user conversation states,
temporary data storage, and concurrent access protection during multi-step processes.
Now with Google Sheets persistent storage to prevent state loss on container restarts.
"""

import asyncio
import gc
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any
import logging
from threading import Lock, Thread
from models import UserState, UserStateType

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available, memory monitoring disabled")

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages user conversation states and temporary data with Google Sheets persistence.
    
    This class provides thread-safe operations for tracking user states
    during registration and claim submission processes, with persistent storage
    to prevent state loss on container restarts.
    """
    
    def __init__(self, lazy_client_manager=None, cleanup_interval_minutes: int = 5, sync_interval_minutes: int = 5):
        """
        Initialize the StateManager with Google Sheets persistence.
        
        Args:
            lazy_client_manager: Lazy client manager for Google API clients
            cleanup_interval_minutes: Interval for cleaning up expired states (default: 5 minutes)
            sync_interval_minutes: Interval for syncing with Google Sheets (default: 5 minutes)
        """
        self.lazy_client_manager = lazy_client_manager
        self._states: Dict[int, UserState] = {}  # Memory cache for active users
        self._locks: Dict[int, Lock] = {}
        self._global_lock = Lock()
        self._cleanup_interval = cleanup_interval_minutes
        self._sync_interval = sync_interval_minutes
        self._last_cleanup = datetime.now()
        self._last_sync = datetime.now()
        self._sheets_worksheet = "UserStates"
        self._sync_enabled = lazy_client_manager is not None
        
        # Initialize background sync if sheets client is available
        if self._sync_enabled:
            self._initialize_sheets_storage()
            self._load_states_from_sheets()
            self._start_background_sync()
        
        logger.info("StateManager initialized with Google Sheets persistence: %s, cleanup interval: %d minutes", 
                   "enabled" if self._sync_enabled else "disabled", cleanup_interval_minutes)
    
    def _initialize_sheets_storage(self):
        """Initialize Google Sheets storage for user states"""
        try:
            if not self._sync_enabled:
                return
            
            sheets_client = self.lazy_client_manager.get_sheets_client()
            
            # Create UserStates worksheet if it doesn't exist
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                success = loop.run_until_complete(
                    sheets_client.create_worksheet_if_not_exists(self._sheets_worksheet)
                )
                
                if success:
                    logger.info(f"Created UserStates worksheet: {self._sheets_worksheet}")
                else:
                    logger.info(f"UserStates worksheet already exists: {self._sheets_worksheet}")
                
                # Ensure headers are set
                loop.run_until_complete(
                    sheets_client.ensure_worksheet_headers(self._sheets_worksheet)
                )
                
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"Failed to initialize sheets storage: {e}")
            self._sync_enabled = False
    
    def _load_states_from_sheets(self):
        """Load all user states from Google Sheets on startup"""
        try:
            if not self._sync_enabled:
                return
            
            sheets_client = self.lazy_client_manager.get_sheets_client()
            
            # Get all states from UserStates worksheet
            result = sheets_client._get_service().spreadsheets().values().get(
                spreadsheetId=sheets_client.spreadsheet_id,
                range=f"{self._sheets_worksheet}!A:D"
            ).execute()
            
            values = result.get('values', [])
            loaded_count = 0
            
            # Skip header row
            for row in values[1:] if len(values) > 1 else []:
                if len(row) >= 4:
                    try:
                        user_id = int(row[0])
                        state_value = row[1]
                        temp_data_json = row[2] if row[2] else '{}'
                        last_updated_str = row[3]
                        
                        # Parse data
                        state = UserStateType(state_value)
                        temp_data = json.loads(temp_data_json)
                        last_updated = datetime.fromisoformat(last_updated_str)
                        
                        # Only load recent states (within 24 hours)
                        if (datetime.now() - last_updated).total_seconds() < 24 * 3600:
                            user_state = UserState(
                                user_id=user_id,
                                current_state=state,
                                temp_data=temp_data,
                                last_updated=last_updated
                            )
                            self._states[user_id] = user_state
                            loaded_count += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to parse state row {row}: {e}")
                        continue
            
            logger.info(f"Loaded {loaded_count} user states from Google Sheets")
            
        except Exception as e:
            logger.error(f"Failed to load states from sheets: {e}")
    
    def _save_state_to_sheets(self, user_id: int, user_state: UserState):
        """Save a single user state to Google Sheets"""
        try:
            if not self._sync_enabled:
                return
            
            sheets_client = self.lazy_client_manager.get_sheets_client()
            
            # Prepare data
            temp_data_json = json.dumps(user_state.temp_data, ensure_ascii=False)
            last_updated_str = user_state.last_updated.isoformat()
            
            # Check if user already exists in sheet
            existing_row = self._find_user_row_in_sheets(user_id)
            
            if existing_row is not None:
                # Update existing row
                range_name = f"{self._sheets_worksheet}!A{existing_row}:D{existing_row}"
                values = [[user_id, user_state.current_state.value, temp_data_json, last_updated_str]]
                
                sheets_client._get_service().spreadsheets().values().update(
                    spreadsheetId=sheets_client.spreadsheet_id,
                    range=range_name,
                    valueInputOption='RAW',
                    body={'values': values}
                ).execute()
                
            else:
                # Append new row
                values = [[user_id, user_state.current_state.value, temp_data_json, last_updated_str]]
                
                sheets_client._get_service().spreadsheets().values().append(
                    spreadsheetId=sheets_client.spreadsheet_id,
                    range=f"{self._sheets_worksheet}!A:D",
                    valueInputOption='RAW',
                    insertDataOption='INSERT_ROWS',
                    body={'values': values}
                ).execute()
            
            logger.debug(f"Saved state for user {user_id} to Google Sheets")
            
        except Exception as e:
            logger.error(f"Failed to save state to sheets for user {user_id}: {e}")
    
    def _find_user_row_in_sheets(self, user_id: int) -> Optional[int]:
        """Find the row number for a specific user in Google Sheets"""
        try:
            if not self._sync_enabled:
                return None
            
            sheets_client = self.lazy_client_manager.get_sheets_client()
            
            result = sheets_client._get_service().spreadsheets().values().get(
                spreadsheetId=sheets_client.spreadsheet_id,
                range=f"{self._sheets_worksheet}!A:A"
            ).execute()
            
            values = result.get('values', [])
            
            for i, row in enumerate(values):
                if len(row) > 0 and str(row[0]) == str(user_id):
                    return i + 1  # Sheets rows are 1-indexed
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to find user row for {user_id}: {e}")
            return None
    
    def _delete_state_from_sheets(self, user_id: int):
        """Delete a user state from Google Sheets"""
        try:
            if not self._sync_enabled:
                return
            
            row_number = self._find_user_row_in_sheets(user_id)
            if row_number is None:
                return
            
            sheets_client = self.lazy_client_manager.get_sheets_client()
            
            # Delete the row
            request_body = {
                'requests': [{
                    'deleteDimension': {
                        'range': {
                            'sheetId': 0,  # Assuming first sheet
                            'dimension': 'ROWS',
                            'startIndex': row_number - 1,  # 0-indexed for API
                            'endIndex': row_number
                        }
                    }
                }]
            }
            
            sheets_client._get_service().spreadsheets().batchUpdate(
                spreadsheetId=sheets_client.spreadsheet_id,
                body=request_body
            ).execute()
            
            logger.debug(f"Deleted state for user {user_id} from Google Sheets")
            
        except Exception as e:
            logger.error(f"Failed to delete state from sheets for user {user_id}: {e}")
    
    def _start_background_sync(self):
        """Start background thread for periodic sync with Google Sheets"""
        if not self._sync_enabled:
            return
        
        def sync_worker():
            while True:
                try:
                    # Sleep for sync interval
                    import time
                    time.sleep(self._sync_interval * 60)
                    
                    # Perform sync
                    self._sync_with_sheets()
                    
                except Exception as e:
                    logger.error(f"Error in background sync: {e}")
        
        sync_thread = Thread(target=sync_worker, daemon=True)
        sync_thread.start()
        logger.info("Started background sync thread")
    
    def _sync_with_sheets(self):
        """Sync memory states with Google Sheets"""
        try:
            if not self._sync_enabled:
                return
            
            now = datetime.now()
            
            # Only sync if enough time has passed
            if (now - self._last_sync).total_seconds() < self._sync_interval * 60:
                return
            
            with self._global_lock:
                # Save all active states to sheets
                for user_id, user_state in self._states.items():
                    self._save_state_to_sheets(user_id, user_state)
                
                self._last_sync = now
                logger.debug(f"Synced {len(self._states)} states with Google Sheets")
            
        except Exception as e:
            logger.error(f"Failed to sync with sheets: {e}")
    
    def _get_user_lock(self, user_id: int) -> Lock:
        """
        Get or create a lock for a specific user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Lock object for the user
        """
        with self._global_lock:
            if user_id not in self._locks:
                self._locks[user_id] = Lock()
            return self._locks[user_id]
    
    def _cleanup_expired_states(self) -> None:
        """
        Clean up expired user states (older than 30 minutes) - optimized for memory.
        """
        now = datetime.now()
        
        # Only run cleanup if enough time has passed
        if (now - self._last_cleanup).total_seconds() < self._cleanup_interval * 60:
            return
        
        expired_users = []
        # Reduced expiry time from 1 hour to 30 minutes to prevent memory accumulation
        expiry_threshold = now - timedelta(minutes=30)
        
        with self._global_lock:
            for user_id, state in self._states.items():
                if state.last_updated < expiry_threshold:
                    expired_users.append(user_id)
        
        # Remove expired states
        for user_id in expired_users:
            self._remove_user_state(user_id)
            logger.debug("Cleaned up expired state for user %d", user_id)
        
        self._last_cleanup = now
        
        if expired_users:
            logger.info("Memory optimization: Cleaned up %d expired user states", len(expired_users))
            # Force garbage collection after cleanup to free memory immediately
            import gc
            gc.collect()
    
    def _remove_user_state(self, user_id: int) -> None:
        """
        Remove user state and associated lock.
        
        Args:
            user_id: Telegram user ID
        """
        with self._global_lock:
            self._states.pop(user_id, None)
            self._locks.pop(user_id, None)
    
    def set_user_state(self, user_id: int, state: UserStateType, data: Optional[Dict[str, Any]] = None) -> None:
        """
        Set user conversation state with optional temporary data and persist to Google Sheets.
        
        Args:
            user_id: Telegram user ID
            state: New conversation state
            data: Optional temporary data to store
        """
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            now = datetime.now()
            
            if user_id in self._states:
                # Update existing state
                user_state = self._states[user_id]
                user_state.current_state = state
                user_state.last_updated = now
                
                if data:
                    user_state.temp_data.update(data)
            else:
                # Create new state
                user_state = UserState(
                    user_id=user_id,
                    current_state=state,
                    temp_data=data or {},
                    last_updated=now
                )
                self._states[user_id] = user_state
            
            # Save to Google Sheets asynchronously to avoid blocking
            if self._sync_enabled:
                try:
                    self._save_state_to_sheets(user_id, user_state)
                except Exception as e:
                    logger.error(f"Failed to save state to sheets for user {user_id}: {e}")
        
        logger.debug("Set state for user %d: %s", user_id, state.value)
        
        # Perform cleanup if needed
        self._cleanup_expired_states()
    
    def get_user_state(self, user_id: int) -> Tuple[UserStateType, Dict[str, Any]]:
        """
        Get user conversation state and temporary data, loading from Google Sheets if not in memory.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Tuple of (current_state, temp_data)
        """
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            if user_id not in self._states:
                # Try to load from Google Sheets
                if self._sync_enabled:
                    try:
                        self._load_user_state_from_sheets(user_id)
                    except Exception as e:
                        logger.error(f"Failed to load state from sheets for user {user_id}: {e}")
                
                # If still not found, return default idle state
                if user_id not in self._states:
                    return UserStateType.IDLE, {}
            
            user_state = self._states[user_id]
            return user_state.current_state, user_state.temp_data.copy()
    
    def _load_user_state_from_sheets(self, user_id: int):
        """Load a specific user's state from Google Sheets"""
        try:
            if not self._sync_enabled:
                return
            
            sheets_client = self.lazy_client_manager.get_sheets_client()
            
            # Get user's row from UserStates worksheet
            result = sheets_client._get_service().spreadsheets().values().get(
                spreadsheetId=sheets_client.spreadsheet_id,
                range=f"{self._sheets_worksheet}!A:D"
            ).execute()
            
            values = result.get('values', [])
            
            # Find user's row
            for row in values[1:] if len(values) > 1 else []:
                if len(row) >= 4 and str(row[0]) == str(user_id):
                    try:
                        state_value = row[1]
                        temp_data_json = row[2] if row[2] else '{}'
                        last_updated_str = row[3]
                        
                        # Parse data
                        state = UserStateType(state_value)
                        temp_data = json.loads(temp_data_json)
                        last_updated = datetime.fromisoformat(last_updated_str)
                        
                        # Only load recent states (within 24 hours)
                        if (datetime.now() - last_updated).total_seconds() < 24 * 3600:
                            user_state = UserState(
                                user_id=user_id,
                                current_state=state,
                                temp_data=temp_data,
                                last_updated=last_updated
                            )
                            self._states[user_id] = user_state
                            logger.debug(f"Loaded state for user {user_id} from Google Sheets")
                        
                        break
                        
                    except Exception as e:
                        logger.warning(f"Failed to parse state for user {user_id}: {e}")
                        break
            
        except Exception as e:
            logger.error(f"Failed to load user state from sheets for {user_id}: {e}")
    
    def clear_user_state(self, user_id: int) -> None:
        """
        Clear user state and reset to idle, also remove from Google Sheets.
        
        Args:
            user_id: Telegram user ID
        """
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            if user_id in self._states:
                # Remove from memory
                del self._states[user_id]
                
                # Remove from Google Sheets
                if self._sync_enabled:
                    try:
                        self._delete_state_from_sheets(user_id)
                    except Exception as e:
                        logger.error(f"Failed to delete state from sheets for user {user_id}: {e}")
                
                logger.debug("Cleared state for user %d", user_id)
    
    def update_user_data(self, user_id: int, key: str, value: Any) -> None:
        """
        Update specific temporary data for a user.
        
        Args:
            user_id: Telegram user ID
            key: Data key to update
            value: New value for the key
        """
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            if user_id not in self._states:
                # Create new state if it doesn't exist
                self.set_user_state(user_id, UserStateType.IDLE, {key: value})
            else:
                user_state = self._states[user_id]
                user_state.update_temp_data(key, value)
        
        logger.debug("Updated data for user %d: %s = %s", user_id, key, str(value)[:50])
    
    def get_user_data(self, user_id: int, key: str, default: Any = None) -> Any:
        """
        Get specific temporary data for a user.
        
        Args:
            user_id: Telegram user ID
            key: Data key to retrieve
            default: Default value if key doesn't exist
            
        Returns:
            Value for the key or default
        """
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            if user_id not in self._states:
                return default
            
            user_state = self._states[user_id]
            return user_state.temp_data.get(key, default)
    
    def is_user_in_state(self, user_id: int, state: UserStateType) -> bool:
        """
        Check if user is in a specific state.
        
        Args:
            user_id: Telegram user ID
            state: State to check
            
        Returns:
            True if user is in the specified state
        """
        current_state, _ = self.get_user_state(user_id)
        return current_state == state
    
    def is_user_idle(self, user_id: int) -> bool:
        """
        Check if user is in idle state.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if user is idle
        """
        return self.is_user_in_state(user_id, UserStateType.IDLE)
    
    def is_user_registering(self, user_id: int) -> bool:
        """
        Check if user is in any registration state.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if user is in registration process
        """
        current_state, _ = self.get_user_state(user_id)
        registration_states = {
            UserStateType.REGISTERING_NAME,
            UserStateType.REGISTERING_PHONE,
            UserStateType.REGISTERING_ROLE
        }
        return current_state in registration_states
    
    def is_user_claiming(self, user_id: int) -> bool:
        """
        Check if user is in any claim submission state.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if user is in claim submission process
        """
        current_state, _ = self.get_user_state(user_id)
        claiming_states = {
            UserStateType.CLAIMING_CATEGORY,
            UserStateType.CLAIMING_AMOUNT,
            UserStateType.CLAIMING_OTHER_DESCRIPTION,
            UserStateType.CLAIMING_PHOTO,
            UserStateType.CLAIMING_CONFIRM
        }
        return current_state in claiming_states
    
    def is_user_requesting_dayoff(self, user_id: int) -> bool:
        """
        Check if user is in any day-off request state.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if user is in day-off request process
        """
        current_state, _ = self.get_user_state(user_id)
        dayoff_states = {
            UserStateType.DAYOFF_TYPE,
            UserStateType.DAYOFF_DATE,
            UserStateType.DAYOFF_START_DATE,
            UserStateType.DAYOFF_END_DATE,
            UserStateType.DAYOFF_REASON
        }
        return current_state in dayoff_states
    
    def get_active_users_count(self) -> int:
        """
        Get count of users with active (non-idle) states.
        
        Returns:
            Number of active users
        """
        with self._global_lock:
            active_count = sum(
                1 for state in self._states.values()
                if state.current_state != UserStateType.IDLE
            )
        return active_count
    
    def get_total_users_count(self) -> int:
        """
        Get total count of users in state manager.
        
        Returns:
            Total number of users
        """
        with self._global_lock:
            return len(self._states)
    
    def force_cleanup(self) -> int:
        """
        Force cleanup of all expired states.
        
        Returns:
            Number of states cleaned up
        """
        now = datetime.now()
        expired_users = []
        expiry_threshold = now - timedelta(hours=1)
        
        with self._global_lock:
            for user_id, state in self._states.items():
                if state.last_updated < expiry_threshold:
                    expired_users.append(user_id)
        
        # Remove expired states
        for user_id in expired_users:
            self._remove_user_state(user_id)
        
        self._last_cleanup = now
        
        logger.info("Force cleanup removed %d expired states", len(expired_users))
        return len(expired_users)
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """
        Get current memory usage information.
        
        Returns:
            Dict containing memory usage stats
        """
        if not PSUTIL_AVAILABLE:
            return {'available': False, 'message': 'psutil not installed'}
        
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            
            return {
                'available': True,
                'rss_mb': round(memory_info.rss / 1024 / 1024, 2),
                'vms_mb': round(memory_info.vms / 1024 / 1024, 2),
                'percent': process.memory_percent(),
                'states_count': len(self._states),
                'locks_count': len(self._locks)
            }
        except Exception as e:
            logger.error(f"Error getting memory usage: {e}")
            return {'available': False, 'error': str(e)}
    
    def check_memory_and_cleanup(self, threshold_mb: float = 400.0) -> bool:
        """
        Check memory usage and perform aggressive cleanup if threshold exceeded.
        
        Args:
            threshold_mb: Memory threshold in MB to trigger cleanup
            
        Returns:
            bool: True if cleanup was performed
        """
        if not PSUTIL_AVAILABLE:
            return False
        
        try:
            memory_info = self.get_memory_usage()
            if not memory_info.get('available'):
                return False
            
            current_memory = memory_info['rss_mb']
            
            if current_memory >= threshold_mb:
                logger.warning(f"Memory usage {current_memory}MB exceeds threshold {threshold_mb}MB, performing aggressive cleanup")
                
                # Force cleanup all expired states
                cleanup_count = self.force_cleanup()
                
                # Additional aggressive cleanup: remove idle states older than 10 minutes
                now = datetime.now()
                aggressive_threshold = now - timedelta(minutes=10)
                aggressive_cleanup = []
                
                with self._global_lock:
                    for user_id, state in self._states.items():
                        if (state.current_state == UserStateType.IDLE and 
                            state.last_updated < aggressive_threshold):
                            aggressive_cleanup.append(user_id)
                
                for user_id in aggressive_cleanup:
                    self._remove_user_state(user_id)
                
                total_cleaned = cleanup_count + len(aggressive_cleanup)
                
                # Force garbage collection
                gc.collect()
                
                # Check memory after cleanup
                new_memory_info = self.get_memory_usage()
                new_memory = new_memory_info.get('rss_mb', current_memory)
                
                logger.info(f"Aggressive cleanup completed: removed {total_cleaned} states, "
                           f"memory: {current_memory}MB -> {new_memory}MB")
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error in memory check and cleanup: {e}")
            return False
    
    def force_sync_with_sheets(self) -> bool:
        """
        Force immediate sync with Google Sheets (for debugging/monitoring)
        
        Returns:
            bool: True if sync was successful
        """
        try:
            if not self._sync_enabled:
                logger.warning("Sheets sync is disabled")
                return False
            
            with self._global_lock:
                # Save all active states to sheets
                for user_id, user_state in self._states.items():
                    self._save_state_to_sheets(user_id, user_state)
                
                self._last_sync = datetime.now()
                logger.info(f"Force synced {len(self._states)} states with Google Sheets")
                return True
            
        except Exception as e:
            logger.error(f"Failed to force sync with sheets: {e}")
            return False
    
    def get_sync_status(self) -> Dict[str, Any]:
        """
        Get current sync status information
        
        Returns:
            Dict with sync status information
        """
        return {
            'sync_enabled': self._sync_enabled,
            'memory_states_count': len(self._states),
            'last_sync': self._last_sync.isoformat() if self._last_sync else None,
            'sync_interval_minutes': self._sync_interval,
            'worksheet_name': self._sheets_worksheet
        }
