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
from state_manager import StateManager
from models import UserStateType
from keyboards import KeyboardBuilder
from error_handler import global_error_handler, with_error_handling

logger = logging.getLogger(__name__)


class TelegramBot:
    """Main Telegram Bot handler class for v13.15"""
    
    def __init__(self, token: str, user_manager: UserManager, claims_manager: ClaimsManager, 
                 state_manager: StateManager):
        """
        Initialize bot with token and required managers
        
        Args:
            token: Telegram bot token
            user_manager: User management instance
            claims_manager: Claims management instance
            state_manager: State management instance
        """
        self.token = token
        self.user_manager = user_manager
        self.claims_manager = claims_manager
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
        Start webhook for production deployment (v13.15 style)
        
        Args:
            webhook_url: URL for webhook
            port: Port to listen on
        """
        try:
            logger.info(f"Starting webhook on {webhook_url}:{port}")
            
            # Set webhook
            self.updater.bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook set to: {webhook_url}")
            
            # Start Flask server for health check and webhook handling
            from flask import Flask, request, jsonify
            import time
            
            app = Flask(__name__)
            start_time = time.time()
            health_check_count = 0
            
            @app.route('/health')
            def health_check():
                """Health check endpoint for monitoring"""
                nonlocal health_check_count
                health_check_count += 1
                
                uptime_seconds = time.time() - start_time
                uptime_hours = uptime_seconds / 3600
                hours, remainder = divmod(int(uptime_seconds), 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime_human = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"
                
                return jsonify({
                    'status': 'healthy',
                    'service': 'telegram-claim-bot',
                    'timestamp': time.time(),
                    'uptime_seconds': uptime_seconds,
                    'uptime_hours': round(uptime_hours, 2),
                    'uptime_human': uptime_human,
                    'health_checks_total': health_check_count,
                    'monitoring_interval': '10_minutes',
                    'version': '1.0.0',
                    'deployment': 'render_production',
                    'telegram_bot_version': '13.15'
                }), 200
            
            @app.route('/', methods=['POST'])
            def webhook():
                """Handle incoming webhook updates from Telegram"""
                try:
                    update_data = request.get_json()
                    if update_data:
                        # Create update object and process it (v13.15 style)
                        update = Update.de_json(update_data, self.updater.bot)
                        self.dispatcher.process_update(update)
                    
                    return '', 200
                except Exception as e:
                    logger.error(f"Webhook processing error: {e}")
                    return '', 500
            
            # Run Flask app
            logger.info(f"Starting Flask server on port {port}")
            app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
            
        except Exception as e:
            logger.error(f"Failed to start webhook: {e}")
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
        """Handle /start command"""
        try:
            user_id = update.effective_user.id
            user_name = update.effective_user.first_name or "User"
            
            logger.info(f"User {user_id} ({user_name}) started bot")
            
            # Check if user is registered (v13.15 - synchronous call)
            is_registered = self.user_manager.is_user_registered(user_id)
            
            if is_registered:
                message = (
                    f"Welcome back, {user_name}! 👋\n\n"
                    "You are already registered and can use the following features:\n"
                    "• /claim - Submit expense claim\n"
                    "• /help - View help information"
                )
                keyboard = KeyboardBuilder.claim_complete_keyboard()
            else:
                message = (
                    f"Welcome to the Expense Claim System, {user_name}! 👋\n\n"
                    "Please register your information first to use the system:\n"
                    "• /register - Register user information\n"
                    "• /help - View help information"
                )
                keyboard = KeyboardBuilder.registration_complete_keyboard()
            
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
                "📋 <b>Expense Claim System Help</b>\n\n"
                "<b>Available Commands:</b>\n"
                "• /start - Start using the system\n"
                "• /register - Register user information\n"
                "• /claim - Submit expense claim\n"
                "• /help - Show this help information\n\n"
                "<b>Usage Flow:</b>\n"
                "1. Use /register to register your information\n"
                "2. Use /claim to submit expense claim\n"
                "3. Select category, enter amount, upload receipt\n"
                "4. Confirm and submit claim\n\n"
                "<b>Supported Expense Categories:</b>\n"
                "• 🍔 Food - Food expenses\n"
                "• 🚗 Transportation - Transportation costs\n"
                "• ✈️ Flight - Flight expenses\n"
                "• 🎉 Event - Event costs\n"
                "• 🤖 AI - AI tool expenses\n"
                "• 📦 Other - Other expenses\n\n"
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
                    reply_markup=keyboard
                )
            else:
                update.message.reply_text(result['message'])
                
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
        """Handle photo uploads"""
        try:
            user_id = update.effective_user.id
            
            logger.info(f"User {user_id} uploaded photo")
            
            # Get current user state
            current_state, temp_data = self.state_manager.get_user_state(user_id)
            
            if current_state != UserStateType.CLAIMING_PHOTO:
                update.message.reply_text(
                    "Please use /claim command first to start the claim process, then upload receipt photo as prompted."
                )
                return
            
            # Get photo data (v13.15 style)
            photo = update.message.photo[-1]  # Get highest resolution
            photo_file = photo.get_file()
            photo_data = photo_file.download_as_bytearray()
            
            # Process photo upload
            result = self.claims_manager.process_claim_step(
                user_id, 'photo', bytes(photo_data)
            )
            
            if result['success']:
                update.message.reply_text(
                    result['message'],
                    reply_markup=result['keyboard']
                )
            else:
                update.message.reply_text(
                    result['message'],
                    reply_markup=result.get('keyboard')
                )
                
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
    
    def _handle_cancel_callback(self, query, current_state):
        """Handle cancel callback"""
        user_id = query.from_user.id
        
        if self.state_manager.is_user_registering(user_id):
            result = self.user_manager.cancel_registration(user_id)
            self._safe_edit_message(query, result['message'])
        
        elif self.state_manager.is_user_claiming(user_id):
            result = self.claims_manager.cancel_claim_process(user_id)
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
            reply_markup=keyboard
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
            query.edit_message_text(message, reply_markup=reply_markup)
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
