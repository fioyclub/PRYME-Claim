"""
Day-off request management for the Telegram Claim Bot.

This module provides the DayOffManager class that handles day-off request process
with simplified logic (state management now handled by ConversationHandler).
"""

import asyncio
import logging
from datetime import datetime
import pytz
from models import DayOffRequest, UserRole

from user_manager import UserManager
from keyboards import KeyboardBuilder
from error_handler import global_error_handler, with_error_handling

logger = logging.getLogger(__name__)


class DayOffManager:
    """
    Manages day-off request submission process.
    
    This class handles day-off request validation and Google Sheets integration.
    State management is now handled by ConversationHandler in bot_handler.py.
    """
    
    def __init__(self, lazy_client_manager, user_manager: UserManager):
        """
        Initialize the DayOffManager with lazy loading.
        
        Args:
            lazy_client_manager: Lazy client manager for Google API clients
            user_manager: User manager for user data and permissions
        """
        self.lazy_client_manager = lazy_client_manager
        self.user_manager = user_manager
        self.error_handler = global_error_handler
        
        logger.info("DayOffManager initialized with ConversationHandler support")
    
    def start_dayoff_request(self, user_id: int) -> dict:
        """
        Start the day-off request process for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dict containing response message and keyboard
        """
        try:
            # Check if user is registered and get user data
            user_data = self.user_manager.get_user_data(user_id)
            
            if not user_data:
                logger.info("User %d attempted day-off request but is not registered", user_id)
                return {
                    'success': False,
                    'message': 'You need to register first to request day-off. Please use /register command.',
                    'keyboard': KeyboardBuilder.register_now_keyboard()
                }
            
            # Check if user role allows day-off requests (Staff and Manager only)
            if user_data.role not in [UserRole.STAFF, UserRole.MANAGER]:
                logger.info("User %d (%s) attempted day-off request but role %s not allowed", 
                           user_id, user_data.name, user_data.role.value)
                return {
                    'success': False,
                    'message': f'Day-off requests are only available for Staff and Manager roles.\n\nYour current role: {user_data.role.value}',
                    'keyboard': KeyboardBuilder.start_claim_keyboard()
                }
            
            logger.info("Started day-off request process for user %d (%s)", user_id, user_data.name)
            
            return {
                'success': True,
                'message': f'🗓️ <b>Day-off Request System</b>\n\nHello <b>{user_data.name}</b>!\n\nIs this a <b>One-day</b> or <b>Multiple-day</b> day-off?\n\nPlease select an option below:',
                'keyboard': KeyboardBuilder.dayoff_type_keyboard()
            }
            
        except Exception as e:
            logger.error("Error starting day-off request for user %d: %s", user_id, e)
            return {
                'success': False,
                'message': 'Error starting day-off request, please try again later.',
                'keyboard': None
            }
    
    def save_dayoff_request(self, user_id: int, dayoff_type: str, dayoff_date: str, reason: str) -> bool:
        """
        Save completed day-off request to Google Sheets
        
        Args:
            user_id: Telegram user ID
            dayoff_type: Type of day-off ('oneday' or 'multiday')
            dayoff_date: Date string (DD/MM/YYYY or DD/MM/YYYY - DD/MM/YYYY)
            reason: Reason for day-off
            
        Returns:
            bool: True if successful
        """
        try:
            # Get user data
            user_data = self.user_manager.get_user_data(user_id)
            if not user_data:
                logger.error("Cannot save day-off request: user %d not found", user_id)
                return False
            
            # Create day-off request object
            dayoff_request = DayOffRequest(
                request_date=datetime.now(),
                dayoff_date=dayoff_date,
                reason=reason,
                submitted_by=user_id,
                submitted_by_name=user_data.name,
                status="Pending"
            )
            
            # Prepare data for Google Sheets
            dayoff_data = {
                'request_date': dayoff_request.request_date.strftime('%d/%m/%Y %I:%M%p'),
                'dayoff_date': dayoff_request.dayoff_date,
                'reason': dayoff_request.reason,
                'submitted_by': dayoff_request.submitted_by,
                'submitted_by_name': dayoff_request.submitted_by_name,
                'status': dayoff_request.status
            }
            
            # Get sheets client with lazy loading
            sheets_client = self.lazy_client_manager.get_sheets_client()
            
            # Use asyncio to call async method
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            success = loop.run_until_complete(
                sheets_client.append_dayoff_data(dayoff_data)
            )
            
            if success:
                logger.info("Successfully saved day-off request for user %d (%s)", user_id, user_data.name)
                return True
            else:
                logger.error("Failed to save day-off request for user %d", user_id)
                return False
            
        except Exception as e:
            logger.error("Error saving day-off request for user %d: %s", user_id, e)
            return False
    
    def validate_date_format(self, date_str: str) -> tuple:
        """
        Validate date format (DD/MM/YYYY)
        
        Args:
            date_str: Date string to validate
            
        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            # Remove extra whitespace
            date_str = date_str.strip()
            
            # Check basic format
            if not date_str:
                return False, "Date cannot be empty"
            
            # Try to parse the date
            try:
                parsed_date = datetime.strptime(date_str, '%d/%m/%Y')
            except ValueError:
                return False, "Invalid date format. Please use DD/MM/YYYY format (e.g., 25/08/2025)"
            
            # Check if date is in the future
            today = datetime.now().date()
            if parsed_date.date() <= today:
                return False, "Day-off date must be in the future"
            
            return True, None
            
        except Exception as e:
            logger.error(f"Error validating date format: {e}")
            return False, "Error validating date, please try again"
    
    def validate_reason(self, reason: str) -> tuple:
        """
        Validate day-off reason
        
        Args:
            reason: Reason string to validate
            
        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            if not reason or not reason.strip():
                return False, "Reason cannot be empty"
            
            reason = reason.strip()
            
            if len(reason) < 3:
                return False, "Reason must be at least 3 characters long"
            
            if len(reason) > 200:
                return False, "Reason cannot exceed 200 characters"
            
            return True, None
            
        except Exception as e:
            logger.error(f"Error validating reason: {e}")
            return False, "Error validating reason, please try again"
