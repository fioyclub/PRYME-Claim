"""
User management for the Telegram Claim Bot.

This module provides the UserManager class that handles user registration process,
authentication, and permission checking. State management is now handled by ConversationHandler.
"""

import logging
import gc
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from models import UserRegistration, UserRole
from validation import (
    validate_name, validate_phone_number, validate_telegram_user_id_legacy,
    get_validation_help_message
)
from validation_helper import (
    global_validation_helper, create_validation_error_response, 
    create_validation_success_response
)
from error_handler import global_error_handler, with_error_handling

logger = logging.getLogger(__name__)


class UserManager:
    """
    Manages user registration and authentication.
    
    This class handles user registration validation and Google Sheets integration.
    State management is now handled by ConversationHandler in bot_handler.py.
    """
    
    def __init__(self, lazy_client_manager):
        """
        Initialize the UserManager with lazy loading.
        
        Args:
            lazy_client_manager: Lazy client manager for Google API clients
        """
        self.lazy_client_manager = lazy_client_manager
        self.error_handler = global_error_handler
        
        logger.info("UserManager initialized with ConversationHandler support")
    
    def is_user_registered(self, user_id: int) -> bool:
        """
        Check if a user is already registered with memory optimization.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if user is registered, False otherwise
        """
        import gc
        
        user_data = None
        
        try:
            # Validate user ID
            is_valid, error_msg = validate_telegram_user_id_legacy(user_id)
            if not is_valid:
                logger.warning("Invalid user ID %s: %s", user_id, error_msg)
                return False
            
            # Check in Google Sheets (lazy loading)
            sheets_client = self.lazy_client_manager.get_sheets_client()
            user_data = sheets_client._get_user_sync(user_id)
            is_registered = user_data is not None
            
            logger.debug("User %d registration status: %s", user_id, is_registered)
            return is_registered
            
        except Exception as e:
            logger.error("Error checking registration for user %d: %s", user_id, e)
            return False
        finally:
            # Clean up user data immediately
            if user_data:
                del user_data
            gc.collect()
    
    def get_user_data(self, user_id: int) -> Optional[UserRegistration]:
        """
        Get user registration data with memory optimization.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            UserRegistration object if found, None otherwise
        """
        import gc
        
        user_data = None
        registration = None
        
        try:
            # Validate user ID
            is_valid, error_msg = validate_telegram_user_id_legacy(user_id)
            if not is_valid:
                logger.warning("Invalid user ID %s: %s", user_id, error_msg)
                return None
            
            # Get data from Google Sheets (lazy loading)
            sheets_client = self.lazy_client_manager.get_sheets_client()
            user_data = sheets_client._get_user_sync(user_id)
            
            if not user_data:
                return None
            
            # Convert to UserRegistration object
            registration = UserRegistration(
                telegram_user_id=user_data['telegram_user_id'],
                name=user_data['name'],
                phone=user_data['phone'],
                role=UserRole(user_data['role']),
                register_date=datetime.strptime(user_data['register_date'], '%d/%m/%Y %I:%M%p') 
                    if user_data['register_date'] else datetime.now()
            )
            
            logger.debug("Retrieved user data for %d: %s", user_id, user_data['name'])
            return registration
            
        except Exception as e:
            logger.error("Error getting user data for %d: %s", user_id, e)
            return None
        finally:
            # Clean up large objects immediately
            if user_data:
                del user_data
            gc.collect()
    
    def process_registration_step(self, user_id: int, step: str, data: str) -> Dict[str, Any]:
        """
        Process a single registration step (used by ConversationHandler).
        
        Args:
            user_id: Telegram user ID
            step: Registration step ('name', 'phone', 'role')
            data: User input data
            
        Returns:
            Dict containing validation result and next step information
        """
        try:
            if step == 'name':
                return self._validate_name_input(user_id, data)
            elif step == 'phone':
                return self._validate_phone_input(user_id, data)
            elif step == 'role':
                return self._complete_registration(user_id, data)
            else:
                logger.warning("Unknown registration step: %s", step)
                return {
                    'success': False,
                    'message': 'Unknown registration step, please restart registration.',
                    'next_step': None
                }
                
        except Exception as e:
            logger.error("Error processing registration step %s for user %d: %s", step, user_id, e)
            return {
                'success': False,
                'message': 'Error processing registration, please try again later.',
                'next_step': None
            }
    
    def _validate_name_input(self, user_id: int, name: str) -> Dict[str, Any]:
        """Validate name input"""
        try:
            # Validate name using validation system
            validation_result = validate_name(name)
            
            if not validation_result.is_valid:
                logger.info("Invalid name input from user %d: %s", user_id, validation_result.error_message)
                
                error_response = create_validation_error_response(
                    validation_result, 'name', user_id,
                    "during registration"
                )
                
                return {
                    'success': False,
                    'message': error_response['message'],
                    'keyboard': error_response.get('keyboard'),
                    'attempt_count': error_response['attempt_count']
                }
            
            # Success
            success_response = create_validation_success_response(
                'name', validation_result.value, user_id
            )
            
            logger.info("User %d provided valid name, moving to phone input", user_id)
            
            return {
                'success': True,
                'message': success_response['message'],
                'next_step': 'phone'
            }
            
        except Exception as e:
            logger.error("Error validating name for user %d: %s", user_id, e)
            return {
                'success': False,
                'message': 'Error validating name, please try again.',
                'next_step': None
            }
    
    def _validate_phone_input(self, user_id: int, phone: str) -> Dict[str, Any]:
        """Validate phone input"""
        try:
            # Validate phone using validation system
            validation_result = validate_phone_number(phone)
            
            if not validation_result.is_valid:
                logger.info("Invalid phone input from user %d: %s", user_id, validation_result.error_message)
                
                error_response = create_validation_error_response(
                    validation_result, 'phone', user_id,
                    "during registration"
                )
                
                return {
                    'success': False,
                    'message': error_response['message'],
                    'keyboard': error_response.get('keyboard'),
                    'attempt_count': error_response['attempt_count']
                }
            
            # Success
            success_response = create_validation_success_response(
                'phone', validation_result.value, user_id
            )
            
            logger.info("User %d provided valid phone, moving to role selection", user_id)
            
            return {
                'success': True,
                'message': success_response['message'],
                'next_step': 'role'
            }
            
        except Exception as e:
            logger.error("Error validating phone for user %d: %s", user_id, e)
            return {
                'success': False,
                'message': 'Error validating phone, please try again.',
                'next_step': None
            }
    
    def _complete_registration(self, user_id: int, role: str) -> Dict[str, Any]:
        """Complete registration with role selection"""
        try:
            # This method is called from ConversationHandler with context data
            # The actual registration completion happens in the ConversationHandler
            logger.info("User %d selected role: %s", user_id, role)
            
            return {
                'success': True,
                'message': f'✅ Role selected: {role}',
                'next_step': 'complete'
            }
            
        except Exception as e:
            logger.error("Error completing registration for user %d: %s", user_id, e)
            return {
                'success': False,
                'message': 'Error completing registration, please try again.',
                'next_step': None
            }
    
    def save_registration(self, user_id: int, name: str, phone: str, role: str) -> bool:
        """
        Save completed registration to Google Sheets
        
        Args:
            user_id: Telegram user ID
            name: User's name
            phone: User's phone number
            role: User's role
            
        Returns:
            bool: True if successful
        """
        try:
            # Create UserRegistration object
            registration = UserRegistration(
                telegram_user_id=user_id,
                name=name,
                phone=phone,
                role=UserRole(role),
                register_date=datetime.now()
            )
            
            # Save to Google Sheets
            user_data = {
                'telegram_user_id': registration.telegram_user_id,
                'name': registration.name,
                'phone': registration.phone,
                'role': registration.role.value,
                'register_date': registration.register_date.isoformat()
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
                sheets_client.append_registration_data(registration.role.value, user_data)
            )
            
            if success:
                logger.info("Successfully saved registration for user %d (%s)", user_id, name)
                return True
            else:
                logger.error("Failed to save registration data for user %d", user_id)
                return False
            
        except Exception as e:
            logger.error("Error saving registration for user %d: %s", user_id, e)
            return False
    
    def check_user_permission(self, user_id: int, required_role: Optional[UserRole] = None) -> Tuple[bool, Optional[str]]:
        """
        Check if user has permission to perform an action with memory optimization.
        
        Args:
            user_id: Telegram user ID
            required_role: Optional required role for the action
            
        Returns:
            Tuple of (has_permission, error_message)
        """
        import gc
        
        user_data = None
        
        try:
            # Check if user is registered
            if not self.is_user_registered(user_id):
                return False, "You need to register first to use this feature. Please use /register command to register."
            
            # If no specific role required, registration is sufficient
            if required_role is None:
                return True, None
            
            # Get user data and check role
            user_data = self.get_user_data(user_id)
            if not user_data:
                return False, "Unable to get user information, please register again."
            
            # Check if user has required role or higher
            role_hierarchy = {
                UserRole.STAFF: 1,
                UserRole.MANAGER: 2,
                UserRole.AMBASSADOR: 3
            }
            
            user_level = role_hierarchy.get(user_data.role, 0)
            required_level = role_hierarchy.get(required_role, 0)
            
            if user_level >= required_level:
                return True, None
            else:
                return False, f"This feature requires {required_role.value} or higher permissions."
                
        except Exception as e:
            logger.error("Error checking permission for user %d: %s", user_id, e)
            return False, "Error checking permissions, please try again later."
        finally:
            # Clean up user data immediately
            if user_data:
                del user_data
            gc.collect()
