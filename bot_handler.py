"""
Telegram Bot Handler for python-telegram-bot v13.15
Handles Telegram webhook/polling and message routing with comprehensive error handling
"""

import logging
from typing import Optional
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters
from telegram import ParseMode

from user_manager import UserManager
from claims_manager import ClaimsManager
from dayoff_manager import DayOffManager
from state_manager import StateManager
from models import UserStateType
from keyboards import KeyboardBuilder
from error_handler import global_error_handler, with_error_handling

logger = logging.getLogger(__name__)


class TelegramBot:
    """Main Telegram Bot handler class for v13.15"""
    
    def __init__(self, token: str, user_manager: UserManager, claims_manager: ClaimsManager, 
                 dayoff_manager: DayOffManager, state_manager: StateManager):
        """
        Initialize bot with token and required managers
        
        Args:
            token: Telegram bot token
            user_manager: User management instance
            claims_manager: Claims management instance
            dayoff_manager: Day-off management instance
            state_manager: State management instance
        """
        self.token = token
        self.user_manager = user_manager
        self.claims_manager = claims_manager
        self.dayoff_manager = dayoff_manager
        self.state_manager = state_manager
        self.error_handler = global_error_handler
        
        # Create updater and dispatcher (v13.15 style)
        self.updater = Updater(token=token, use_context=True)
        self.dispatcher = self.updater.dispatcher
        
        # Setup handlers
        self._setup_handlers()
        
        logger.info("TelegramBot initialized with v13.15 Updater")
    
    def _setup_handlers(self):
        """Setup all message and callback handlers"""
        # Command handlers
        self.dispatcher.add_handler(CommandHandler("start", self.handle_start_command))
        self.dispatcher.add_handler(CommandHandler("register", self.handle_register_command))
        self.dispatcher.add_handler(CommandHandler("claim", self.handle_claim_command))
        self.dispatcher.add_handler(CommandHandler("dayoff", self.handle_dayoff_command))
        self.dispatcher.add_handler(CommandHandler("help", self.handle_help_command))
        
        # Callback query handler for inline keyboards
        self.dispatcher.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Message handlers (v13.15 uses Filters with capital F)
        self.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, self.handle_text_input))
        self.dispatcher.add_handler(MessageHandler(Filters.photo, self.handle_photo_upload))
        
        # Error handler
        self.dispatcher.add_error_handler(self.handle_error)
        
        logger.info("Bot handlers setup complete")
    
    def start_webhook(self, webhook_url: str, port: int = 8000):
        """
        Set webhook for production deployment (v13.15 style)
        Note: Flask server is now handled separately by Gunicorn
        
        Args:
            webhook_url: URL for webhook
            port: Port to listen on (unused, kept for compatibility)
        """
        try:
            logger.info(f"Setting webhook to {webhook_url}")
            
            # Set webhook
            self.updater.bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook set successfully to: {webhook_url}")
            logger.info("Flask server will be handled by Gunicorn")
            
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
            raise
    
    def start_polling(self):
        """Start polling for development (v13.15 style)"""
        try:
            logger.info("Starting polling mode")
            
            # Start polling (v13.15 style)
            self.updater.start_polling()
            
            # Keep running
            self.updater.idle()
            
        except Exception as e:
            logger.error(f"Failed to start polling: {e}")
            raise
    
    def handle_start_command(self, update: Update, context):
        """Handle /start command with optimized HTML format and dynamic user name"""
        try:
            user_id = update.effective_user.id
            telegram_name = update.effective_user.first_name or "User"
            
            logger.info(f"User {user_id} ({telegram_name}) started bot")
            
            # Check if user is registered (v13.15 - synchronous call)
            is_registered = self.user_manager.is_user_registered(user_id)
            
            # Get user name (registered name if available, otherwise Telegram name)
            if is_registered:
                user_data = self.user_manager.get_user_data(user_id)
                display_name = user_data.name if user_data else telegram_name
                keyboard = KeyboardBuilder.start_claim_keyboard()
            else:
                display_name = telegram_name
                keyboard = KeyboardBuilder.register_now_keyboard()
            
            # Optimized welcome message with HTML format and emojis
            message = (
                f"<b>🎉 Welcome to PRYME PLUS Bot!</b>\n\n"
                f"Hey there, <b>{display_name}</b>! 👋 Great to see you here!\n\n"
                f"I'm your <b>PRYMEPLUS Claim Assistant</b>, ready to make your claim process easier! 💼✨\n\n"
                f"<b>📋 Available Commands:</b>\n"
                f"• /register - Register your information 📝\n"
                f"• /claim - Submit your expense claim 💰\n"
                f"• /help - View help information ℹ️\n"
                f"• /dayoff - Request Day-off 🗓️\n\n"
                f"<b>🚀 Let's get started!</b>"
            )
            
            update.message.reply_text(
                message,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"Error handling start command: {e}")
            self._send_error_message(update, "Failed to process start command, please try again later.")
    
    def handle_help_command(self, update: Update, context):
        """Handle /help command"""
        try:
            help_message = (
                "📋 <b>PRYMEPLUS System Help</b>\n\n"
                "<b>Available Commands:</b>\n"
                "• /start - Start using the system\n"
                "• /register - Register user information\n"
                "• /claim - Submit expense claim\n"
                "• /dayoff - Request Day-off 🗓️\n"
                "• /help - Show this help information\n\n"
                "<b>Usage Flow:</b>\n"
                "1. Use /register to register your information\n"
                "2. Use /claim to submit expense claim\n"
                "3. Use /dayoff to request day-off (Staff & Manager only)\n"
                "4. Select category, enter amount, upload receipt\n"
                "5. Confirm and submit claim\n\n"
                "<b>Supported Expense Categories:</b>\n"
                "• 🍔 Food - Food expenses\n"
                "• 🚗 Transportation - Transportation costs\n"
                "• ✈️ Flight - Flight expenses\n"
                "• 🎉 Event - Event costs\n"
                "• 🤖 AI - AI tool expenses\n"
                "• 🎪 Reception - Reception expenses\n"
                "• 📦 Other - Other expenses\n\n"
                "<b>Day-off Request:</b>\n"
                "• Available for Staff and Manager roles only\n"
                "• Use DD/MM/YYYY date format\n"
                "• Provide clear reason for request\n\n"
                "If you have any questions, please contact the administrator."
            )
            
            update.message.reply_text(
                help_message,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"Error handling help command: {e}")
            self._send_error_message(update, "Failed to get help information, please try again later.")
    
    def handle_register_command(self, update: Update, context):
        """Handle /register command"""
        try:
            user_id = update.effective_user.id
            
            logger.info(f"User {user_id} initiated registration")
            
            # Start registration process
            result = self.user_manager.start_registration(user_id)
            
            if result['success']:
                keyboard = None
                if result.get('next_step') == UserStateType.REGISTERING_ROLE.value:
                    keyboard = KeyboardBuilder.role_selection_keyboard()
                
                update.message.reply_text(
                    result['message'],
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )
            else:
                update.message.reply_text(result['message'], parse_mode=ParseMode.HTML)
                
        except Exception as e:
            logger.error(f"Error handling register command: {e}")
            self._send_error_message(update, "Failed to process register command, please try again later.")
    
    def handle_claim_command(self, update: Update, context):
        """Handle /claim command"""
        try:
            user_id = update.effective_user.id
            
            logger.info(f"User {user_id} initiated claim process")
            
            # Check if user is registered
            has_permission, error_msg = self.user_manager.check_user_permission(user_id)
            
            if not has_permission:
                update.message.reply_text(error_msg)
                return
            
            # Start claim process
            result = self.claims_manager.start_claim_process(user_id)
            
            if result['success']:
                update.message.reply_text(
                    result['message'],
                    reply_markup=result['keyboard']
                )
            else:
                update.message.reply_text(result['message'])
                
        except Exception as e:
            logger.error(f"Error handling claim command: {e}")
            self._send_error_message(update, "Failed to process claim command, please try again later.")
    
    def handle_dayoff_command(self, update: Update, context):
        """Handle /dayoff command"""
        try:
            user_id = update.effective_user.id
            
            logger.info(f"User {user_id} initiated day-off request")
            
            # Start day-off request process
            result = self.dayoff_manager.start_dayoff_request(user_id)
            
            if result['success']:
                update.message.reply_text(
                    result['message'],
                    reply_markup=result.get('keyboard'),
                    parse_mode=ParseMode.HTML
                )
            else:
                update.message.reply_text(
                    result['message'],
                    reply_markup=result.get('keyboard'),
                    parse_mode=ParseMode.HTML
                )
                
        except Exception as e:
            logger.error(f"Error handling dayoff command: {e}")
            self._send_error_message(update, "Failed to process day-off command, please try again later.")
    
    def handle_callback_query(self, update: Update, context):
        """Handle inline keyboard callbacks"""
        try:
            query = update.callback_query
            user_id = query.from_user.id
            callback_data = query.data
            
            logger.info(f"User {user_id} pressed callback: {callback_data}")
            
            # Answer callback query to remove loading state
            query.answer()
            
            # Get current user state
            current_state, temp_data = self.state_manager.get_user_state(user_id)
            
            # Handle different callback types
            if callback_data.startswith('role_'):
                self._handle_role_callback(query, callback_data, current_state, temp_data)
            
            elif callback_data.startswith('category_'):
                self._handle_category_callback(query, callback_data, current_state, temp_data)
            
            elif callback_data.startswith('confirm_'):
                self._handle_confirmation_callback(query, callback_data, current_state, temp_data)
            
            elif callback_data == 'start_claim':
                self._handle_start_claim_callback(query)
            
            elif callback_data == 'new_claim':
                self._handle_new_claim_callback(query)
            
            elif callback_data == 'register_now':
                self._handle_register_now_callback(query)
            
            elif callback_data.startswith('dayoff_type_'):
                self._handle_dayoff_type_callback(query, callback_data, current_state, temp_data)
            
            elif callback_data == 'cancel':
                self._handle_cancel_callback(query, current_state)
            
            else:
                logger.warning(f"Unknown callback data: {callback_data}")
                self._safe_edit_message(query, "Unknown operation, please start again.")
                
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            self._send_callback_error(update.callback_query, "Operation failed, please try again later.")
    
    def handle_text_input(self, update: Update, context):
        """Handle text input from users"""
        try:
            user_id = update.effective_user.id
            text = update.message.text.strip()
            
            logger.info(f"User {user_id} sent text: {text[:50]}...")
            
            # Get current user state
            current_state, temp_data = self.state_manager.get_user_state(user_id)
            
            # Handle based on current state
            if current_state == UserStateType.REGISTERING_NAME:
                self._handle_registration_text(update, 'name', text)
            
            elif current_state == UserStateType.REGISTERING_PHONE:
                self._handle_registration_text(update, 'phone', text)
            
            elif current_state == UserStateType.CLAIMING_AMOUNT:
                self._handle_claim_text(update, 'amount', text)
            
            elif current_state == UserStateType.CLAIMING_OTHER_DESCRIPTION:
                self._handle_claim_text(update, 'other_description', text)
            
            elif current_state == UserStateType.DAYOFF_DATE:
                self._handle_dayoff_text(update, 'date', text)
            
            elif current_state == UserStateType.DAYOFF_START_DATE:
                self._handle_dayoff_text(update, 'start_date', text)
            
            elif current_state == UserStateType.DAYOFF_END_DATE:
                self._handle_dayoff_text(update, 'end_date', text)
            
            elif current_state == UserStateType.DAYOFF_REASON:
                self._handle_dayoff_text(update, 'reason', text)
            
            elif current_state == UserStateType.IDLE:
                # User sent text while idle - provide guidance
                update.message.reply_text(
                    "Please use the following commands:\n"
                    "• /register - Register user information\n"
                    "• /claim - Submit expense claim\n"
                    "• /help - View help information"
                )
            
            else:
                logger.warning(f"Unexpected text input in state {current_state}")
                update.message.reply_text("Please follow the prompts or use /help to view help.")
                
        except Exception as e:
            logger.error(f"Error handling text input: {e}")
            self._send_error_message(update, "Text processing failed, please try again later.")
    
    def handle_photo_upload(self, update: Update, context):
        """Handle photo uploads with message deletion and processing feedback"""
        try:
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            message_id = update.message.message_id
            
            logger.info(f"User {user_id} uploaded photo")
            
            # Get current user state
            current_state, temp_data = self.state_manager.get_user_state(user_id)
            
            if current_state != UserStateType.CLAIMING_PHOTO:
                update.message.reply_text(
                    "Please use /claim command first to start the claim process, then upload receipt photo as prompted."
                )
                return
            
            # Send processing message first
            processing_message = update.message.reply_text("📸 Processing your receipt...")
            
            try:
                # Get photo data (v13.15 style)
                photo = update.message.photo[-1]  # Get highest resolution
                photo_file = photo.get_file()
                photo_data = photo_file.download_as_bytearray()
                
                # Process photo upload (save to Google Drive)
                result = self.claims_manager.process_claim_step(
                    user_id, 'photo', bytes(photo_data)
                )
                
                # Delete the original photo message from user
                try:
                    context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    logger.info(f"Successfully deleted original photo message {message_id} from user {user_id}")
                except Exception as delete_error:
                    logger.warning(f"Failed to delete photo message {message_id}: {delete_error}")
                    # Continue processing even if deletion fails
                
                # Delete the processing message
                try:
                    context.bot.delete_message(chat_id=chat_id, message_id=processing_message.message_id)
                except Exception as delete_error:
                    logger.warning(f"Failed to delete processing message: {delete_error}")
                
                # Send final result message
                if result['success']:
                    # Send success message with confirmation
                    final_message = "✅ Receipt saved successfully!\n\n" + result['message']
                    update.effective_chat.send_message(
                        text=final_message,
                        reply_markup=result['keyboard']
                    )
                else:
                    # Send error message
                    update.effective_chat.send_message(
                        text=result['message'],
                        reply_markup=result.get('keyboard')
                    )
                    
            except Exception as processing_error:
                # Delete the processing message if it exists
                try:
                    context.bot.delete_message(chat_id=chat_id, message_id=processing_message.message_id)
                except:
                    pass
                
                # Send error message
                update.effective_chat.send_message(
                    text="❌ Failed to process receipt. Please try again.",
                    reply_markup=KeyboardBuilder.cancel_keyboard()
                )
                raise processing_error
                
        except Exception as e:
            logger.error(f"Error handling photo upload: {e}")
            self._send_error_message(update, "Photo processing failed, please try again later.")
    
    def handle_error(self, update: Update, context):
        """Handle errors with comprehensive error handling"""
        error = context.error
        user_id = update.effective_user.id if update and update.effective_user else None
        
        # Log error details
        self.error_handler.log_error_details(error, "telegram_bot_handler", user_id)
        
        # Classify error and get user-friendly message
        error_type, error_severity = self.error_handler.classify_error(error)
        user_message = self.error_handler.get_user_friendly_message(error_type, error_severity, "bot_operation")
        
        # Send error message to user
        if update and update.effective_message:
            self._send_error_message(update, user_message)
        
        # Reset user state if error is severe
        if user_id and error_severity.value in ['high', 'critical']:
            try:
                self.state_manager.clear_user_state(user_id)
                logger.info(f"Cleared state for user {user_id} due to severe error")
            except Exception as state_error:
                logger.error(f"Failed to clear state for user {user_id}: {state_error}")
    
    # Helper methods for callback handling
    
    def _handle_role_callback(self, query, callback_data, current_state, temp_data):
        """Handle role selection callback"""
        if current_state != UserStateType.REGISTERING_ROLE:
            self._safe_edit_message(query, "Please use /register command first to start registration.")
            return
        
        role = callback_data.replace('role_', '')
        # Map callback role to UserRole enum value
        role_mapping = {
            'staff': 'Staff',
            'manager': 'Manager', 
            'ambassador': 'Ambassador'
        }
        mapped_role = role_mapping.get(role, role)
        result = self.user_manager.process_registration_step(
            query.from_user.id, 'role', mapped_role
        )
        
        if result['success']:
            keyboard = KeyboardBuilder.claim_complete_keyboard() if result.get('user_data') else None
            self._safe_edit_message(query, result['message'], keyboard)
        else:
            keyboard = KeyboardBuilder.role_selection_keyboard() if result.get('show_role_keyboard') else None
            self._safe_edit_message(query, result['message'], keyboard)
    
    def _handle_category_callback(self, query, callback_data, current_state, temp_data):
        """Handle category selection callback"""
        if current_state != UserStateType.CLAIMING_CATEGORY:
            self._safe_edit_message(query, "Please use /claim command first to start the claim.")
            return
        
        result = self.claims_manager.process_claim_step(
            query.from_user.id, 'category', callback_data
        )
        
        self._safe_edit_message(query, result['message'], result.get('keyboard'))
    
    def _handle_confirmation_callback(self, query, callback_data, current_state, temp_data):
        """Handle confirmation callback"""
        if current_state != UserStateType.CLAIMING_CONFIRM:
            self._safe_edit_message(query, "No pending claim to confirm.")
            return
        
        result = self.claims_manager.process_claim_step(
            query.from_user.id, 'confirm', callback_data
        )
        
        self._safe_edit_message(query, result['message'], result.get('keyboard'))
    
    def _handle_start_claim_callback(self, query):
        """Handle start claim callback"""
        user_id = query.from_user.id
        
        # Check permission
        has_permission, error_msg = self.user_manager.check_user_permission(user_id)
        
        if not has_permission:
            self._safe_edit_message(query, error_msg)
            return
        
        # Start claim process
        result = self.claims_manager.start_claim_process(user_id)
        
        self._safe_edit_message(query, result['message'], result['keyboard'])
    
    def _handle_new_claim_callback(self, query):
        """Handle new claim callback"""
        user_id = query.from_user.id
        
        # Check permission
        has_permission, error_msg = self.user_manager.check_user_permission(user_id)
        
        if not has_permission:
            self._safe_edit_message(query, error_msg)
            return
        
        # Start new claim process
        result = self.claims_manager.start_claim_process(user_id)
        
        self._safe_edit_message(query, result['message'], result['keyboard'])
    
    def _handle_register_now_callback(self, query):
        """Handle register now callback"""
        user_id = query.from_user.id
        
        logger.info(f"User {user_id} clicked register now button")
        
        # Start registration process
        result = self.user_manager.start_registration(user_id)
        
        if result['success']:
            keyboard = None
            if result.get('next_step') == UserStateType.REGISTERING_ROLE.value:
                keyboard = KeyboardBuilder.role_selection_keyboard()
            
            self._safe_edit_message(query, result['message'], keyboard)
        else:
            self._safe_edit_message(query, result['message'])
    
    def _handle_dayoff_type_callback(self, query, callback_data, current_state, temp_data):
        """Handle day-off type selection callback"""
        if current_state != UserStateType.DAYOFF_TYPE:
            self._safe_edit_message(query, "Please use /dayoff command first to start day-off request.")
            return
        
        dayoff_type = callback_data.replace('dayoff_type_', '')
        result = self.dayoff_manager.process_dayoff_type_selection(
            query.from_user.id, dayoff_type
        )
        
        self._safe_edit_message(query, result['message'], result.get('keyboard'))
    
    def _handle_cancel_callback(self, query, current_state):
        """Handle cancel callback"""
        user_id = query.from_user.id
        
        if self.state_manager.is_user_registering(user_id):
            result = self.user_manager.cancel_registration(user_id)
            self._safe_edit_message(query, result['message'])
        
        elif self.state_manager.is_user_claiming(user_id):
            result = self.claims_manager.cancel_claim_process(user_id)
            self._safe_edit_message(query, result['message'], result.get('keyboard'))
        
        elif self.state_manager.is_user_requesting_dayoff(user_id):
            result = self.dayoff_manager.cancel_dayoff_request(user_id)
            self._safe_edit_message(query, result['message'], result.get('keyboard'))
        
        else:
            self._safe_edit_message(query, "No ongoing operation to cancel.")
    
    def _handle_registration_text(self, update, field, text):
        """Handle text input during registration"""
        user_id = update.effective_user.id
        
        result = self.user_manager.process_registration_step(
            user_id, field, text
        )
        
        keyboard = None
        if result.get('show_role_keyboard'):
            keyboard = KeyboardBuilder.role_selection_keyboard()
        elif result.get('user_data'):
            keyboard = KeyboardBuilder.claim_complete_keyboard()
        
        update.message.reply_text(
            result['message'],
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    
    def _handle_claim_text(self, update, field, text):
        """Handle text input during claim process"""
        user_id = update.effective_user.id
        
        result = self.claims_manager.process_claim_step(
            user_id, field, text
        )
        
        update.message.reply_text(
            result['message'],
            reply_markup=result.get('keyboard')
        )
    
    def _handle_dayoff_text(self, update, field, text):
        """Handle text input during day-off request process"""
        user_id = update.effective_user.id
        
        result = self.dayoff_manager.process_dayoff_step(
            user_id, field, text
        )
        
        update.message.reply_text(
            result['message'],
            reply_markup=result.get('keyboard'),
            parse_mode=ParseMode.HTML
        )
    
    def _send_error_message(self, update, message):
        """Send error message to user"""
        try:
            if update.message:
                update.message.reply_text(f"❌ {message}")
            elif update.callback_query:
                update.callback_query.message.reply_text(f"❌ {message}")
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
    
    def _send_callback_error(self, query, message):
        """Send error message for callback query"""
        try:
            query.edit_message_text(f"❌ {message}")
        except Exception as e:
            logger.error(f"Failed to send callback error: {e}")
    
    def _safe_edit_message(self, query, message, reply_markup=None):
        """Safely edit message, handling 'Message is not modified' error"""
        try:
            query.edit_message_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception as e:
            if "Message is not modified" in str(e):
                # Message content is the same, just log and continue
                logger.debug("Message content unchanged, skipping edit")
            else:
                logger.error(f"Failed to edit message: {e}")
                raise
    
    def get_updater(self):
        """Get the updater instance for v13.15 compatibility"""
        return self.updater
