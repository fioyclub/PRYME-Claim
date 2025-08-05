"""
Global Error Handler for Telegram Claim Bot

This module provides comprehensive error handling, retry mechanisms,
and user-friendly error messages for the entire application.
"""

import asyncio
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, Tuple
from functools import wraps
from enum import Enum

from telegram import Update
from telegram.error import TelegramError, NetworkError, TimedOut, BadRequest
from googleapiclient.errors import HttpError
from google.auth.exceptions import GoogleAuthError

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Types of errors that can occur in the system"""
    TELEGRAM_API = "telegram_api"
    GOOGLE_API = "google_api"
    VALIDATION = "validation"
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """Severity levels for errors"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RetryConfig:
    """Configuration for retry mechanisms"""
    
    def __init__(self, max_attempts: int = 3, base_delay: float = 1.0, 
                 max_delay: float = 60.0, exponential_base: float = 2.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base


class ErrorHandler:
    """
    Global error handler with retry mechanisms and user feedback
    """
    
    def __init__(self):
        self.error_counts = {}  # Track error frequencies
        self.last_errors = {}   # Track last error times for rate limiting
        self.retry_configs = self._setup_retry_configs()
        
        logger.info("ErrorHandler initialized")
    
    def _setup_retry_configs(self) -> Dict[ErrorType, RetryConfig]:
        """Setup retry configurations for different error types"""
        return {
            ErrorType.TELEGRAM_API: RetryConfig(max_attempts=3, base_delay=1.0),
            ErrorType.GOOGLE_API: RetryConfig(max_attempts=5, base_delay=2.0),
            ErrorType.NETWORK: RetryConfig(max_attempts=3, base_delay=1.0),
            ErrorType.RATE_LIMIT: RetryConfig(max_attempts=5, base_delay=5.0, max_delay=300.0),
            ErrorType.AUTHENTICATION: RetryConfig(max_attempts=2, base_delay=1.0),
            ErrorType.VALIDATION: RetryConfig(max_attempts=1),  # No retry for validation errors
            ErrorType.UNKNOWN: RetryConfig(max_attempts=2, base_delay=1.0)
        }
    
    def classify_error(self, error: Exception) -> Tuple[ErrorType, ErrorSeverity]:
        """
        Classify error type and severity
        
        Args:
            error: Exception to classify
            
        Returns:
            Tuple of (ErrorType, ErrorSeverity)
        """
        # Telegram API errors
        if isinstance(error, TelegramError):
            if isinstance(error, (NetworkError, TimedOut)):
                return ErrorType.NETWORK, ErrorSeverity.MEDIUM
            elif isinstance(error, BadRequest):
                return ErrorType.TELEGRAM_API, ErrorSeverity.LOW
            else:
                return ErrorType.TELEGRAM_API, ErrorSeverity.MEDIUM
        
        # Google API errors
        elif isinstance(error, HttpError):
            status_code = error.resp.status
            if status_code == 429:  # Rate limit
                return ErrorType.RATE_LIMIT, ErrorSeverity.HIGH
            elif status_code in [401, 403]:  # Auth errors
                return ErrorType.AUTHENTICATION, ErrorSeverity.HIGH
            elif status_code >= 500:  # Server errors
                return ErrorType.GOOGLE_API, ErrorSeverity.HIGH
            else:
                return ErrorType.GOOGLE_API, ErrorSeverity.MEDIUM
        
        # Google Auth errors
        elif isinstance(error, GoogleAuthError):
            return ErrorType.AUTHENTICATION, ErrorSeverity.CRITICAL
        
        # Validation errors
        elif isinstance(error, ValueError) and "validation" in str(error).lower():
            return ErrorType.VALIDATION, ErrorSeverity.LOW
        
        # Network errors
        elif isinstance(error, (ConnectionError, TimeoutError)):
            return ErrorType.NETWORK, ErrorSeverity.MEDIUM
        
        # Unknown errors
        else:
            return ErrorType.UNKNOWN, ErrorSeverity.MEDIUM
    
    def get_user_friendly_message(self, error_type: ErrorType, 
                                 error_severity: ErrorSeverity, 
                                 context: str = "") -> str:
        """
        Generate user-friendly error message
        
        Args:
            error_type: Type of error
            error_severity: Severity of error
            context: Context where error occurred
            
        Returns:
            User-friendly error message in Chinese
        """
        base_messages = {
            ErrorType.TELEGRAM_API: {
                ErrorSeverity.LOW: "Minor issue with message sending, please try again later.",
                ErrorSeverity.MEDIUM: "Telegram service temporarily unavailable, please try again later.",
                ErrorSeverity.HIGH: "Serious problem with Telegram connection, please try again later."
            },
            ErrorType.GOOGLE_API: {
                ErrorSeverity.LOW: "Minor issue saving data, please try again.",
                ErrorSeverity.MEDIUM: "Google service temporarily unavailable, please try again later.",
                ErrorSeverity.HIGH: "Problem with Google service, please try again later."
            },
            ErrorType.NETWORK: {
                ErrorSeverity.LOW: "Network connection unstable, please try again.",
                ErrorSeverity.MEDIUM: "Network connection problem, please check network and try again.",
                ErrorSeverity.HIGH: "Serious network connection issue, please try again later."
            },
            ErrorType.RATE_LIMIT: {
                ErrorSeverity.MEDIUM: "Too many requests, please wait a moment and try again.",
                ErrorSeverity.HIGH: "System busy, please wait a few minutes and try again."
            },
            ErrorType.AUTHENTICATION: {
                ErrorSeverity.HIGH: "System authentication problem, please contact administrator.",
                ErrorSeverity.CRITICAL: "System authentication failed, please contact administrator."
            },
            ErrorType.VALIDATION: {
                ErrorSeverity.LOW: "Input information format incorrect, please check and try again."
            },
            ErrorType.UNKNOWN: {
                ErrorSeverity.LOW: "Unknown error occurred, please try again.",
                ErrorSeverity.MEDIUM: "System problem occurred, please try again later.",
                ErrorSeverity.HIGH: "Serious system problem, please contact administrator."
            }
        }
        
        # Get base message
        type_messages = base_messages.get(error_type, base_messages[ErrorType.UNKNOWN])
        message = type_messages.get(error_severity, type_messages.get(ErrorSeverity.MEDIUM, "System problem occurred, please try again later."))
        
        # Add context-specific information
        if context:
            context_messages = {
                "registration": "during registration",
                "claim_submission": "when submitting claim",
                "photo_upload": "when uploading photo",
                "data_save": "when saving data",
                "user_lookup": "when looking up user information"
            }
            
            if context in context_messages:
                message = f"{context_messages[context]}{message}"
        
        return f"❌ {message}"
    
    async def handle_error_with_retry(self, func: Callable, *args, 
                                    error_context: str = "", 
                                    user_id: Optional[int] = None, **kwargs) -> Tuple[bool, Any, Optional[str]]:
        """
        Execute function with automatic retry on failure
        
        Args:
            func: Function to execute
            *args: Function arguments
            error_context: Context description for error messages
            user_id: User ID for error tracking
            **kwargs: Function keyword arguments
            
        Returns:
            Tuple of (success, result, error_message)
        """
        last_error = None
        
        for attempt in range(3):  # Default max attempts
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Success - reset error count for this context
                if user_id and error_context:
                    error_key = f"{user_id}_{error_context}"
                    self.error_counts.pop(error_key, None)
                
                return True, result, None
                
            except Exception as error:
                last_error = error
                error_type, error_severity = self.classify_error(error)
                
                # Log the error
                logger.error(f"Attempt {attempt + 1} failed in {error_context}: {error}")
                
                # Track error frequency
                if user_id:
                    error_key = f"{user_id}_{error_context}"
                    self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
                
                # Check if we should retry
                if not self._should_retry(error_type, attempt + 1):
                    break
                
                # Calculate delay for next attempt
                delay = self._calculate_retry_delay(error_type, attempt)
                if delay > 0:
                    await asyncio.sleep(delay)
        
        # All attempts failed
        if last_error:
            error_type, error_severity = self.classify_error(last_error)
            user_message = self.get_user_friendly_message(error_type, error_severity, error_context)
            
            # Log final failure
            logger.error(f"All retry attempts failed for {error_context}: {last_error}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            return False, None, user_message
        
        return False, None, "❌ Operation failed, please try again later."
    
    def _should_retry(self, error_type: ErrorType, attempt: int) -> bool:
        """Determine if error should be retried"""
        config = self.retry_configs.get(error_type, self.retry_configs[ErrorType.UNKNOWN])
        
        # Don't retry validation errors
        if error_type == ErrorType.VALIDATION:
            return False
        
        # Don't retry if max attempts reached
        if attempt >= config.max_attempts:
            return False
        
        return True
    
    def _calculate_retry_delay(self, error_type: ErrorType, attempt: int) -> float:
        """Calculate delay before next retry attempt"""
        config = self.retry_configs.get(error_type, self.retry_configs[ErrorType.UNKNOWN])
        
        # Exponential backoff
        delay = config.base_delay * (config.exponential_base ** attempt)
        
        # Cap at max delay
        delay = min(delay, config.max_delay)
        
        return delay
    
    def log_error_details(self, error: Exception, context: str, user_id: Optional[int] = None):
        """
        Log detailed error information for debugging
        
        Args:
            error: Exception that occurred
            context: Context where error occurred
            user_id: Optional user ID
        """
        error_type, error_severity = self.classify_error(error)
        
        error_details = {
            'timestamp': datetime.now().isoformat(),
            'error_type': error_type.value,
            'error_severity': error_severity.value,
            'context': context,
            'user_id': user_id,
            'error_message': str(error),
            'error_class': error.__class__.__name__,
            'traceback': traceback.format_exc()
        }
        
        # Log based on severity
        if error_severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            logger.critical(f"Critical error in {context}: {error_details}")
        elif error_severity == ErrorSeverity.MEDIUM:
            logger.error(f"Error in {context}: {error_details}")
        else:
            logger.warning(f"Minor error in {context}: {error_details}")
    
    def reset_user_error_state(self, user_id: int):
        """
        Reset error state for a user (useful after successful operations)
        
        Args:
            user_id: User ID to reset
        """
        keys_to_remove = [key for key in self.error_counts.keys() if key.startswith(f"{user_id}_")]
        for key in keys_to_remove:
            self.error_counts.pop(key, None)
        
        logger.debug(f"Reset error state for user {user_id}")
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """
        Get error statistics for monitoring
        
        Returns:
            Dictionary with error statistics
        """
        total_errors = sum(self.error_counts.values())
        
        # Group by error type
        type_counts = {}
        for key, count in self.error_counts.items():
            # Extract context from key (format: userid_context)
            if '_' in key:
                context = key.split('_', 1)[1]
                type_counts[context] = type_counts.get(context, 0) + count
        
        return {
            'total_errors': total_errors,
            'error_by_context': type_counts,
            'active_error_keys': len(self.error_counts),
            'timestamp': datetime.now().isoformat()
        }


def with_error_handling(context: str = "", reset_state_on_success: bool = True):
    """
    Decorator for automatic error handling with retry
    
    Args:
        context: Context description for error messages
        reset_state_on_success: Whether to reset error state on success
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Try to extract user_id from arguments
            user_id = None
            if args and hasattr(args[0], '__dict__'):
                # Look for user_id in first argument (usually self)
                for arg in args[1:]:  # Skip self
                    if isinstance(arg, int) and arg > 0:
                        user_id = arg
                        break
            
            # Get error handler instance (assuming it's available globally)
            error_handler = getattr(args[0], 'error_handler', None) if args else None
            
            if not error_handler:
                # Fallback to direct execution if no error handler available
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error in {func.__name__}: {e}")
                    raise
            
            success, result, error_message = await error_handler.handle_error_with_retry(
                func, *args, error_context=context or func.__name__, user_id=user_id, **kwargs
            )
            
            if success:
                if reset_state_on_success and user_id:
                    error_handler.reset_user_error_state(user_id)
                return result
            else:
                # Create a custom exception with user-friendly message
                raise RuntimeError(error_message or "Operation failed")
        
        return wrapper
    return decorator


# Global error handler instance
global_error_handler = ErrorHandler()
