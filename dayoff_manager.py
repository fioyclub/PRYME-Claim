"""
Day-off request management for the Telegram Claim Bot.

This module provides the DayOffManager class that handles day-off request process,
validation, and data storage with comprehensive error handling.
"""

import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional
from models import DayOffRequest, UserStateType, UserRole
from state_manager import StateManager
from sheets_client import SheetsClient
from user_manager import UserManager
from keyboards import KeyboardBuilder
from error_handler import global_error_handler

logger = logging.getLogger(__name__)


class DayOffManager:
    """
    Manages day-off request submission process.
    
    This class handles the complete day-off request flow, validates input data,
    and stores requests in Google Sheets.
    """
    
    def __init__(self, sheets_client: SheetsClient, state_manager: StateManager, user_manager: UserManager):
        """
        Initialize the DayOffManager.
        
        Args:
            sheets_client: Google Sheets client for data storage
            state_manager: State manager for tracking conversation states
            user_manager: User manager for user data and permissions
        """
        self.sheets_client = sheets_client
        self.state_manager = state_manager
        self.user_manager = user_manager
        self.error_handler = global_error_handler
        
        logger.info("DayOffManager initialized")
    
    def start_dayoff_request(self, user_id: int) -> Dict[str, Any]:
        """
        Start the day-off request process for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dictionary with request start information
        """
        try:
            # Check if user is registered
            if not self.user_manager.is_user_registered(user_id):
                logger.info("Unregistered user %d attempted to request day-off", user_id)
                return {
                    'success': False,
                    'message': 'You need to register first to use this feature. Please use /register command to register.',
                    'keyboard': KeyboardBuilder.register_now_keyboard()
                }
            
            # Check user role permissions
            user_data = self.user_manager.get_user_data(user_id)
            if not user_data:
                logger.error("Could not get user data for registered user %d", user_id)
                return {
                    'success': False,
                    'message': 'Unable to get user information, please try again later.',
                    'keyboard': None
                }
            
            # Check if user role is allowed (Staff and Manager only)
            if user_data.role == UserRole.AMBASSADOR:
                logger.info("Ambassador user %d attempted to request day-off", user_id)
                return {
                    'success': False,
                    'message': '🚫 Sorry, your role does not allow you to use this command.',
                    'keyboard': None
                }
            
            # Check if user is already in day-off request process
            if self.state_manager.is_user_requesting_dayoff(user_id):
                logger.info("User %d is already in day-off request process", user_id)
                current_state, temp_data = self.state_manager.get_user_state(user_id)
                
                if current_state == UserStateType.DAYOFF_DATE:
                    message = '<b>🗓️ Please enter your day-off date</b>\n\nExample: <code>25/08/2025</code> (Use DD/MM/YYYY format)'
                elif current_state == UserStateType.DAYOFF_REASON:
                    message = '<b>✏️ Please enter your reason for this day-off</b>\n\nExample: <i>Family event</i>, <i>Medical appointment</i>, etc.'
                else:
                    message = 'Please continue to complete the day-off request process'
                
                return {
                    'success': True,
                    'message': message,
                    'keyboard': KeyboardBuilder.cancel_keyboard()
                }
            
            # Check if user is in other processes
            if not self.state_manager.is_user_idle(user_id):
                logger.info("User %d attempted day-off request while in other process", user_id)
                return {
                    'success': False,
                    'message': 'Please complete your current process first before requesting day-off.',
                    'keyboard': None
                }
            
            # Start new day-off request process
            self.state_manager.set_user_state(user_id, UserStateType.DAYOFF_DATE)
            
            logger.info("Started day-off request process for user %d (%s)", user_id, user_data.name)
            return {
                'success': True,
                'message': '<b>🗓️ Please enter your day-off date</b>\n\nExample: <code>25/08/2025</code> (Use DD/MM/YYYY format)',
                'keyboard': KeyboardBuilder.cancel_keyboard()
            }
            
        except Exception as e:
            logger.error("Error starting day-off request for user %d: %s", user_id, e)
            return {
                'success': False,
                'message': 'Failed to start day-off request, please try again later.',
                'keyboard': None
            }
    
    def process_dayoff_step(self, user_id: int, step: str, data: str) -> Dict[str, Any]:
        """
        Process a step in the day-off request flow.
        
        Args:
            user_id: Telegram user ID
            step: Current step (date or reason)
            data: User input data
            
        Returns:
            Dictionary with step processing result
        """
        try:
            current_state, temp_data = self.state_manager.get_user_state(user_id)
            
            # Validate that user is in day-off request process
            if not self.state_manager.is_user_requesting_dayoff(user_id):
                logger.warning("User %d not in day-off request process for step %s", user_id, step)
                return {
                    'success': False,
                    'message': 'Please use /dayoff command first to start day-off request.',
                    'keyboard': None
                }
            
            # Process based on current step
            if step == 'date' or current_state == UserStateType.DAYOFF_DATE:
                return self._process_date_input(user_id, data, temp_data)
            
            elif step == 'reason' or current_state == UserStateType.DAYOFF_REASON:
                return self._process_reason_input(user_id, data, temp_data)
            
            else:
                logger.warning("Unknown day-off step %s for user %d", step, user_id)
                return {
                    'success': False,
                    'message': 'Day-off request process error, please restart with /dayoff.',
                    'keyboard': None
                }
                
        except Exception as e:
            logger.error("Error processing day-off step %s for user %d: %s", step, user_id, e)
            return {
                'success': False,
                'message': 'Error processing day-off request, please try again.',
                'keyboard': KeyboardBuilder.cancel_keyboard()
            }
    
    def _process_date_input(self, user_id: int, date_str: str, temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process date input step."""
        try:
            # Validate date format (DD/MM/YYYY)
            if not self._validate_date_format(date_str):
                logger.info("Invalid date format from user %d: %s", user_id, date_str)
                return {
                    'success': False,
                    'message': '❌ Invalid date format. Please use DD/MM/YYYY format.\n\nExample: <code>25/08/2025</code>',
                    'keyboard': KeyboardBuilder.cancel_keyboard()
                }
            
            # Store date and move to reason input
            self.state_manager.update_user_data(user_id, 'dayoff_date', date_str.strip())
            self.state_manager.set_user_state(user_id, UserStateType.DAYOFF_REASON)
            
            logger.info("User %d provided valid date, moving to reason input", user_id)
            return {
                'success': True,
                'message': '<b>✏️ Please enter your reason for this day-off</b>\n\nExample: <i>Family event</i>, <i>Medical appointment</i>, etc.',
                'keyboard': KeyboardBuilder.cancel_keyboard()
            }
            
        except Exception as e:
            self.error_handler.log_error_details(e, "dayoff_date_processing", user_id)
            return {
                'success': False,
                'message': '❌ Error processing date, please try again',
                'keyboard': KeyboardBuilder.cancel_keyboard()
            }
    
    def _process_reason_input(self, user_id: int, reason: str, temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process reason input step."""
        try:
            # Validate reason
            if not reason or not reason.strip() or len(reason.strip()) < 3:
                logger.info("Invalid reason from user %d: %s", user_id, reason)
                return {
                    'success': False,
                    'message': '❌ Please provide a valid reason (at least 3 characters).\n\nExample: <i>Family event</i>, <i>Medical appointment</i>, etc.',
                    'keyboard': KeyboardBuilder.cancel_keyboard()
                }
            
            # Store reason and complete request
            self.state_manager.update_user_data(user_id, 'reason', reason.strip())
            
            # Get updated temp_data with the new reason
            _, updated_temp_data = self.state_manager.get_user_state(user_id)
            
            # Complete day-off request
            return self._complete_dayoff_request(user_id, updated_temp_data)
            
        except Exception as e:
            self.error_handler.log_error_details(e, "dayoff_reason_processing", user_id)
            return {
                'success': False,
                'message': '❌ Error processing reason, please try again',
                'keyboard': KeyboardBuilder.cancel_keyboard()
            }
    
    def _complete_dayoff_request(self, user_id: int, temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Complete the day-off request process."""
        try:
            # Get all collected data
            dayoff_date = temp_data.get('dayoff_date')
            reason = temp_data.get('reason')
            
            if not all([dayoff_date, reason]):
                logger.error("Missing day-off data for user %d: date=%s, reason=%s", 
                           user_id, dayoff_date, reason)
                return {
                    'success': False,
                    'message': 'Day-off request information incomplete, please restart with /dayoff.',
                    'keyboard': None
                }
            
            # Get user data
            user_data = self.user_manager.get_user_data(user_id)
            if not user_data:
                logger.error("Could not get user data for user %d during completion", user_id)
                return {
                    'success': False,
                    'message': 'Unable to get user information, please try again.',
                    'keyboard': None
                }
            
            # Create DayOffRequest object
            dayoff_request = DayOffRequest(
                request_date=datetime.now(),
                dayoff_date=dayoff_date,
                reason=reason,
                submitted_by=user_id,
                submitted_by_name=user_data.name,
                status="Pending"
            )
            
            # Save to Google Sheets
            dayoff_data = dayoff_request.to_dict()
            
            # Use asyncio to run the async method
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            success = loop.run_until_complete(
                self.sheets_client.append_dayoff_data(dayoff_data)
            )
            
            if not success:
                logger.error("Failed to save day-off request data for user %d", user_id)
                return {
                    'success': False,
                    'message': 'Failed to save day-off request, please try again.',
                    'keyboard': KeyboardBuilder.cancel_keyboard()
                }
            
            # Clear user state
            self.state_manager.clear_user_state(user_id)
            
            logger.info("Successfully completed day-off request for user %d (%s)", user_id, user_data.name)
            return {
                'success': True,
                'message': '<b>✅ Your day-off request has been submitted!</b>\n\n🎉 We\'ll notify you once it\'s approved. 📩',
                'keyboard': None
            }
            
        except Exception as e:
            logger.error("Error completing day-off request for user %d: %s", user_id, e)
            return {
                'success': False,
                'message': 'Error completing day-off request, please try again.',
                'keyboard': KeyboardBuilder.cancel_keyboard()
            }
    
    def cancel_dayoff_request(self, user_id: int) -> Dict[str, Any]:
        """
        Cancel ongoing day-off request process.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dictionary with cancellation result
        """
        try:
            if not self.state_manager.is_user_requesting_dayoff(user_id):
                return {
                    'success': False,
                    'message': 'No ongoing day-off request process',
                    'keyboard': None
                }
            
            self.state_manager.clear_user_state(user_id)
            
            logger.info("Cancelled day-off request for user %d", user_id)
            return {
                'success': True,
                'message': 'Day-off request cancelled',
                'keyboard': None
            }
            
        except Exception as e:
            logger.error("Error cancelling day-off request for user %d: %s", user_id, e)
            return {
                'success': False,
                'message': 'Error cancelling day-off request',
                'keyboard': None
            }
    
    def _validate_date_format(self, date_str: str) -> bool:
        """
        Validate date format (DD/MM/YYYY).
        
        Args:
            date_str: Date string to validate
            
        Returns:
            True if format is valid
        """
        try:
            # Check format with regex
            pattern = r'^(\d{1,2})/(\d{1,2})/(\d{4})$'
            match = re.match(pattern, date_str.strip())
            
            if not match:
                return False
            
            day, month, year = map(int, match.groups())
            
            # Basic validation
            if not (1 <= day <= 31):
                return False
            if not (1 <= month <= 12):
                return False
            if not (2020 <= year <= 2030):  # Reasonable year range
                return False
            
            # Try to create datetime to validate the date
            datetime(year, month, day)
            return True
            
        except (ValueError, TypeError):
            return False