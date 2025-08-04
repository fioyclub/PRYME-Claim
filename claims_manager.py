"""
Claims Manager for Telegram Claim Bot

This module provides the ClaimsManager class that handles the expense claim submission process,
including category selection, amount input, photo upload, and integration with Google services
with comprehensive error handling.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Any, Tuple, List
from io import BytesIO

from models import Claim, ClaimCategory, ClaimStatus, UserStateType
from state_manager import StateManager
from sheets_client import SheetsClient
from drive_client import DriveClient
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
    
    def __init__(self, sheets_client: SheetsClient, drive_client: DriveClient, 
                 state_manager: StateManager):
        """
        Initialize the ClaimsManager.
        
        Args:
            sheets_client: Google Sheets client for data storage
            drive_client: Google Drive client for photo uploads
            state_manager: State manager for tracking user conversations
        """
        self.sheets_client = sheets_client
        self.drive_client = drive_client
        self.state_manager = state_manager
        self.error_handler = global_error_handler
        
        # Category mapping for callback data to enum
        self.category_mapping = {
            'category_food': ClaimCategory.FOOD,
            'category_transportation': ClaimCategory.TRANSPORTATION,
            'category_flight': ClaimCategory.FLIGHT,
            'category_event': ClaimCategory.EVENT,
            'category_ai': ClaimCategory.AI,
            'category_other': ClaimCategory.OTHER
        }
        
        logger.info("ClaimsManager initialized")
    
    def start_claim_process(self, user_id: int) -> Dict[str, Any]:
        """
        Start the claim submission process for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dict containing response message and keyboard
        """
        try:
            # Set user state to category selection
            self.state_manager.set_user_state(
                user_id, 
                UserStateType.CLAIMING_CATEGORY,
                {'step': 'category', 'claim_data': {}}
            )
            
            logger.info(f"Started claim process for user {user_id}")
            
            return {
                'message': '请选择报销类别：',
                'keyboard': KeyboardBuilder.claim_categories_keyboard(),
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Failed to start claim process for user {user_id}: {e}")
            return {
                'message': '启动申请流程时出现错误，请稍后重试。',
                'keyboard': None,
                'success': False
            }
    
    def process_claim_step(self, user_id: int, step: str, data: Any) -> Dict[str, Any]:
        """
        Process a step in the claim submission flow.
        
        Args:
            user_id: Telegram user ID
            step: Current step ('category', 'amount', 'photo', 'confirm')
            data: Step-specific data (callback_data, text, photo_data)
            
        Returns:
            Dict containing response message, keyboard, and success status
        """
        try:
            current_state, temp_data = self.state_manager.get_user_state(user_id)
            
            if step == 'category':
                return self._process_category_selection(user_id, data, temp_data)
            elif step == 'amount':
                return self._process_amount_input(user_id, data, temp_data)
            elif step == 'photo':
                return self._process_photo_upload(user_id, data, temp_data)
            elif step == 'confirm':
                return self._process_confirmation(user_id, data, temp_data)
            else:
                logger.warning(f"Unknown claim step '{step}' for user {user_id}")
                return {
                    'message': '未知的操作步骤，请重新开始申请。',
                    'keyboard': KeyboardBuilder.cancel_keyboard(),
                    'success': False
                }
                
        except Exception as e:
            logger.error(f"Failed to process claim step {step} for user {user_id}: {e}")
            return {
                'message': '处理申请时出现错误，请稍后重试。',
                'keyboard': KeyboardBuilder.cancel_keyboard(),
                'success': False
            }
    
    def _process_category_selection(self, user_id: int, callback_data: str, 
                                        temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process category selection step."""
        try:
            # Validate category selection
            if callback_data not in self.category_mapping:
                return {
                    'message': '无效的类别选择，请重新选择：',
                    'keyboard': KeyboardBuilder.claim_categories_keyboard(),
                    'success': False
                }
            
            category = self.category_mapping[callback_data]
            
            # Update claim data and move to amount input
            claim_data = temp_data.get('claim_data', {})
            claim_data['category'] = category.value
            
            self.state_manager.set_user_state(
                user_id,
                UserStateType.CLAIMING_AMOUNT,
                {'step': 'amount', 'claim_data': claim_data}
            )
            
            category_display = f"{category.value} {self._get_category_emoji(category)}"
            
            return {
                'message': f'已选择类别：{category_display}\n\n请输入金额（RM）：',
                'keyboard': KeyboardBuilder.cancel_keyboard(),
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Failed to process category selection for user {user_id}: {e}")
            raise
    
    def _process_amount_input(self, user_id: int, amount_text: str, 
                                  temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process amount input step with enhanced error handling and retry flow."""
        try:
            # Validate amount using new validation system
            validation_result = validate_amount(amount_text)
            
            if not validation_result.is_valid:
                logger.info(f"Invalid amount input from user {user_id}: {validation_result.error_message}")
                
                # Use validation helper for comprehensive error handling
                error_response = create_validation_error_response(
                    validation_result, 'amount', user_id,
                    "申请过程中"
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
                "请上传收据照片："
            )
            
            # Update claim data and move to photo upload
            claim_data = temp_data.get('claim_data', {})
            claim_data['amount'] = validation_result.value
            
            self.state_manager.set_user_state(
                user_id,
                UserStateType.CLAIMING_PHOTO,
                {'step': 'photo', 'claim_data': claim_data}
            )
            
            return {
                'message': success_response['message'],
                'keyboard': KeyboardBuilder.cancel_keyboard(),
                'success': True
            }
            
        except Exception as e:
            self.error_handler.log_error_details(e, "amount_input_processing", user_id)
            return {
                'message': '❌ 处理金额时出现错误，请重试',
                'keyboard': KeyboardBuilder.cancel_keyboard(),
                'success': False
            }
    
    def _process_photo_upload(self, user_id: int, photo_data: bytes, 
                                  temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process photo upload step with enhanced error handling and retry flow."""
        try:
            # Validate photo using new validation system
            validation_result = validate_photo_file(photo_data)
            
            if not validation_result.is_valid:
                logger.info(f"Invalid photo upload from user {user_id}: {validation_result.error_message}")
                
                # Use validation helper for comprehensive error handling
                error_response = create_validation_error_response(
                    validation_result, 'photo', user_id,
                    "申请过程中"
                )
                
                return {
                    'message': error_response['message'],
                    'keyboard': error_response.get('keyboard', KeyboardBuilder.cancel_keyboard()),
                    'success': False,
                    'attempt_count': error_response['attempt_count']
                }
            
            claim_data = temp_data.get('claim_data', {})
            
            # Upload photo to Google Drive (simplified for v13.15)
            try:
                receipt_link = self.upload_receipt(user_id, photo_data, claim_data.get('category', 'Other'))
                success = True
                error_msg = None
            except Exception as e:
                success = False
                receipt_link = None
                error_msg = str(e)
            
            if not success:
                return {
                    'message': error_msg or '❌ 上传收据照片失败，请稍后重试。',
                    'keyboard': KeyboardBuilder.cancel_keyboard(),
                    'success': False
                }
            
            # Success - use validation helper for success response
            success_response = create_validation_success_response(
                'photo', '收据照片', user_id
            )
            
            claim_data['receipt_link'] = receipt_link
            
            # Move to confirmation step
            self.state_manager.set_user_state(
                user_id,
                UserStateType.CLAIMING_CONFIRM,
                {'step': 'confirm', 'claim_data': claim_data}
            )
            
            # Generate confirmation message
            confirmation_message = self._generate_confirmation_message(claim_data)
            
            return {
                'message': f'{success_response["message"]}\n\n{confirmation_message}',
                'keyboard': KeyboardBuilder.confirmation_keyboard(),
                'success': True
            }
            
        except Exception as e:
            self.error_handler.log_error_details(e, "photo_upload_processing", user_id)
            return {
                'message': '❌ 处理照片时出现错误，请重试',
                'keyboard': KeyboardBuilder.cancel_keyboard(),
                'success': False
            }
    
    def _process_confirmation(self, user_id: int, callback_data: str, 
                                  temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process confirmation step."""
        try:
            if callback_data == 'confirm_yes':
                # Submit the claim
                claim_data = temp_data.get('claim_data', {})
                success = self.submit_claim(user_id, claim_data)
                
                if success:
                    # Clear user state
                    self.state_manager.clear_user_state(user_id)
                    
                    return {
                        'message': '✅ 申请已成功提交！\n\n您的报销申请状态为：待审核',
                        'keyboard': KeyboardBuilder.claim_complete_keyboard(),
                        'success': True
                    }
                else:
                    return {
                        'message': '❌ 提交申请时出现错误，请稍后重试。',
                        'keyboard': KeyboardBuilder.confirmation_keyboard(),
                        'success': False
                    }
                    
            elif callback_data == 'confirm_no':
                # Cancel the claim
                self.state_manager.clear_user_state(user_id)
                
                return {
                    'message': '❌ 申请已取消。',
                    'keyboard': KeyboardBuilder.claim_complete_keyboard(),
                    'success': True
                }
            else:
                return {
                    'message': '请选择确认或取消：',
                    'keyboard': KeyboardBuilder.confirmation_keyboard(),
                    'success': False
                }
                
        except Exception as e:
            logger.error(f"Failed to process confirmation for user {user_id}: {e}")
            raise
    
    def upload_receipt(self, user_id: int, photo_data: bytes, category: str) -> str:
        """
        Upload receipt photo to Google Drive shared folder and get shareable link.
        
        Args:
            user_id: Telegram user ID
            photo_data: Photo data as bytes
            category: Expense category
            
        Returns:
            str: Shareable link to the uploaded photo
        """
        try:
            timestamp = datetime.now()
            
            # Generate filename with timestamp and category for better organization
            filename = f"receipt_{user_id}_{category}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            
            # Upload to shared folder (not service account's drive)
            file_id = self.drive_client._upload_photo_sync(
                photo_data, filename, self.drive_client.root_folder_id
            )
            
            # Get shareable link for the uploaded file
            shareable_link = self.drive_client._get_shareable_link_sync(file_id)
            
            logger.info(f"Successfully uploaded receipt for user {user_id}, category {category}, link: {shareable_link}")
            return shareable_link
            
        except Exception as e:
            logger.error(f"Failed to upload receipt for user {user_id}: {e}")
            raise
    
    def submit_claim(self, user_id: int, claim_data: Dict[str, Any]) -> bool:
        """
        Submit claim to Google Sheets.
        
        Args:
            user_id: Telegram user ID
            claim_data: Dictionary containing claim information
            
        Returns:
            bool: True if submission was successful
        """
        try:
            # Create claim object
            claim = Claim(
                date=datetime.now(),
                category=ClaimCategory(claim_data['category']),
                amount=float(claim_data['amount']),
                receipt_link=claim_data['receipt_link'],
                submitted_by=user_id,
                status=ClaimStatus.PENDING
            )
            
            # Submit to Google Sheets (using sync method)
            claim_dict = claim.to_dict()
            values = [
                claim_dict['user_id'],
                claim_dict['category'],
                claim_dict['amount'],
                claim_dict['receipt_link'],
                claim_dict['submit_date'],
                claim_dict['status']
            ]
            success = self.sheets_client._append_data_sync('Claims', [values], 'A:F')
            
            if success:
                logger.info(f"Successfully submitted claim for user {user_id}")
            else:
                logger.error(f"Failed to submit claim for user {user_id}")
            
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
            ClaimCategory.OTHER: '📦'
        }
        return emoji_map.get(category, '📦')
    
    def _generate_confirmation_message(self, claim_data: Dict[str, Any]) -> str:
        """Generate confirmation message for claim review."""
        try:
            category = claim_data.get('category', 'Unknown')
            amount = claim_data.get('amount', 0)
            
            # Get category enum for emoji
            try:
                category_enum = ClaimCategory(category)
                emoji = self._get_category_emoji(category_enum)
                category_display = f"{category} {emoji}"
            except ValueError:
                category_display = category
            
            formatted_amount = format_amount(float(amount))
            
            message = (
                "📋 请确认您的申请信息：\n\n"
                f"类别：{category_display}\n"
                f"金额：{formatted_amount}\n"
                f"收据：已上传 ✅\n\n"
                "确认提交申请吗？"
            )
            
            return message
            
        except Exception as e:
            logger.error(f"Failed to generate confirmation message: {e}")
            return "请确认您的申请信息并选择是否提交。"
    
    def cancel_claim_process(self, user_id: int) -> Dict[str, Any]:
        """
        Cancel the current claim process for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dict containing response message and keyboard
        """
        try:
            # Clear user state
            self.state_manager.clear_user_state(user_id)
            
            logger.info(f"Cancelled claim process for user {user_id}")
            
            return {
                'message': '❌ 申请流程已取消。',
                'keyboard': KeyboardBuilder.claim_complete_keyboard(),
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Failed to cancel claim process for user {user_id}: {e}")
            return {
                'message': '取消申请时出现错误。',
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
            # Get all claims and filter by user
            # For now, return empty list (can be enhanced later with sync method)
            all_claims = []
            
            user_claims = [
                claim for claim in all_claims 
                if claim.get('submitted_by') == user_id
            ]
            
            # Sort by date (most recent first) and limit
            user_claims.sort(key=lambda x: x.get('date', ''), reverse=True)
            
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
            return "您还没有提交任何申请。"
        
        message = f"📊 您的申请状态（最近{len(claims)}条）：\n\n"
        
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
                message += f"{i}. 申请信息格式错误\n"
        
        return message
