"""
Telegram Bot Handler for python-telegram-bot v13.15
Handles Telegram webhook/polling and message routing with ConversationHandler
"""

import logging
import gc
from typing import Optional
from telegram import Update, Bot
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, CallbackQueryHandler, 
    ConversationHandler, Filters
)
from telegram import ParseMode

from user_manager import UserManager
from claims_manager import ClaimsManager
from dayoff_manager import DayOffManager
from keyboards import KeyboardBuilder
from error_handler import global_error_handler, with_error_handling
from conversation_states import *

logger = logging.getLogger(__name__)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available, memory monitoring disabled")


class TelegramBot:
    """Main Telegram Bot handler class for v13.15"""
    
    def __init__(self, token: str, user_manager: UserManager, claims_manager: ClaimsManager, 
                 dayoff_manager: DayOffManager):
        """
        Initialize bot with token and required managers
        
        Args:
            token: Telegram bot token
            user_manager: User management instance
            claims_manager: Claims management instance
            dayoff_manager: Day-off management instance
        """
        self.token = token
        self.user_manager = user_manager
        self.claims_manager = claims_manager
        self.dayoff_manager = dayoff_manager
        self.error_handler = global_error_handler
        
        # Create updater and dispatcher (v13.15 style)
        self.updater = Updater(token=token, use_context=True)
        self.dispatcher = self.updater.dispatcher
        
        # Setup handlers
        self._setup_handlers()
        
        logger.info("TelegramBot initialized with v13.15 Updater")
    
    def _log_memory_usage(self, operation: str, stage: str) -> float:
        """
        Log current memory usage for monitoring
        
        Args:
            operation: Operation name (e.g., '/start', '/claim')
            stage: Stage of operation (e.g., 'begin', 'end', 'after_gc')
            
        Returns:
            Current memory usage in MB
        """
        if not PSUTIL_AVAILABLE:
            return 0.0
        
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            logger.info(f"[MEMORY] {operation} {stage}: {memory_mb:.2f} MB")
            return memory_mb
        except Exception as e:
            logger.error(f"Error getting memory usage: {e}")
            return 0.0
    
    def _cleanup_and_monitor_memory(self, operation: str, objects_to_clean: list = None) -> None:
        """
        Clean up objects and monitor memory usage
        
        Args:
            operation: Operation name for logging
            objects_to_clean: List of objects to delete
        """
        try:
            # Clean up specified objects
            if objects_to_clean:
                for obj in objects_to_clean:
                    if obj is not None:
                        del obj
            
            # Force garbage collection
            gc.collect()
            
            # Log memory after cleanup
            self._log_memory_usage(operation, "after_cleanup")
            
        except Exception as e:
            logger.error(f"Error in memory cleanup for {operation}: {e}")
    
    def _setup_handlers(self):
        """Setup all message and callback handlers with ConversationHandler"""
        
        # Registration ConversationHandler
        register_handler = ConversationHandler(
            entry_points=[
                CommandHandler('register', self.start_register),
                CallbackQueryHandler(self.start_register, pattern='^register_now$')
            ],
            states={
                REGISTER_NAME: [MessageHandler(Filters.text & ~Filters.command, self.register_name)],
                REGISTER_PHONE: [MessageHandler(Filters.text & ~Filters.command, self.register_phone)],
                REGISTER_ROLE: [CallbackQueryHandler(self.register_role, pattern='^role_')]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel_register),
                CallbackQueryHandler(self.cancel_register, pattern='^cancel$')
            ],
            name="registration",
            persistent=False
        )
        
        # Claim ConversationHandler
        claim_handler = ConversationHandler(
            entry_points=[
                CommandHandler('claim', self.start_claim),
                CallbackQueryHandler(self.start_claim, pattern='^start_claim$')
            ],
            states={
                CLAIM_CATEGORY: [CallbackQueryHandler(self.claim_category, pattern='^category_')],
                CLAIM_AMOUNT: [MessageHandler(Filters.text & ~Filters.command, self.claim_amount)],
                CLAIM_OTHER_DESCRIPTION: [MessageHandler(Filters.text & ~Filters.command, self.claim_other_description)],
                CLAIM_PHOTO: [MessageHandler(Filters.photo, self.claim_photo)],
                CLAIM_CONFIRM: [CallbackQueryHandler(self.claim_confirm, pattern='^confirm_')]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel_claim),
                CallbackQueryHandler(self.cancel_claim, pattern='^cancel$')
            ],
            name="claim",
            persistent=False
        )
        
        # Add ConversationHandlers
        self.dispatcher.add_handler(register_handler)
        self.dispatcher.add_handler(claim_handler)
        
        # Basic command handlers
        self.dispatcher.add_handler(CommandHandler("start", self.handle_start_command))
        self.dispatcher.add_handler(CommandHandler("help", self.handle_help_command))
        self.dispatcher.add_handler(CommandHandler("dayoff", self.handle_dayoff_command))
        
        # General callback handler for non-conversation callbacks
        self.dispatcher.add_handler(CallbackQueryHandler(self.handle_general_callback))
        
        # Fallback message handler
        self.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, self.handle_fallback_message))
        
        # Error handler
        self.dispatcher.add_error_handler(self.handle_error)
        
        logger.info("Bot handlers setup complete with ConversationHandler")
    
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
        """Handle /start command with optimized memory management"""
        # Memory monitoring - start
        memory_start = self._log_memory_usage("/start", "begin")
        
        user_data = None
        keyboard = None
        
        try:
            user_id = update.effective_user.id
            telegram_name = update.effective_user.first_name or "User"
            
            logger.info(f"User {user_id} ({telegram_name}) started bot")
            
            # Check memory and cleanup if needed before processing
            self.state_manager.check_memory_and_cleanup(threshold_mb=300.0)
            
            # Optimized approach: Try to get user data first, if not found, user is not registered
            # This reduces API calls from 2 to 1 for registered users, and 0 for unregistered users
            try:
                user_data = self.user_manager.get_user_data(user_id)
                if user_data:
                    # User is registered
                    display_name = user_data.name
                    keyboard = KeyboardBuilder.start_claim_keyboard()
                    logger.info(f"Registered user {user_id} ({display_name}) accessed /start")
                else:
                    # User is not registered - no Google API calls made
                    display_name = telegram_name
                    keyboard = KeyboardBuilder.register_now_keyboard()
                    logger.info(f"Unregistered user {user_id} ({telegram_name}) accessed /start - no API calls made")
            except Exception as e:
                # Fallback: assume user is not registered
                logger.warning(f"Error checking user {user_id} registration status: {e}")
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
            
            # Memory monitoring - end
            memory_end = self._log_memory_usage("/start", "end")
            if PSUTIL_AVAILABLE and memory_start > 0:
                memory_diff = memory_end - memory_start
                logger.info(f"[MEMORY] /start memory diff: {memory_diff:+.2f} MB")
            
        except Exception as e:
            logger.error(f"Error handling start command: {e}")
            self._send_error_message(update, "Failed to process start command, please try again later.")
        finally:
            # Clean up and monitor memory
            self._cleanup_and_monitor_memory("/start", [user_data, keyboard])
    
    # ==================== REGISTRATION CONVERSATION HANDLERS ====================
    
    def start_register(self, update: Update, context):
        """Start registration conversation"""
        user_id = update.effective_user.id
        
        logger.info(f"User {user_id} started registration")
        
        # Check if user is already registered
        if self.user_manager.is_user_registered(user_id):
            message = "✅ You are already registered! You can now use all bot features."
            
            if update.callback_query:
                update.callback_query.answer()
                update.callback_query.edit_message_text(
                    message,
                    reply_markup=KeyboardBuilder.start_claim_keyboard()
                )
            else:
                update.message.reply_text(
                    message,
                    reply_markup=KeyboardBuilder.start_claim_keyboard()
                )
            return ConversationHandler.END
        
        # Start registration process
        message = "📝 Welcome to PRYMEPLUS Registration!\n\nPlease enter your REAL NAME 👤:"
        
        if update.callback_query:
            update.callback_query.answer()
            update.callback_query.edit_message_text(
                message,
                reply_markup=KeyboardBuilder.cancel_keyboard()
            )
        else:
            update.message.reply_text(
                message,
                reply_markup=KeyboardBuilder.cancel_keyboard()
            )
        
        return REGISTER_NAME
    
    def register_name(self, update: Update, context):
        """Handle name input in registration"""
        user_id = update.effective_user.id
        name = update.message.text.strip()
        
        logger.info(f"User {user_id} provided name: {name[:20]}...")
        
        # Validate name
        result = self.user_manager.process_registration_step(user_id, 'name', name)
        
        if result['success']:
            # Store name in context
            context.user_data['name'] = name
            
            update.message.reply_text(
                result['message'] + "\n\nPlease enter your PHONE NUMBER 📱:",
                reply_markup=KeyboardBuilder.cancel_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return REGISTER_PHONE
        else:
            # Invalid name, ask again
            update.message.reply_text(
                result['message'],
                reply_markup=KeyboardBuilder.cancel_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return REGISTER_NAME
    
    def register_phone(self, update: Update, context):
        """Handle phone input in registration"""
        user_id = update.effective_user.id
        phone = update.message.text.strip()
        
        logger.info(f"User {user_id} provided phone: {phone[:10]}...")
        
        # Validate phone
        result = self.user_manager.process_registration_step(user_id, 'phone', phone)
        
        if result['success']:
            # Store phone in context
            context.user_data['phone'] = phone
            
            update.message.reply_text(
                result['message'] + "\n\nPlease select your ROLE:",
                reply_markup=KeyboardBuilder.role_selection_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return REGISTER_ROLE
        else:
            # Invalid phone, ask again
            update.message.reply_text(
                result['message'],
                reply_markup=KeyboardBuilder.cancel_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return REGISTER_PHONE
    
    def register_role(self, update: Update, context):
        """Handle role selection in registration"""
        query = update.callback_query
        user_id = query.from_user.id
        role_data = query.data
        
        query.answer()
        
        # Extract role from callback data
        role_mapping = {
            'role_staff': 'Staff',
            'role_manager': 'Manager',
            'role_ambassador': 'Ambassador'
        }
        
        role = role_mapping.get(role_data)
        if not role:
            query.edit_message_text(
                "❌ Invalid role selection. Please try again:",
                reply_markup=KeyboardBuilder.role_selection_keyboard()
            )
            return REGISTER_ROLE
        
        logger.info(f"User {user_id} selected role: {role}")
        
        # Get registration data from context
        name = context.user_data.get('name')
        phone = context.user_data.get('phone')
        
        if not name or not phone:
            query.edit_message_text(
                "❌ Registration data missing. Please start again with /register",
                reply_markup=KeyboardBuilder.register_now_keyboard()
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        # Save registration to Google Sheets
        success = self.user_manager.save_registration(user_id, name, phone, role)
        
        if success:
            # Registration completed successfully
            query.edit_message_text(
                f"✅ Registration completed successfully!\n\n"
                f"👤 Name: {name}\n"
                f"📱 Phone: {phone}\n"
                f"🏢 Role: {role}\n\n"
                f"You can now use all bot features!",
                reply_markup=KeyboardBuilder.start_claim_keyboard(),
                parse_mode=ParseMode.HTML
            )
            
            # Clear context data
            context.user_data.clear()
            
            return ConversationHandler.END
        else:
            # Registration failed
            query.edit_message_text(
                "❌ Failed to save registration. Please try again.",
                reply_markup=KeyboardBuilder.role_selection_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return REGISTER_ROLE
    
    def cancel_register(self, update: Update, context):
        """Cancel registration conversation"""
        user_id = update.effective_user.id
        logger.info(f"User {user_id} cancelled registration")
        
        message = "❌ Registration cancelled. You can start again anytime with /register"
        
        if update.callback_query:
            update.callback_query.answer()
            update.callback_query.edit_message_text(
                message,
                reply_markup=KeyboardBuilder.register_now_keyboard()
            )
        else:
            update.message.reply_text(
                message,
                reply_markup=KeyboardBuilder.register_now_keyboard()
            )
        
        # Clear context data
        context.user_data.clear()
        
        return ConversationHandler.END
    
    # ==================== CLAIM CONVERSATION HANDLERS ====================
    
    def start_claim(self, update: Update, context):
        """Start claim conversation"""
        user_id = update.effective_user.id
        
        logger.info(f"User {user_id} started claim process")
        
        # Check if user is registered
        has_permission, error_msg = self.user_manager.check_user_permission(user_id)
        
        if not has_permission:
            message = error_msg
            
            if update.callback_query:
                update.callback_query.answer()
                update.callback_query.edit_message_text(
                    message,
                    reply_markup=KeyboardBuilder.register_now_keyboard()
                )
            else:
                update.message.reply_text(
                    message,
                    reply_markup=KeyboardBuilder.register_now_keyboard()
                )
            return ConversationHandler.END
        
        # Start claim process
        message = "💰 Welcome to PRYMEPLUS Claim System!\n\nPlease select expense category:"
        
        if update.callback_query:
            update.callback_query.answer()
            update.callback_query.edit_message_text(
                message,
                reply_markup=KeyboardBuilder.claim_categories_keyboard()
            )
        else:
            update.message.reply_text(
                message,
                reply_markup=KeyboardBuilder.claim_categories_keyboard()
            )
        
        # Initialize claim data in context
        context.user_data['claim_data'] = {}
        
        return CLAIM_CATEGORY
    
    def claim_category(self, update: Update, context):
        """Handle category selection in claim"""
        query = update.callback_query
        user_id = query.from_user.id
        category_data = query.data
        
        query.answer()
        
        logger.info(f"User {user_id} selected category: {category_data}")
        
        # Process category selection
        result = self.claims_manager.process_claim_step(user_id, 'category', category_data)
        
        if result['success']:
            # Store category in context
            context.user_data['claim_data']['category'] = category_data
            
            query.edit_message_text(
                result['message'],
                reply_markup=KeyboardBuilder.cancel_keyboard()
            )
            return CLAIM_AMOUNT
        else:
            # Invalid category
            query.edit_message_text(
                result['message'],
                reply_markup=KeyboardBuilder.claim_categories_keyboard()
            )
            return CLAIM_CATEGORY
    
    def claim_amount(self, update: Update, context):
        """Handle amount input in claim"""
        user_id = update.effective_user.id
        amount_text = update.message.text.strip()
        
        logger.info(f"User {user_id} entered amount: {amount_text}")
        
        # Process amount input
        result = self.claims_manager.process_claim_step(user_id, 'amount', amount_text)
        
        if result['success']:
            # Store amount in context
            context.user_data['claim_data']['amount'] = amount_text
            
            # Check if category is "Other" - if so, ask for description
            category = context.user_data['claim_data'].get('category', '')
            if 'other' in category.lower():
                update.message.reply_text(
                    "📝 Please enter what you are claiming for:\n\nExample: Stationery purchase, Parking fee, etc...",
                    reply_markup=KeyboardBuilder.cancel_keyboard()
                )
                return CLAIM_OTHER_DESCRIPTION
            else:
                # Move directly to photo upload
                update.message.reply_text(
                    result['message'],
                    reply_markup=KeyboardBuilder.cancel_keyboard()
                )
                return CLAIM_PHOTO
        else:
            # Invalid amount, ask again
            update.message.reply_text(
                result['message'],
                reply_markup=KeyboardBuilder.cancel_keyboard()
            )
            return CLAIM_AMOUNT
    
    def claim_other_description(self, update: Update, context):
        """Handle other category description in claim"""
        user_id = update.effective_user.id
        description = update.message.text.strip()
        
        logger.info(f"User {user_id} provided other description: {description[:30]}...")
        
        # Process description
        result = self.claims_manager.process_claim_step(user_id, 'other_description', description)
        
        if result['success']:
            # Store description in context
            context.user_data['claim_data']['other_description'] = description
            
            update.message.reply_text(
                result['message'],
                reply_markup=KeyboardBuilder.cancel_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return CLAIM_PHOTO
        else:
            # Invalid description, ask again
            update.message.reply_text(
                result['message'],
                reply_markup=KeyboardBuilder.cancel_keyboard()
            )
            return CLAIM_OTHER_DESCRIPTION
    
    def claim_photo(self, update: Update, context):
        """Handle photo upload in claim"""
        user_id = update.effective_user.id
        
        logger.info(f"User {user_id} uploaded photo")
        
        # Get photo data
        photo = update.message.photo[-1]  # Get highest resolution
        photo_file = photo.get_file()
        photo_data = photo_file.download_as_bytearray()
        
        # Process photo upload
        result = self.claims_manager.process_claim_step(user_id, 'photo', bytes(photo_data))
        
        if result['success']:
            # Store photo info in context
            context.user_data['claim_data']['photo_uploaded'] = True
            
            update.message.reply_text(
                result['message'],
                reply_markup=KeyboardBuilder.confirmation_keyboard()
            )
            return CLAIM_CONFIRM
        else:
            # Invalid photo, ask again
            update.message.reply_text(
                result['message'],
                reply_markup=KeyboardBuilder.cancel_keyboard()
            )
            return CLAIM_PHOTO
    
    def claim_confirm(self, update: Update, context):
        """Handle claim confirmation"""
        query = update.callback_query
        user_id = query.from_user.id
        confirm_data = query.data
        
        query.answer()
        
        logger.info(f"User {user_id} claim confirmation: {confirm_data}")
        
        # Process confirmation
        result = self.claims_manager.process_claim_step(user_id, 'confirm', confirm_data)
        
        query.edit_message_text(
            result['message'],
            reply_markup=KeyboardBuilder.start_claim_keyboard() if result['success'] else KeyboardBuilder.confirmation_keyboard()
        )
        
        # Clear context data
        context.user_data.clear()
        
        return ConversationHandler.END
    
    def cancel_claim(self, update: Update, context):
        """Cancel claim conversation"""
        user_id = update.effective_user.id
        logger.info(f"User {user_id} cancelled claim")
        
        message = "❌ Claim process cancelled. You can start again anytime with /claim"
        
        if update.callback_query:
            update.callback_query.answer()
            update.callback_query.edit_message_text(
                message,
                reply_markup=KeyboardBuilder.start_claim_keyboard()
            )
        else:
            update.message.reply_text(
                message,
                reply_markup=KeyboardBuilder.start_claim_keyboard()
            )
        
        # Clear context data
        context.user_data.clear()
        
        return ConversationHandler.END
    
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
        """Handle /claim command with memory optimization"""
        # Memory monitoring - start
        memory_start = self._log_memory_usage("/claim", "begin")
        
        result = None
        
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
            
            # Memory monitoring - end
            memory_end = self._log_memory_usage("/claim", "end")
            if PSUTIL_AVAILABLE and memory_start > 0:
                memory_diff = memory_end - memory_start
                logger.info(f"[MEMORY] /claim memory diff: {memory_diff:+.2f} MB")
                
        except Exception as e:
            logger.error(f"Error handling claim command: {e}")
            self._send_error_message(update, "Failed to process claim command, please try again later.")
        finally:
            # Clean up and monitor memory
            self._cleanup_and_monitor_memory("/claim", [result])
    
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
    
    def handle_general_callback(self, update: Update, context):
        """Handle general callbacks not handled by ConversationHandler"""
        query = update.callback_query
        callback_data = query.data
        
        query.answer()
        
        logger.info(f"General callback: {callback_data}")
        
        if callback_data == 'start_dayoff':
            # Handle day-off start
            result = self.dayoff_manager.start_dayoff_request(query.from_user.id)
            query.edit_message_text(
                result['message'],
                reply_markup=result.get('keyboard'),
                parse_mode=ParseMode.HTML
            )
        elif callback_data == 'new_claim':
            # Start new claim
            query.edit_message_text(
                "💰 Starting new claim process...\n\nPlease select expense category:",
                reply_markup=KeyboardBuilder.claim_categories_keyboard()
            )
        else:
            query.edit_message_text("Unknown operation, please use the menu buttons.")
    
    def handle_fallback_message(self, update: Update, context):
        """Handle messages not in any conversation"""
        update.message.reply_text(
            "Please use one of the following commands:\n"
            "• /register - Register your information\n"
            "• /claim - Submit expense claim\n"
            "• /help - View help information\n"
            "• /dayoff - Request day-off"
        )
    
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
        """Handle photo uploads with optimized memory management"""
        photo_data = None
        try:
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            message_id = update.message.message_id
            
            logger.info(f"User {user_id} uploaded photo")
            
            # Check memory before processing large files
            self.state_manager.check_memory_and_cleanup(threshold_mb=350.0)
            
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
                # Get photo data with memory optimization
                photo = update.message.photo[-1]  # Get highest resolution
                photo_file = photo.get_file()
                
                # Download as bytes directly to avoid bytearray -> bytes conversion
                photo_data = photo_file.download_as_bytearray()
                logger.debug(f"Downloaded photo: {len(photo_data)} bytes")
                
                # Process photo upload immediately and release memory
                result = self.claims_manager.process_claim_step(
                    user_id, 'photo', bytes(photo_data)
                )
                
                # Immediately clear photo data from memory
                del photo_data
                photo_data = None
                
                # Force garbage collection after large file processing
                import gc
                gc.collect()
                
                # Delete the original photo message from user
                try:
                    context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    logger.debug(f"Deleted original photo message {message_id} from user {user_id}")
                except Exception as delete_error:
                    logger.warning(f"Failed to delete photo message {message_id}: {delete_error}")
                
                # Delete the processing message
                try:
                    context.bot.delete_message(chat_id=chat_id, message_id=processing_message.message_id)
                except Exception as delete_error:
                    logger.warning(f"Failed to delete processing message: {delete_error}")
                
                # Send final result message
                if result['success']:
                    final_message = "✅ Receipt saved successfully!\n\n" + result['message']
                    update.effective_chat.send_message(
                        text=final_message,
                        reply_markup=result['keyboard']
                    )
                else:
                    update.effective_chat.send_message(
                        text=result['message'],
                        reply_markup=result.get('keyboard')
                    )
                    
            except Exception as processing_error:
                # Clean up photo data on error
                if photo_data is not None:
                    del photo_data
                    photo_data = None
                
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
            # Ensure photo data is cleaned up on any error
            if photo_data is not None:
                del photo_data
                photo_data = None
            
            logger.error(f"Error handling photo upload: {e}")
            self._send_error_message(update, "Photo processing failed, please try again later.")
        finally:
            # Final cleanup to ensure memory is released
            if photo_data is not None:
                del photo_data
            import gc
            gc.collect()
    
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
        
        # ConversationHandler will automatically handle state cleanup on errors
        # No manual state clearing needed
    
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
