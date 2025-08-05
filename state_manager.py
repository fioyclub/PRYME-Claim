"""
State management for the Telegram Claim Bot.

This module provides the StateManager class that handles user conversation states,
temporary data storage, and concurrent access protection during multi-step processes.
"""

import asyncio
import gc
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any
import logging
from threading import Lock
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
    Manages user conversation states and temporary data.
    
    This class provides thread-safe operations for tracking user states
    during registration and claim submission processes.
    """
    
    def __init__(self, cleanup_interval_minutes: int = 5):
        """
        Initialize the StateManager with optimized memory management.
        
        Args:
            cleanup_interval_minutes: Interval for cleaning up expired states (default: 5 minutes)
        """
        self._states: Dict[int, UserState] = {}
        self._locks: Dict[int, Lock] = {}
        self._global_lock = Lock()
        self._cleanup_interval = cleanup_interval_minutes
        self._last_cleanup = datetime.now()
        
        logger.info("StateManager initialized with cleanup interval: %d minutes (optimized for memory)", 
                   cleanup_interval_minutes)
    
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
        Set user conversation state with optional temporary data.
        
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
        
        logger.debug("Set state for user %d: %s", user_id, state.value)
        
        # Perform cleanup if needed
        self._cleanup_expired_states()
    
    def get_user_state(self, user_id: int) -> Tuple[UserStateType, Dict[str, Any]]:
        """
        Get user conversation state and temporary data.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Tuple of (current_state, temp_data)
        """
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            if user_id not in self._states:
                # Return default idle state
                return UserStateType.IDLE, {}
            
            user_state = self._states[user_id]
            return user_state.current_state, user_state.temp_data.copy()
    
    def clear_user_state(self, user_id: int) -> None:
        """
        Clear user state and reset to idle.
        
        Args:
            user_id: Telegram user ID
        """
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            if user_id in self._states:
                user_state = self._states[user_id]
                user_state.current_state = UserStateType.IDLE
                user_state.clear_temp_data()
                
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
