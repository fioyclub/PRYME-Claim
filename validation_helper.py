"""
Validation Helper for Telegram Claim Bot

This module provides enhanced validation error handling with retry flows,
format examples, and user guidance for input validation failures.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram import ParseMode

from validation import (
    validate_name, validate_phone_number, validate_amount, validate_photo_file,
    get_validation_help_message, ValidationResult
)
from keyboards import KeyboardBuilder

logger = logging.getLogger(__name__)


class ValidationHelper:
    """
    Helper class for handling validation errors with user-friendly feedback
    """
    
    def __init__(self):
        self.validation_attempts = {}  # Track validation attempts per user
        self.max_attempts = 3  # Maximum attempts before showing help
        
        logger.info("ValidationHelper initialized")
    
    def track_validation_attempt(self, user_id: int, field: str) -> int:
        """
        Track validation attempts for a user and field
        
        Args:
            user_id: Telegram user ID
            field: Field being validated
            
        Returns:
            Current attempt count
        """
        key = f"{user_id}_{field}"
        self.validation_attempts[key] = self.validation_attempts.get(key, 0) + 1
        return self.validation_attempts[key]
    
    def reset_validation_attempts(self, user_id: int, field: str = None):
        """
        Reset validation attempts for a user
        
        Args:
            user_id: Telegram user ID
            field: Specific field to reset, or None for all fields
        """
        if field:
            key = f"{user_id}_{field}"
            self.validation_attempts.pop(key, None)
        else:
            # Reset all attempts for user
            keys_to_remove = [k for k in self.validation_attempts.keys() if k.startswith(f"{user_id}_")]
            for key in keys_to_remove:
                self.validation_attempts.pop(key, None)
    
    def should_show_help(self, user_id: int, field: str) -> bool:
        """
        Determine if help should be shown based on attempt count
        
        Args:
            user_id: Telegram user ID
            field: Field being validated
            
        Returns:
            True if help should be shown
        """
        key = f"{user_id}_{field}"
        attempts = self.validation_attempts.get(key, 0)
        return attempts >= self.max_attempts
    
    def create_validation_error_message(self, validation_result: ValidationResult, 
                                      field: str, user_id: int, 
                                      show_examples: bool = True) -> Dict[str, Any]:
        """
        Create comprehensive validation error message with suggestions
        
        Args:
            validation_result: Result from validation function
            field: Field that failed validation
            user_id: User ID for tracking attempts
            show_examples: Whether to show format examples
            
        Returns:
            Dictionary with message and keyboard
        """
        attempt_count = self.track_validation_attempt(user_id, field)
        
        # Base error message
        message = f"❌ {validation_result.error_message}"
        
        # Add suggestions if available
        if validation_result.suggestions:
            message += "\n\n💡 Suggestions:\n" + "\n".join(f"• {suggestion}" for suggestion in validation_result.suggestions)
        
        # Add examples after multiple attempts
        if show_examples and attempt_count >= 2:
            help_message = get_validation_help_message(field)
            message += f"\n\n{help_message}"
        
        # Add attempt counter if multiple attempts
        if attempt_count > 1:
            message += f"\n\n🔄 Attempts: {attempt_count}/{self.max_attempts}"
        
        # Create keyboard with help option
        keyboard = self._create_validation_keyboard(field, attempt_count)
        
        return {
            'message': message,
            'keyboard': keyboard,
            'attempt_count': attempt_count,
            'show_help': attempt_count >= self.max_attempts
        }
    
    def _create_validation_keyboard(self, field: str, attempt_count: int) -> InlineKeyboardMarkup:
        """
        Create keyboard for validation error handling
        
        Args:
            field: Field being validated
            attempt_count: Current attempt count
            
        Returns:
            InlineKeyboardMarkup with appropriate options
        """
        buttons = []
        
        # Always show help button after first attempt
        if attempt_count >= 1:
            help_text = {
                'name': '👤 Name Format Help',
                'phone': '📱 Phone Format Help',
                'amount': '💰 Amount Format Help',
                'photo': '📷 Photo Format Help'
            }.get(field, '❓ Format Help')
            
            buttons.append([InlineKeyboardButton(help_text, callback_data=f"help_{field}")])
        
        # Show skip option for non-critical fields after multiple attempts
        if attempt_count >= self.max_attempts and field in ['phone']:  # Only for optional fields
            buttons.append([InlineKeyboardButton("⏭️ Fill Later", callback_data=f"skip_{field}")])
        
        # Always show cancel option
        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
        
        return InlineKeyboardMarkup(buttons)
    
    def create_success_message(self, field: str, value: Any, user_id: int) -> str:
        """
        Create success message for successful validation
        
        Args:
            field: Field that was validated
            value: Validated value
            user_id: User ID
            
        Returns:
            Success message string
        """
        # Reset attempts on success
        self.reset_validation_attempts(user_id, field)
        
        success_messages = {
            'name': f'✅ Name confirmed: {value}',
            'phone': f'✅ Phone number confirmed: {value}',
            'amount': f'✅ Amount confirmed: {value}',
            'photo': '✅ Photo uploaded successfully'
        }
        
        return success_messages.get(field, f'✅ {field} confirmed')
    
    def handle_validation_help_request(self, field: str) -> str:
        """
        Handle help request for specific field
        
        Args:
            field: Field to provide help for
            
        Returns:
            Help message string
        """
        help_message = get_validation_help_message(field)
        
        # Add specific tips based on field
        tips = {
            'name': "\n\n🔧 Common Issues:\n• Ensure name is at least 2 characters\n• Avoid using numbers or special symbols\n• Can include Chinese, English and common punctuation",
            'phone': "\n\n🔧 Common Issues:\n• Ensure it includes country code or starts with 0\n• Check if number length is correct\n• Can include spaces and hyphens",
            'amount': "\n\n🔧 Common Issues:\n• Ensure amount is greater than 0\n• Maximum 2 decimal places\n• Can include RM prefix and thousand separators",
            'photo': "\n\n🔧 Common Issues:\n• Ensure file is in image format\n• Check file size does not exceed 10MB\n• Ensure image is clear and visible"
        }
        
        return help_message + tips.get(field, "")
    
    def create_retry_prompt(self, field: str, context: str = "") -> str:
        """
        Create retry prompt for failed validation
        
        Args:
            field: Field to retry
            context: Additional context
            
        Returns:
            Retry prompt string
        """
        prompts = {
            'name': 'Please re-enter your real name:',
            'phone': 'Please re-enter your phone number:',
            'amount': 'Please re-enter amount (RM):',
            'photo': 'Please re-upload receipt photo:'
        }
        
        base_prompt = prompts.get(field, f'Please re-enter {field}:')
        
        if context:
            return f"{context}\n\n{base_prompt}"
        
        return base_prompt
    
    def get_validation_statistics(self) -> Dict[str, Any]:
        """
        Get validation statistics for monitoring
        
        Returns:
            Dictionary with validation statistics
        """
        total_attempts = sum(self.validation_attempts.values())
        
        # Group by field
        field_stats = {}
        for key, count in self.validation_attempts.items():
            if '_' in key:
                field = key.split('_', 1)[1]
                field_stats[field] = field_stats.get(field, 0) + count
        
        # Count users with multiple attempts
        users_with_issues = len(set(key.split('_')[0] for key in self.validation_attempts.keys()))
        
        return {
            'total_validation_attempts': total_attempts,
            'attempts_by_field': field_stats,
            'users_with_validation_issues': users_with_issues,
            'active_validation_sessions': len(self.validation_attempts)
        }
    
    def cleanup_old_attempts(self, max_age_hours: int = 24):
        """
        Clean up old validation attempts to prevent memory buildup
        
        Args:
            max_age_hours: Maximum age in hours to keep attempts
        """
        # This is a simple implementation - in production you might want to track timestamps
        # For now, we'll just limit the total number of tracked attempts
        if len(self.validation_attempts) > 1000:
            # Keep only the most recent 500 attempts
            sorted_items = sorted(self.validation_attempts.items(), key=lambda x: x[1], reverse=True)
            self.validation_attempts = dict(sorted_items[:500])
            logger.info("Cleaned up old validation attempts")


# Global validation helper instance
global_validation_helper = ValidationHelper()


def create_validation_error_response(validation_result: ValidationResult, field: str, 
                                   user_id: int, context: str = "") -> Dict[str, Any]:
    """
    Create standardized validation error response
    
    Args:
        validation_result: Result from validation function
        field: Field that failed validation
        user_id: User ID
        context: Additional context
        
    Returns:
        Dictionary with error response
    """
    helper = global_validation_helper
    
    error_info = helper.create_validation_error_message(validation_result, field, user_id)
    retry_prompt = helper.create_retry_prompt(field, context)
    
    return {
        'success': False,
        'message': f"{error_info['message']}\n\n{retry_prompt}",
        'keyboard': error_info['keyboard'],
        'attempt_count': error_info['attempt_count'],
        'show_help': error_info['show_help'],
        'field': field
    }


def create_validation_success_response(field: str, value: Any, user_id: int, 
                                     next_message: str = "") -> Dict[str, Any]:
    """
    Create standardized validation success response
    
    Args:
        field: Field that was validated
        value: Validated value
        user_id: User ID
        next_message: Next step message
        
    Returns:
        Dictionary with success response
    """
    helper = global_validation_helper
    success_msg = helper.create_success_message(field, value, user_id)
    
    message = success_msg
    if next_message:
        message += f"\n\n{next_message}"
    
    return {
        'success': True,
        'message': message,
        'value': value,
        'field': field
    }
