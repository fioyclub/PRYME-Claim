"""
User management for the Telegram Claim Bot.

This module provides the UserManager class that handles user registration process,
authentication, and permission checking with comprehensive error handling.
"""

import logging
import gc
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
    
    This class handles the complete user registration flow, tracks registration
    states, and provides user authentication and permission checking.
    """
    
    def __init__(self, lazy_client_manager):
        """
        Initialize the UserManager with lazy loading.
        
        Args:
            lazy_client_manager: Lazy client manager for Google API clients
        """
        self.lazy_client_manager = lazy_client_manager
        self.error_handler = global_error_handler
        
        logger.info("UserManager initialized with lazy loading")
    
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
                register_date=datetime.fromisoformat(user_data['register_date']) 
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
    
    def start_registration(self, user_id: int) -> Dict[str, Any]:
        """
        Start the registration process for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dictionary with registration start information
        """
        try:
            # Validate user ID
            is_valid, error_msg = validate_telegram_user_id_legacy(user_id)
            if not is_valid:
                logger.warning("Cannot start registration for invalid user ID %s: %s", 
                             user_id, error_msg)
                return {
                    'success': False,
                    'message': 'Invalid user ID, please try again',
                    'next_step': None
                }
            
            # Check if user is already registered
            if self.is_user_registered(user_id):
                logger.info("User %d attempted to register but is already registered", user_id)
                return {
                    'success': False,
                    'message': 'You are already registered, you can directly use /claim to submit expense claims',
                    'next_step': None
                }
            
            # Check if user is already in registration process
            if self.state_manager.is_user_registering(user_id):
                logger.info("User %d is already in registration process", user_id)
                current_state, temp_data = self.state_manager.get_user_state(user_id)
                
                # Return appropriate message based on current state
                if current_state == UserStateType.REGISTERING_NAME:
                    message = '<b>Welcome to PRYMEPLUS Claim System</b> ✨\n\nPlease enter your <b>NAME</b> 📝'
                elif current_state == UserStateType.REGISTERING_PHONE:
                    message = 'Please enter your <b>PHONE NUMBER</b> 📱'
                elif current_state == UserStateType.REGISTERING_ROLE:
                    message = 'Please select your <b>ROLE</b> 👤'
                else:
                    message = 'Please continue to complete the registration process'
                
                return {
                    'success': True,
                    'message': message,
                    'next_step': current_state.value,
                    'temp_data': temp_data
                }
            
            # Start new registration process
            self.state_manager.set_user_state(user_id, UserStateType.REGISTERING_NAME)
            
            logger.info("Started registration process for user %d", user_id)
            return {
                'success': True,
                'message': '<b>Welcome to PRYMEPLUS Claim System</b> ✨\n\nPlease enter your <b>NAME</b> 📝',
                'next_step': UserStateType.REGISTERING_NAME.value,
                'temp_data': {}
            }
            
        except Exception as e:
            logger.error("Error starting registration for user %d: %s", user_id, e)
            return {
                'success': False,
                'message': 'Failed to start registration, please try again later',
                'next_step': None
            }
    
    def process_registration_step(self, user_id: int, step: str, data: str) -> Dict[str, Any]:
        """
        Process a step in the registration flow.
        
        Args:
            user_id: Telegram user ID
            step: Current registration step
            data: User input data
            
        Returns:
            Dictionary with step processing result
        """
        try:
            current_state, temp_data = self.state_manager.get_user_state(user_id)
            
            # Validate that user is in registration process
            if not self.state_manager.is_user_registering(user_id):
                logger.warning("User %d not in registration process for step %s", user_id, step)
                return {
                    'success': False,
                    'message': 'Please use /register command first to start registration',
                    'next_step': None
                }
            
            # Process based on current step
            if step == UserStateType.REGISTERING_NAME.value or current_state == UserStateType.REGISTERING_NAME:
                return self._process_name_input(user_id, data, temp_data)
            
            elif step == UserStateType.REGISTERING_PHONE.value or current_state == UserStateType.REGISTERING_PHONE:
                return self._process_phone_input(user_id, data, temp_data)
            
            elif step == UserStateType.REGISTERING_ROLE.value or current_state == UserStateType.REGISTERING_ROLE:
                return self._process_role_selection(user_id, data, temp_data)
            
            else:
                logger.warning("Unknown registration step %s for user %d", step, user_id)
                return {
                    'success': False,
                    'message': 'Registration process error, please restart registration',
                    'next_step': None
                }
                
        except Exception as e:
            logger.error("Error processing registration step %s for user %d: %s", step, user_id, e)
            return {
                'success': False,
                'message': 'Error processing registration information, please try again',
                'next_step': None
            }
    
    def _process_name_input(self, user_id: int, name: str, temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process name input step with enhanced error handling and retry flow."""
        try:
            # Validate name using new validation system
            validation_result = validate_name(name)
            
            if not validation_result.is_valid:
                logger.info("Invalid name input from user %d: %s", user_id, validation_result.error_message)
                
                # Use validation helper for comprehensive error handling
                error_response = create_validation_error_response(
                    validation_result, 'name', user_id, 
                    "during registration"
                )
                
                return {
                    'success': False,
                    'message': error_response['message'],
                    'keyboard': error_response.get('keyboard'),
                    'next_step': UserStateType.REGISTERING_NAME.value,
                    'help_available': True,
                    'attempt_count': error_response['attempt_count']
                }
            
            # Success - use validation helper for success response
            success_response = create_validation_success_response(
                'name', validation_result.value, user_id,
                "Please enter your <b>PHONE NUMBER</b> 📱:"
            )
            
            # Store name and move to phone input
            self.state_manager.update_user_data(user_id, 'name', validation_result.value.strip())
            self.state_manager.set_user_state(user_id, UserStateType.REGISTERING_PHONE)
            
            logger.info("User %d provided valid name, moving to phone input", user_id)
            return {
                'success': True,
                'message': success_response['message'],
                'next_step': UserStateType.REGISTERING_PHONE.value
            }
            
        except Exception as e:
            self.error_handler.log_error_details(e, "name_input_processing", user_id)
            return {
                'success': False,
                'message': '❌ Error processing name, please try again',
                'next_step': UserStateType.REGISTERING_NAME.value
            }
    
    def _process_phone_input(self, user_id: int, phone: str, temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process phone input step with enhanced error handling and retry flow."""
        try:
            # Validate phone number using new validation system
            validation_result = validate_phone_number(phone)
            
            if not validation_result.is_valid:
                logger.info("Invalid phone input from user %d: %s", user_id, validation_result.error_message)
                
                # Use validation helper for comprehensive error handling
                error_response = create_validation_error_response(
                    validation_result, 'phone', user_id,
                    "during registration"
                )
                
                return {
                    'success': False,
                    'message': error_response['message'],
                    'keyboard': error_response.get('keyboard'),
                    'next_step': UserStateType.REGISTERING_PHONE.value,
                    'help_available': True,
                    'attempt_count': error_response['attempt_count']
                }
            
            # Success - use validation helper for success response
            success_response = create_validation_success_response(
                'phone', validation_result.value, user_id,
                "Please select your <b>ROLE</b> 👤:"
            )
            
            # Store phone and move to role selection
            self.state_manager.update_user_data(user_id, 'phone', validation_result.value)
            self.state_manager.set_user_state(user_id, UserStateType.REGISTERING_ROLE)
            
            logger.info("User %d provided valid phone, moving to role selection", user_id)
            return {
                'success': True,
                'message': success_response['message'],
                'next_step': UserStateType.REGISTERING_ROLE.value,
                'show_role_keyboard': True
            }
            
        except Exception as e:
            self.error_handler.log_error_details(e, "phone_input_processing", user_id)
            return {
                'success': False,
                'message': '❌ Error processing phone number, please try again',
                'next_step': UserStateType.REGISTERING_PHONE.value
            }
    
    def _process_role_selection(self, user_id: int, role: str, temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process role selection step."""
        # Validate role
        try:
            user_role = UserRole(role)
        except ValueError:
            logger.info("Invalid role selection from user %d: %s", user_id, role)
            return {
                'success': False,
                'message': 'Please select a valid role option',
                'next_step': UserStateType.REGISTERING_ROLE.value,
                'show_role_keyboard': True
            }
        
        # Store role and complete registration
        self.state_manager.update_user_data(user_id, 'role', role)
        
        # Get updated temp_data with the new role
        _, updated_temp_data = self.state_manager.get_user_state(user_id)
        
        # Complete registration
        return self._complete_registration(user_id, updated_temp_data)
    
    def _complete_registration(self, user_id: int, temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Complete the registration process."""
        try:
            # Get all collected data
            name = temp_data.get('name')
            phone = temp_data.get('phone')
            role = temp_data.get('role')
            
            if not all([name, phone, role]):
                logger.error("Missing registration data for user %d: name=%s, phone=%s, role=%s", 
                           user_id, name, phone, role)
                return {
                    'success': False,
                    'message': 'Registration information incomplete, please restart registration',
                    'next_step': None
                }
            
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
                'register_date': registration.register_date.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Use asyncio to run the async method
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Get sheets client with lazy loading
            sheets_client = self.lazy_client_manager.get_sheets_client()
            success = loop.run_until_complete(
                sheets_client.append_registration_data(registration.role.value, user_data)
            )
            
            if not success:
                logger.error("Failed to save registration data for user %d", user_id)
                return {
                    'success': False,
                    'message': 'Failed to save registration, please try again',
                    'next_step': None
                }
            
            # Clear user state
            self.state_manager.clear_user_state(user_id)
            
            logger.info("Successfully completed registration for user %d (%s)", user_id, name)
            return {
                'success': True,
                'message': f'<b>Registration successful!!</b> 🎉\n\n<b>PRYMEPLUS</b> welcomes you!! 💖\n\nYou can now use <code>/claim</code> command to submit your Claims.',
                'next_step': None,
                'user_data': registration.to_dict()
            }
            
        except Exception as e:
            logger.error("Error completing registration for user %d: %s", user_id, e)
            return {
                'success': False,
                'message': 'Error completing registration, please try again',
                'next_step': None
            }
    
    def cancel_registration(self, user_id: int) -> Dict[str, Any]:
        """
        Cancel ongoing registration process.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dictionary with cancellation result
        """
        try:
            if not self.state_manager.is_user_registering(user_id):
                return {
                    'success': False,
                    'message': 'No ongoing registration process'
                }
            
            self.state_manager.clear_user_state(user_id)
            
            logger.info("Cancelled registration for user %d", user_id)
            return {
                'success': True,
                'message': 'Registration cancelled'
            }
            
        except Exception as e:
            logger.error("Error cancelling registration for user %d: %s", user_id, e)
            return {
                'success': False,
                'message': 'Error cancelling registration'
            }
    
    def get_registration_progress(self, user_id: int) -> Dict[str, Any]:
        """
        Get current registration progress for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dictionary with progress information
        """
        try:
            if not self.state_manager.is_user_registering(user_id):
                return {
                    'in_progress': False,
                    'current_step': None,
                    'collected_data': {}
                }
            
            current_state, temp_data = self.state_manager.get_user_state(user_id)
            
            return {
                'in_progress': True,
                'current_step': current_state.value,
                'collected_data': {
                    'name': temp_data.get('name'),
                    'phone': temp_data.get('phone'),
                    'role': temp_data.get('role')
                }
            }
            
        except Exception as e:
            logger.error("Error getting registration progress for user %d: %s", user_id, e)
            return {
                'in_progress': False,
                'current_step': None,
                'collected_data': {}
            }
    
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
