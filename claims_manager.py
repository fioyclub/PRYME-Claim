"""
Claims Manager for Telegram Claim Bot

This module provides the ClaimsManager class that handles the expense claim submission process,
including category selection, amount input, photo upload, and integration with Google services
with comprehensive error handling.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, Tuple, List
from io import BytesIO

from models import Claim, ClaimCategory, ClaimStatus
from sheets_client import SheetsClient
from drive_client import DriveClient
from config import Config
from validation import validate_amount, validate_photo_file, format_amount, get_validation_help_message
from validation_helper import (
    global_validation_helper, create_validation_error_response,
    create_validation_success_response
)
from keyboards import KeyboardBuilder
from error_handler import global_error_handler, with_error_handling

logger = logging.getLogger(__name__)


class ClaimsManager:
    """
    Manages the expense claim submission process.
    
    This class handles the multi-step claim submission flow including category selection,
    amount input, photo upload, and final submission with Google Sheets and Drive integration.
    """
    
    def __init__(self, lazy_client_manager, config: Config):
        """
        Initialize the ClaimsManager with lazy loading.
        
        Args:
            lazy_client_manager: Lazy client manager for Google API clients
            config: Configuration instance for accessing environment variables
        """
        self.lazy_client_manager = lazy_client_manager
        self.config = config
        self.error_handler = global_error_handler
        
        # Category mapping for callback data to enum
        self.category_mapping = {
            'category_food': ClaimCategory.FOOD,
            'category_transportation': ClaimCategory.TRANSPORTATION,
            'category_flight': ClaimCategory.FLIGHT,
            'category_event': ClaimCategory.EVENT,
            'category_ai': ClaimCategory.AI,
            'category_reception': ClaimCategory.RECEPTION,
            'category_other': ClaimCategory.OTHER
        }
        
        logger.info("ClaimsManager initialized")
    
    # Claim process is now handled by ConversationHandler in bot_handler.py
    # These methods are simplified for business logic only
    
    # Claim process is now handled by ConversationHandler in bot_handler.py
    # Individual step methods are called directly by the conversation handlers
    
    def _process_category_selection(self, user_id: int, callback_data: str) -> Dict[str, Any]:
        """Process category selection step."""
        try:
            # Validate category selection
            if callback_data not in self.category_mapping:
                return {
                    'message': 'Invalid category selection, please select again:',
                    'keyboard': KeyboardBuilder.claim_categories_keyboard(),
                    'success': False
                }
            
            category = self.category_mapping[callback_data]
            category_display = f"{category.value} {self._get_category_emoji(category)}"
            
            return {
                'message': f'Selected category: {category_display}\n\nPlease enter amount (RM):',
                'keyboard': KeyboardBuilder.cancel_keyboard(),
                'success': True,
                'category': category.value
            }
            
        except Exception as e:
            logger.error(f"Failed to process category selection for user {user_id}: {e}")
            raise
    
    def _process_amount_input(self, user_id: int, amount_text: str, category: str = None) -> Dict[str, Any]:
        """Process amount input step with enhanced error handling and retry flow."""
        try:
            # Validate amount using new validation system
            validation_result = validate_amount(amount_text)
            
            if not validation_result.is_valid:
                logger.info(f"Invalid amount input from user {user_id}: {validation_result.error_message}")
                
                # Use validation helper for comprehensive error handling
                error_response = create_validation_error_response(
                    validation_result, 'amount', user_id,
                    "during claim process"
                )
                
                return {
                    'message': error_response['message'],
                    'keyboard': error_response.get('keyboard', KeyboardBuilder.cancel_keyboard()),
                    'success': False,
                    'attempt_count': error_response['attempt_count']
                }
            
            # Success - use validation helper for success response
            formatted_amount = format_amount(validation_result.value)
            success_response = create_validation_success_response(
                'amount', formatted_amount, user_id,
                "Please upload receipt photo:"
            )
            
            # Check if category is "Other" - if so, ask for description
            if category and category == 'Other':
                return {
                    'message': '📝 Please enter what you are claiming for:\n\nExample: Stationery purchase, Parking fee, etc...',
                    'keyboard': KeyboardBuilder.cancel_keyboard(),
                    'success': True,
                    'amount': validation_result.value,
                    'needs_description': True
                }
            else:
                # For other categories, move directly to photo upload
                return {
                    'message': success_response['message'],
                    'keyboard': KeyboardBuilder.cancel_keyboard(),
                    'success': True,
                    'amount': validation_result.value,
                    'needs_description': False
                }
            
        except Exception as e:
            self.error_handler.log_error_details(e, "amount_input_processing", user_id)
            return {
                'message': '❌ Error processing amount, please try again',
                'keyboard': KeyboardBuilder.cancel_keyboard(),
                'success': False
            }
    
    def _process_other_description_input(self, user_id: int, description_text: str) -> Dict[str, Any]:
        """Process Other category description input step."""
        try:
            # Validate description
            if not description_text or not description_text.strip():
                return {
                    'message': '❌ Please provide a description for your claim.\n\nExample: Stationery purchase, Parking fee, etc...',
                    'keyboard': KeyboardBuilder.cancel_keyboard(),
                    'success': False
                }
            
            description = description_text.strip()
            
            # Validate minimum length
            if len(description) < 3:
                return {
                    'message': '❌ Description too short. Please provide at least 3 characters.\n\nExample: Stationery purchase, Parking fee, etc...',
                    'keyboard': KeyboardBuilder.cancel_keyboard(),
                    'success': False
                }
            
            logger.info(f"User {user_id} provided Other description: {description}")
            return {
                'message': f'✅ Description saved: <i>{description}</i>\n\nPlease upload receipt photo:',
                'keyboard': KeyboardBuilder.cancel_keyboard(),
                'success': True,
                'description': description
            }
            
        except Exception as e:
            logger.error(f"Failed to process Other description for user {user_id}: {e}")
            return {
                'message': '❌ Error processing description, please try again',
                'keyboard': KeyboardBuilder.cancel_keyboard(),
                'success': False
            }
    
    def _process_photo_upload(self, user_id: int, photo_data: bytes, claim_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process photo upload step with memory-optimized error handling."""
        try:
            logger.debug(f"Processing photo upload for user {user_id}, size: {len(photo_data)} bytes")
            
            # Validate photo using new validation system
            validation_result = validate_photo_file(photo_data)
            
            if not validation_result.is_valid:
                logger.info(f"Invalid photo upload from user {user_id}: {validation_result.error_message}")
                
                # Use validation helper for comprehensive error handling
                error_response = create_validation_error_response(
                    validation_result, 'photo', user_id,
                    "during claim process"
                )
                
                return {
                    'message': error_response['message'],
                    'keyboard': error_response.get('keyboard', KeyboardBuilder.cancel_keyboard()),
                    'success': False,
                    'attempt_count': error_response['attempt_count']
                }
            
            # Upload photo to Google Drive with memory optimization
            try:
                receipt_link = self.upload_receipt(user_id, photo_data, claim_data.get('category', 'Other'))
                success = True
                error_msg = None
                
                # Release memory immediately after successful upload to reduce memory usage
                del photo_data
                import gc
                gc.collect()
                logger.info("[MEMORY] Released file_data after successful Drive upload")
                
            except Exception as e:
                success = False
                receipt_link = None
                error_msg = str(e)
                logger.error(f"Photo upload failed for user {user_id}: {e}")
            
            if not success:
                return {
                    'message': error_msg or '❌ Failed to upload receipt photo, please try again later.',
                    'keyboard': KeyboardBuilder.cancel_keyboard(),
                    'success': False
                }
            
            # Add receipt link to claim data
            claim_data['receipt_link'] = receipt_link
            
            # Generate confirmation message
            confirmation_message = self._generate_confirmation_message(claim_data)
            
            return {
                'message': confirmation_message,
                'keyboard': KeyboardBuilder.confirmation_keyboard(),
                'success': True,
                'receipt_link': receipt_link
            }
            
        except Exception as e:
            self.error_handler.log_error_details(e, "photo_upload_processing", user_id)
            return {
                'message': '❌ Error processing photo, please try again',
                'keyboard': KeyboardBuilder.cancel_keyboard(),
                'success': False
            }
        finally:
            # Force garbage collection after photo processing
            import gc
            gc.collect()
    
    def _process_confirmation(self, user_id: int, callback_data: str, claim_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process confirmation step."""
        try:
            if callback_data == 'confirm_yes':
                # Submit the claim
                success = self.submit_claim(user_id, claim_data)
                
                if success:
                    return {
                        'message': '✅ Claim submitted successfully!\n\nYour expense claim status: Pending Review',
                        'keyboard': KeyboardBuilder.claim_complete_keyboard(),
                        'success': True
                    }
                else:
                    return {
                        'message': '❌ Error submitting claim, please try again later.',
                        'keyboard': KeyboardBuilder.confirmation_keyboard(),
                        'success': False
                    }
                    
            elif callback_data == 'confirm_no':
                # Cancel the claim
                return {
                    'message': '❌ Claim cancelled.',
                    'keyboard': KeyboardBuilder.claim_complete_keyboard(),
                    'success': True
                }
            else:
                return {
                    'message': 'Please select confirm or cancel:',
                    'keyboard': KeyboardBuilder.confirmation_keyboard(),
                    'success': False
                }
                
        except Exception as e:
            logger.error(f"Failed to process confirmation for user {user_id}: {e}")
            raise
    
    def upload_receipt(self, user_id: int, photo_data: bytes, category: str) -> str:
        """
        Upload receipt photo to category-specific Google Drive folder and get shareable link.
        
        Args:
            user_id: Telegram user ID
            photo_data: Photo data as bytes
            category: Expense category (may include "Other : description" format)
            
        Returns:
            str: Shareable link to the uploaded photo
        """
        try:
            timestamp = datetime.now()
            
            # Extract base category for folder lookup
            # If category is "Other : description", extract "Other"
            if category.startswith('Other : '):
                base_category = 'Other'
                logger.info(f"Detected Other category with description: {category}, using base category: {base_category}")
            else:
                base_category = category
            
            # Generate filename with timestamp and full category for better organization
            # Use safe filename by replacing spaces and colons
            safe_category = category.replace(' : ', '_').replace(' ', '_')
            filename = f"receipt_{user_id}_{safe_category}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            
            # Get category-specific folder ID from config using base category
            category_folder_id = self.config.get_category_folder_id(base_category)
            
            logger.info(f"Uploading receipt for user {user_id}, category {category} (base: {base_category}) to folder {category_folder_id}")
            
            # Upload to category-specific folder (lazy loading)
            drive_client = self.lazy_client_manager.get_drive_client()
            file_id = drive_client._upload_photo_sync(
                photo_data, filename, category_folder_id
            )
            
            # Get shareable link for the uploaded file
            shareable_link = drive_client._get_shareable_link_sync(file_id)
            
            logger.info(f"Successfully uploaded receipt for user {user_id}, category {category}, link: {shareable_link}")
            return shareable_link
            
        except Exception as e:
            logger.error(f"Failed to upload receipt for user {user_id}: {e}")
            raise
    
    def _format_datetime_local(self, dt: datetime) -> str:
        """
        Format datetime to Malaysia timezone format: 5/8/2025 2:20pm
        
        Args:
            dt: datetime object (UTC)
            
        Returns:
            str: Formatted datetime string in Malaysia timezone
        """
        # Convert UTC to Malaysia timezone (GMT+8)
        malaysia_tz = timezone(timedelta(hours=8))
        
        # If datetime is naive (no timezone), assume it's UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        # Convert to Malaysia time
        malaysia_dt = dt.astimezone(malaysia_tz)
        
        # Format: M/D/YYYY H:MMam/pm (cross-platform compatible)
        month = malaysia_dt.month
        day = malaysia_dt.day
        year = malaysia_dt.year
        hour = malaysia_dt.hour
        minute = malaysia_dt.minute
        
        # Convert to 12-hour format
        if hour == 0:
            hour_12 = 12
            ampm = 'am'
        elif hour < 12:
            hour_12 = hour
            ampm = 'am'
        elif hour == 12:
            hour_12 = 12
            ampm = 'pm'
        else:
            hour_12 = hour - 12
            ampm = 'pm'
        
        return f"{month}/{day}/{year} {hour_12}:{minute:02d}{ampm}"
    
    def _get_user_name(self, user_id: int) -> str:
        """
        Get user's registered name by user_id
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            str: User's registered name or user_id as fallback
        """
        try:
            # Get user data from sheets_client (lazy loading)
            sheets_client = self.lazy_client_manager.get_sheets_client()
            user_data = sheets_client._get_user_sync(user_id)
            if user_data and 'name' in user_data:
                return user_data['name']
            else:
                logger.warning(f"User name not found for user_id {user_id}, using user_id as fallback")
                return str(user_id)
        except Exception as e:
            logger.error(f"Error getting user name for user_id {user_id}: {e}")
            return str(user_id)
    
    def _get_user_role(self, user_id: int) -> str:
        """
        Get user's role by user_id
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            str: User's role (Staff/Manager/Ambassador) or 'Staff' as fallback
        """
        try:
            # Get user data from sheets_client (lazy loading)
            sheets_client = self.lazy_client_manager.get_sheets_client()
            user_data = sheets_client._get_user_sync(user_id)
            if user_data and 'role' in user_data:
                return user_data['role']
            else:
                logger.warning(f"User role not found for user_id {user_id}, using 'Staff' as fallback")
                return 'Staff'
        except Exception as e:
            logger.error(f"Error getting user role for user_id {user_id}: {e}")
            return 'Staff'

    def submit_claim(self, user_id: int, claim_data: Dict[str, Any]) -> bool:
        """
        Submit claim to role-specific Google Sheets with formatted data.
        
        Args:
            user_id: Telegram user ID
            claim_data: Dictionary containing claim information
            
        Returns:
            bool: True if submission was successful
        """
        try:
            # Get user information
            user_name = self._get_user_name(user_id)
            user_role = self._get_user_role(user_id)
            
            # Handle category - for Other with description, store as is
            category_value = claim_data['category']
            if category_value.startswith('Other : '):
                # For Other category with description, use the full string
                category_for_storage = category_value
                category_enum = ClaimCategory.OTHER  # For validation purposes
            else:
                # For regular categories, use the enum
                category_enum = ClaimCategory(category_value)
                category_for_storage = category_enum.value
            
            # Create claim object (using enum for validation)
            claim = Claim(
                date=datetime.now(),
                category=category_enum,
                amount=float(claim_data['amount']),
                receipt_link=claim_data['receipt_link'],
                submitted_by=user_id,
                status=ClaimStatus.PENDING
            )
            
            # Format data for Google Sheets
            formatted_date = self._format_datetime_local(claim.date)
            
            values = [
                formatted_date,                    # Date in local format
                category_for_storage,              # Category (with description for Other)
                claim.amount,                      # Amount
                claim.receipt_link,                # Receipt Link
                user_name,                         # Submitted By (user name)
                claim.status.value                 # Status
            ]
            
            # Submit to role-specific Claims sheet (lazy loading)
            worksheet_name = f"{user_role} Claims"  # 'Staff Claims', 'Manager Claims', or 'Ambassador Claims'
            sheets_client = self.lazy_client_manager.get_sheets_client()
            success = sheets_client._append_data_sync(worksheet_name, [values], 'A:F')
            
            if success:
                logger.info(f"Successfully submitted claim for user {user_id} ({user_name}) to {worksheet_name} sheet")
            else:
                logger.error(f"Failed to submit claim for user {user_id} ({user_name}) to {worksheet_name} sheet")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to submit claim for user {user_id}: {e}")
            return False
    
    def validate_amount(self, amount: str) -> float:
        """
        Validate and parse amount input.
        
        Args:
            amount: Amount string to validate
            
        Returns:
            float: Parsed amount
            
        Raises:
            ValueError: If amount is invalid
        """
        is_valid, parsed_amount, error_message = validate_amount(amount)
        
        if not is_valid:
            raise ValueError(error_message)
        
        return parsed_amount
    
    def _get_category_emoji(self, category: ClaimCategory) -> str:
        """Get emoji for category display."""
        emoji_map = {
            ClaimCategory.FOOD: '🍔',
            ClaimCategory.TRANSPORTATION: '🚗',
            ClaimCategory.FLIGHT: '✈️',
            ClaimCategory.EVENT: '🎉',
            ClaimCategory.AI: '🤖',
            ClaimCategory.RECEPTION: '🎪',
            ClaimCategory.OTHER: '📦'
        }
        return emoji_map.get(category, '📦')
    
    def _generate_confirmation_message(self, claim_data: Dict[str, Any]) -> str:
        """Generate confirmation message for claim review."""
        try:
            category = claim_data.get('category', 'Unknown')
            amount = claim_data.get('amount', 0)
            
            # Handle Other category with description
            if category.startswith('Other : '):
                category_display = f"{category} 📦"
            else:
                # Get category enum for emoji
                try:
                    category_enum = ClaimCategory(category)
                    emoji = self._get_category_emoji(category_enum)
                    category_display = f"{category} {emoji}"
                except ValueError:
                    category_display = category
            
            formatted_amount = format_amount(float(amount))
            
            message = (
                "📋 Please confirm your claim information:\n\n"
                f"Category: {category_display}\n"
                f"Amount: {formatted_amount}\n"
                f"Receipt: Uploaded ✅\n\n"
                "Confirm to submit claim?"
            )
            
            return message
            
        except Exception as e:
            logger.error(f"Failed to generate confirmation message: {e}")
            return "Please confirm your claim information and choose whether to submit."
    
    def cancel_claim_process(self, user_id: int) -> Dict[str, Any]:
        """
        Cancel the current claim process for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dict containing response message and keyboard
        """
        try:
            logger.info(f"Cancelled claim process for user {user_id}")
            
            return {
                'message': '❌ Claim process cancelled.',
                'keyboard': KeyboardBuilder.claim_complete_keyboard(),
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Failed to cancel claim process for user {user_id}: {e}")
            return {
                'message': 'Error cancelling claim.',
                'keyboard': None,
                'success': False
            }
    
    def get_user_claims(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent claims for a specific user.
        
        Args:
            user_id: Telegram user ID
            limit: Maximum number of claims to return
            
        Returns:
            List of user's claims
        """
        try:
            # Get user's role to determine which worksheet to search
            user_role = self._get_user_role(user_id)
            user_name = self._get_user_name(user_id)
            
            # Get all claims from the role-specific Claims worksheet
            sheets_client = self.lazy_client_manager.get_sheets_client()
            worksheet = f"{user_role} Claims"
            all_claims_data = sheets_client._get_all_claims_sync(worksheet)
            
            # Convert raw data to structured format and filter by user name
            user_claims = []
            for row in all_claims_data:
                if len(row) >= 6 and row[4] == user_name:  # row[4] is submitted_by (user name)
                    claim = {
                        'date': row[0],
                        'category': row[1],
                        'amount': float(row[2]) if row[2] else 0.0,
                        'receipt_link': row[3],
                        'submitted_by': row[4],
                        'status': row[5]
                    }
                    user_claims.append(claim)
            
            # Sort by date (most recent first) and limit
            user_claims.sort(key=lambda x: x.get('date', ''), reverse=True)
            
            logger.info(f"Found {len(user_claims)} claims for user {user_id} ({user_name}) in {worksheet}")
            return user_claims[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get claims for user {user_id}: {e}")
            return []
    
    def get_claim_status_message(self, claims: List[Dict[str, Any]]) -> str:
        """
        Generate status message for user's claims.
        
        Args:
            claims: List of user's claims
            
        Returns:
            str: Formatted status message
        """
        if not claims:
            return "You haven't submitted any claims yet."
        
        message = f"📊 Your claim status (latest {len(claims)} items):\n\n"
        
        for i, claim in enumerate(claims, 1):
            try:
                date = claim.get('date', 'Unknown')
                category = claim.get('category', 'Unknown')
                amount = format_amount(float(claim.get('amount', 0)))
                status = claim.get('status', 'Unknown')
                
                # Format date for display
                try:
                    if date != 'Unknown':
                        date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                        date_display = date_obj.strftime('%Y-%m-%d')
                    else:
                        date_display = date
                except:
                    date_display = date
                
                # Status emoji
                status_emoji = {
                    'Pending': '⏳',
                    'Approved': '✅',
                    'Rejected': '❌'
                }.get(status, '❓')
                
                message += f"{i}. {date_display} | {category} | {amount} | {status_emoji} {status}\n"
                
            except Exception as e:
                logger.error(f"Error formatting claim {i}: {e}")
                message += f"{i}. Claim information format error\n"
        
        return message

    def get_user_claims_summary(self, role: str, user_name: str) -> Dict[str, Any]:
        """
        Get summary of user's claims: count, total amount, unique categories.
        
        Args:
            role: User role
            user_name: User's registered name
            
        Returns:
            Dict with count, total_amount, categories
        """
        import gc
        summary = {'count': 0, 'total_amount': 0.0, 'categories': set()}
        try:
            sheets_client = self.lazy_client_manager.get_sheets_client()
            worksheet = f"{role.capitalize()} Claims"
            values = sheets_client._get_all_claims_sync(worksheet)  # Assume similar to _get_all_users_sync
            for row in values:
                if len(row) > 4 and row[4] == user_name:
                    summary['count'] += 1
                    summary['total_amount'] += float(row[2]) if row[2] else 0
                    summary['categories'].add(row[1])
            return summary
        except Exception as e:
            logger.error(f"Error getting claims summary for {user_name} in {role}: {e}")
            return summary
        finally:
            gc.collect()

    def delete_user_claims(self, role: str, user_name: str) -> bool:
        """
        Delete user's claims data and associated photos.
        
        Args:
            role: User role
            user_name: User's registered name
            
        Returns:
            True if deletion successful
        """
        import gc
        try:
            sheets_client = self.lazy_client_manager.get_sheets_client()
            drive_client = self.lazy_client_manager.get_drive_client()
            worksheet = f"{role.capitalize()} Claims"
            values = sheets_client._get_all_claims_sync(worksheet)  # This already skips header
            rows_to_delete = []
            files_to_delete = []
            
            logger.info(f"Found {len(values)} data rows (excluding header) in {worksheet}")
            
            for i, row in enumerate(values):
                if len(row) > 4 and row[4] == user_name:
                    # Since _get_all_claims_sync already skips header, we need i + 2:
                    # i is 0-based index in data rows, +1 for header, +1 for 1-based indexing
                    actual_row_index = i + 2
                    rows_to_delete.append(actual_row_index)
                    logger.info(f"Found user claim at data row {i}, actual sheet row {actual_row_index}")
                    
                    if len(row) > 3 and row[3]:
                        file_id = self._extract_file_id(row[3])
                        if file_id:
                            files_to_delete.append(file_id)
            
            logger.info(f"Will delete {len(rows_to_delete)} rows and {len(files_to_delete)} files for user {user_name}")
            
            # Delete files first
            for file_id in files_to_delete:
                try:
                    drive_client._delete_file_sync(file_id)
                    logger.info(f"Deleted file {file_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete file {file_id}: {e}")
            
            # Delete rows in reverse order to maintain correct indices
            for row_idx in sorted(rows_to_delete, reverse=True):
                try:
                    sheets_client._delete_row_sync(worksheet, row_idx)
                    logger.info(f"Deleted row {row_idx} from {worksheet}")
                except Exception as e:
                    logger.error(f"Failed to delete row {row_idx}: {e}")
                    return False
            
            logger.info(f"Successfully deleted all claims for user {user_name} in {role}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting claims for {user_name} in {role}: {e}")
            return False
        finally:
            gc.collect()

    def _extract_file_id(self, link: str) -> str:
        """Extract file ID from Google Drive link."""
        import re
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', link)
        return match.group(1) if match else None
