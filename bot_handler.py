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
from datetime import datetime  # Added for date parsing in dayoff handlers

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
    """Main Telegram Bot handler class for v13.15 with ConversationHandler"""
    
    def __init__(self, token: str, user_manager: UserManager, claims_manager: ClaimsManager, 
                 dayoff_manager: DayOffManager, config=None):
        self.config = config
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
        
        logger.info("TelegramBot initialized with ConversationHandler")
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        if not self.config:
            logger.warning("No config object found")
            return False
        if not hasattr(self.config, 'ADMIN_IDS'):
            logger.warning("No ADMIN_IDS attribute in config")
            return False
        if not self.config.ADMIN_IDS:
            logger.warning(f"ADMIN_IDS is empty: {self.config.ADMIN_IDS}")
            return False
        
        logger.info(f"Checking admin status for user {user_id}, ADMIN_IDS: {self.config.ADMIN_IDS}")
        is_admin = user_id in self.config.ADMIN_IDS
        logger.info(f"User {user_id} admin status: {is_admin}")
        return is_admin
    
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
            persistent=False  # In-memory state only, requires single worker to maintain state
                             # For multi-worker setup, would need persistent=True with BasePersistence implementation
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
        
        # Day-off ConversationHandler
        dayoff_handler = ConversationHandler(
            entry_points=[
                CommandHandler('dayoff', self.start_dayoff),
                CallbackQueryHandler(self.start_dayoff, pattern='^start_dayoff$')
            ],
            states={
                DAYOFF_TYPE: [CallbackQueryHandler(self.dayoff_type, pattern='^dayoff_type_')],
                DAYOFF_DATE: [MessageHandler(Filters.text & ~Filters.command, self.dayoff_date)],
                DAYOFF_START_DATE: [MessageHandler(Filters.text & ~Filters.command, self.dayoff_start_date)],
                DAYOFF_END_DATE: [MessageHandler(Filters.text & ~Filters.command, self.dayoff_end_date)],
                DAYOFF_REASON: [MessageHandler(Filters.text & ~Filters.command, self.dayoff_reason)]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel_dayoff),
                CallbackQueryHandler(self.cancel_dayoff, pattern='^cancel$')
            ],
            name="dayoff",
            persistent=False
        )
        self.dispatcher.add_handler(dayoff_handler)
        
        # Admin Total ConversationHandler
        total_handler = ConversationHandler(
            entry_points=[CommandHandler('Total', self.start_total)],
            states={
                TOTAL_ROLE: [CallbackQueryHandler(self.total_role, pattern='^role_')],
                TOTAL_USER: [CallbackQueryHandler(self.total_user, pattern='^user_')],
                TOTAL_CONFIRM: [CallbackQueryHandler(self.total_confirm, pattern='^approve_')]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel_total),
                CallbackQueryHandler(self.cancel_total, pattern='^cancel$')
            ],
            name="total",
            persistent=False
        )
        self.dispatcher.add_handler(total_handler)
        
        # Admin Deleted ConversationHandler
        deleted_handler = ConversationHandler(
            entry_points=[CommandHandler('Deleted', self.start_deleted)],
            states={
                DELETED_ROLE: [CallbackQueryHandler(self.deleted_role, pattern='^role_')],
                DELETED_USER: [CallbackQueryHandler(self.deleted_user, pattern='^user_')]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel_deleted),
                CallbackQueryHandler(self.cancel_deleted, pattern='^cancel$')
            ],
            name="deleted",
            persistent=False
        )
        self.dispatcher.add_handler(deleted_handler)
        
        # Basic command handlers
        self.dispatcher.add_handler(CommandHandler("start", self.handle_start_command))
        self.dispatcher.add_handler(CommandHandler("help", self.handle_help_command))
        # Remove CommandHandler for dayoff since it's now handled by ConversationHandler
        # self.dispatcher.add_handler(CommandHandler("dayoff", self.handle_dayoff_command))
        
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
            
            # Skip memory cleanup to avoid triggering unnecessary operations
            
            # Ultra-optimized approach: For /start, use universal keyboard without API calls
            # Registration status will be checked when user tries to use specific features
            display_name = telegram_name
            keyboard = KeyboardBuilder.universal_start_keyboard()
            
            # Log that we're using zero-API approach for /start
            logger.info(f"User {user_id} ({telegram_name}) accessed /start - zero Google API calls")
            
            # Check if user is admin and add admin commands
            admin_commands = ""
            if self.is_admin(user_id):
                admin_commands = (
                    f"\n<b>👑 Admin Commands:</b>\n"
                    f"• /Total - View user claims total 📊\n"
                    f"• /Deleted - Delete user data 🗑️\n"
                )
            
            # Optimized welcome message with HTML format and emojis
            message = (
                f"<b>🎉 Welcome to PRYME PLUS Bot!</b>\n\n"
                f"Hey there, <b>{display_name}</b>! 👋 Great to see you here!\n\n"
                f"I'm your <b>PRYMEPLUS Claim Assistant</b>, ready to make your claim process easier! 💼✨\n\n"
                f"<b>📋 Available Commands:</b>\n"
                f"• /register - Register your information 📝\n"
                f"• /claim - Submit your expense claim 💰\n"
                f"• /help - View help information ℹ️\n"
                f"• /dayoff - Request Day-off 🗓️\n"
                f"{admin_commands}\n"
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
        result = self.claims_manager._process_category_selection(user_id, category_data)
        
        if result['success']:
            # Store category in context
            context.user_data['claim_data']['category'] = result.get('category', category_data)
            
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
        
        # Get category from context
        category = context.user_data['claim_data'].get('category', '')
        
        # Process amount input
        result = self.claims_manager._process_amount_input(user_id, amount_text, category)
        
        if result['success']:
            # Store amount in context
            context.user_data['claim_data']['amount'] = result.get('amount', amount_text)
            
            # Check if needs description (Other category)
            if result.get('needs_description', False):
                update.message.reply_text(
                    result['message'],
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
        result = self.claims_manager._process_other_description_input(user_id, description)
        
        if result['success']:
            # Store description in context and update category
            context.user_data['claim_data']['other_description'] = result.get('description', description)
            context.user_data['claim_data']['category'] = f"Other : {result.get('description', description)}"
            
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
        
        # Get claim data from context
        claim_data = context.user_data.get('claim_data', {})
        
        # Process photo upload
        result = self.claims_manager._process_photo_upload(user_id, bytes(photo_data), claim_data)
        
        if result['success']:
            # Store receipt link in context
            context.user_data['claim_data']['receipt_link'] = result.get('receipt_link')
            
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
        
        # Get claim data from context
        claim_data = context.user_data.get('claim_data', {})
        
        # Process confirmation
        result = self.claims_manager._process_confirmation(user_id, confirm_data, claim_data)
        
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
    
    # Remove handle_dayoff_command since /dayoff is now entry point of ConversationHandler
    # def handle_dayoff_command(self, update: Update, context):
    #     """Handle /dayoff command"""
    #     try:
    #         user_id = update.effective_user.id
    #         
    #         logger.info(f"User {user_id} initiated day-off request")
    #         
    #         # Start day-off request process
    #         result = self.dayoff_manager.start_dayoff_request(user_id)
    #         
    #         update.message.reply_text(
    #             result['message'],
    #             reply_markup=result.get('keyboard'),
    #             parse_mode=ParseMode.HTML
    #         )
    #             
    #     except Exception as e:
    #         logger.error(f"Error handling dayoff command: {e}")
    #         self._send_error_message(update, "Failed to process day-off command, please try again later.")
    
    # ==================== DAY-OFF CONVERSATION HANDLERS ====================
    
    def start_dayoff(self, update: Update, context):
        """Start day-off conversation"""
        user_id = update.effective_user.id
        
        logger.info(f"User {user_id} started day-off request")
        
        result = self.dayoff_manager.start_dayoff_request(user_id)
        
        message = result['message']
        keyboard = result.get('keyboard')
        
        if update.callback_query:
            update.callback_query.answer()
            update.callback_query.edit_message_text(
                message,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
        else:
            update.message.reply_text(
                message,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
        
        if not result['success']:
            return ConversationHandler.END
        
        return DAYOFF_TYPE
    
    def dayoff_type(self, update: Update, context):
        query = update.callback_query
        user_id = query.from_user.id
        type_data = query.data
        
        query.answer()
        
        dayoff_type = type_data.split('_')[-1]  # oneday or multiday
        context.user_data['dayoff_type'] = dayoff_type
        
        logger.info(f"User {user_id} selected day-off type: {dayoff_type}")
        
        if dayoff_type == 'oneday':
            message = "Please enter the date for your day-off (DD/MM/YYYY):"
            next_state = DAYOFF_DATE
        else:
            message = "Please enter the start date (DD/MM/YYYY):"
            next_state = DAYOFF_START_DATE
        
        query.edit_message_text(
            message,
            reply_markup=KeyboardBuilder.cancel_keyboard()
        )
        return next_state
    
    def dayoff_date(self, update: Update, context):
        user_id = update.effective_user.id
        date_str = update.message.text.strip()
        
        logger.info(f"User {user_id} provided day-off date: {date_str}")
        
        is_valid, error_msg = self.dayoff_manager.validate_date_format(date_str)
        if not is_valid:
            update.message.reply_text(
                error_msg + "\n\nPlease enter the date again:",
                reply_markup=KeyboardBuilder.cancel_keyboard()
            )
            return DAYOFF_DATE
        
        context.user_data['dayoff_date'] = date_str
        
        update.message.reply_text(
            "Please provide the reason for your day-off:",
            reply_markup=KeyboardBuilder.cancel_keyboard()
        )
        return DAYOFF_REASON
    
    def dayoff_start_date(self, update: Update, context):
        user_id = update.effective_user.id
        date_str = update.message.text.strip()
        
        logger.info(f"User {user_id} provided start date: {date_str}")
        
        is_valid, error_msg = self.dayoff_manager.validate_date_format(date_str)
        if not is_valid:
            update.message.reply_text(
                error_msg + "\n\nPlease enter the start date again:",
                reply_markup=KeyboardBuilder.cancel_keyboard()
            )
            return DAYOFF_START_DATE
        
        context.user_data['start_date'] = date_str
        
        update.message.reply_text(
            "Please enter the end date (DD/MM/YYYY):",
            reply_markup=KeyboardBuilder.cancel_keyboard()
        )
        return DAYOFF_END_DATE
    
    def dayoff_end_date(self, update: Update, context):
        user_id = update.effective_user.id
        end_date = update.message.text.strip()
        start_date = context.user_data.get('start_date')
        
        logger.info(f"User {user_id} provided end date: {end_date}")
        
        is_valid, error_msg = self.dayoff_manager.validate_date_format(end_date)
        if not is_valid:
            update.message.reply_text(
                error_msg + "\n\nPlease enter the end date again:",
                reply_markup=KeyboardBuilder.cancel_keyboard()
            )
            return DAYOFF_END_DATE
        
        # Check if end date after start date
        start_dt = datetime.strptime(start_date, '%d/%m/%Y')
        end_dt = datetime.strptime(end_date, '%d/%m/%Y')
        if end_dt <= start_dt:
            update.message.reply_text(
                "End date must be after start date.\n\nPlease enter the end date again:",
                reply_markup=KeyboardBuilder.cancel_keyboard()
            )
            return DAYOFF_END_DATE
        
        context.user_data['dayoff_date'] = f"{start_date} - {end_date}"
        
        update.message.reply_text(
            "Please provide the reason for your day-off:",
            reply_markup=KeyboardBuilder.cancel_keyboard()
        )
        return DAYOFF_REASON
    
    def dayoff_reason(self, update: Update, context):
        user_id = update.effective_user.id
        reason = update.message.text.strip()
        
        logger.info(f"User {user_id} provided reason: {reason[:20]}...")
        
        is_valid, error_msg = self.dayoff_manager.validate_reason(reason)
        if not is_valid:
            update.message.reply_text(
                error_msg + "\n\nPlease enter the reason again:",
                reply_markup=KeyboardBuilder.cancel_keyboard()
            )
            return DAYOFF_REASON
        
        dayoff_type = context.user_data.get('dayoff_type')
        dayoff_date = context.user_data.get('dayoff_date')
        
        success = self.dayoff_manager.save_dayoff_request(user_id, dayoff_type, dayoff_date, reason)
        
        if success:
            message = "✅ Day-off request submitted successfully!\n\nYour request is pending review."
        else:
            message = "❌ Failed to submit day-off request. Please try again later."
        
        update.message.reply_text(
            message,
            reply_markup=KeyboardBuilder.universal_start_keyboard()
        )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    def cancel_dayoff(self, update: Update, context):
        """Cancel day-off conversation"""
        user_id = update.effective_user.id
        logger.info(f"User {user_id} cancelled day-off request")
        
        message = "❌ Day-off request cancelled. You can start again with /dayoff"
        
        if update.callback_query:
            update.callback_query.answer()
            update.callback_query.edit_message_text(
                message,
                reply_markup=KeyboardBuilder.universal_start_keyboard()
            )
        else:
            update.message.reply_text(
                message,
                reply_markup=KeyboardBuilder.universal_start_keyboard()
            )
        
        context.user_data.clear()
        return ConversationHandler.END

    def handle_general_callback(self, update: Update, context):
        """Handle general callbacks not handled by ConversationHandler"""
        query = update.callback_query
        callback_data = query.data
        
        query.answer()
        
        logger.info(f"General callback: {callback_data}")
        
        if callback_data == 'new_claim':
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
    
    def _send_error_message(self, update: Update, message: str):
        """Send error message to user"""
        try:
            if update.message:
                update.message.reply_text(message)
            elif update.callback_query:
                update.callback_query.message.reply_text(message)
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
    
    def _send_callback_error(self, query, message: str):
        """Send error message for callback query"""
        try:
            query.answer(message, show_alert=True)
        except Exception as e:
            logger.error(f"Failed to send callback error: {e}")
    
    def _safe_edit_message(self, query, text: str, reply_markup=None):
        """Safely edit message text"""
        try:
            query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to edit message: {e}")
            try:
                query.message.reply_text(text, reply_markup=reply_markup)
            except Exception as e2:
                logger.error(f"Failed to send new message: {e2}")

    # ==================== TOTAL CONVERSATION HANDLERS ====================

    def start_total(self, update: Update, context):
        user_id = update.effective_user.id
        if not self.is_admin(user_id):
            update.message.reply_text("You don't have permission to use this command.")
            return ConversationHandler.END
        update.message.reply_text("Select role type:", reply_markup=KeyboardBuilder.role_selection_keyboard())
        return TOTAL_ROLE

    def total_role(self, update: Update, context):
        query = update.callback_query
        role = query.data.split('_')[1]
        context.user_data['role'] = role
        users = self.user_manager.get_registered_users(role)  # Assume this method exists or add it
        if not users:
            query.edit_message_text("No users found for this role.")
            return ConversationHandler.END
        keyboard = KeyboardBuilder.user_selection_keyboard(users)
        query.edit_message_text("Select user:", reply_markup=keyboard)
        return TOTAL_USER

    def total_user(self, update: Update, context):
        query = update.callback_query
        user_id = int(query.data.split('_')[1])
        
        try:
            claims = self.claims_manager.get_user_claims(user_id)
            total_count = len(claims)
            total_amount = sum(claim['amount'] for claim in claims)
            categories = set(claim['category'] for claim in claims)
            
            # Format the message with better display
            if total_count > 0:
                categories_str = ', '.join(sorted(categories)) if categories else 'None'
                message = f"📊 **Claims Summary**\n\n"
                message += f"👤 **User ID:** {user_id}\n"
                message += f"📋 **Total Claims:** {total_count}\n"
                message += f"💰 **Total Amount:** RM {total_amount:.2f}\n"
                message += f"🏷️ **Categories:** {categories_str}\n\n"
                
                # Show recent claims details
                message += "📝 **Recent Claims:**\n"
                for i, claim in enumerate(claims[:5], 1):  # Show up to 5 recent claims
                    message += f"{i}. {claim['category']} - RM {claim['amount']:.2f} ({claim['status']})\n"
                
                if total_count > 5:
                    message += f"... and {total_count - 5} more claims\n"
            else:
                message = f"📊 **Claims Summary**\n\n"
                message += f"👤 **User ID:** {user_id}\n"
                message += f"📋 **No claims found for this user.**\n"
            
            query.edit_message_text(message, reply_markup=KeyboardBuilder.confirm_approve_keyboard(), parse_mode='Markdown')
            context.user_data['selected_user'] = user_id
            return TOTAL_CONFIRM
            
        except Exception as e:
            logger.error(f"Error in total_user for user {user_id}: {e}")
            query.edit_message_text(f"❌ Error retrieving claims data for user {user_id}. Please try again.", 
                                  reply_markup=KeyboardBuilder.confirm_approve_keyboard())
            return TOTAL_CONFIRM

    def total_confirm(self, update: Update, context):
        query = update.callback_query
        if query.data == 'approve_yes':
            user_id = context.user_data['selected_user']
            self.claims_manager.delete_user_claims(user_id)  # Assume method
            self.drive_client.delete_user_photos(user_id)  # Assume
            query.edit_message_text("Claims approved and deleted.")
        else:
            query.edit_message_text("Operation cancelled.")
        gc.collect()
        context.user_data.clear()
        return ConversationHandler.END

    def cancel_total(self, update: Update, context):
        update.message.reply_text("Total operation cancelled.")
        context.user_data.clear()
        return ConversationHandler.END

    # ==================== DELETED CONVERSATION HANDLERS ====================

    def start_deleted(self, update: Update, context):
        user_id = update.effective_user.id
        if not self.is_admin(user_id):
            update.message.reply_text("You don't have permission to use this command.")
            return ConversationHandler.END
        update.message.reply_text("Select role type:", reply_markup=KeyboardBuilder.role_selection_keyboard())
        return DELETED_ROLE

    def deleted_role(self, update: Update, context):
        query = update.callback_query
        role = query.data.split('_')[1]
        context.user_data['role'] = role
        users = self.user_manager.get_registered_users(role)
        if not users:
            query.edit_message_text("No users found for this role.")
            return ConversationHandler.END
        keyboard = KeyboardBuilder.user_selection_keyboard(users)
        query.edit_message_text("Select user to delete:", reply_markup=keyboard)
        return DELETED_USER

    def deleted_user(self, update: Update, context):
        query = update.callback_query
        user_id = int(query.data.split('_')[1])
        self.user_manager.delete_user_data(user_id, context.user_data['role'])
        self.claims_manager.delete_user_claims(user_id)
        self.drive_client.delete_user_photos(user_id)
        query.edit_message_text("User data and files deleted.")
        gc.collect()
        context.user_data.clear()
        return ConversationHandler.END

    def cancel_deleted(self, update: Update, context):
        update.message.reply_text("Delete operation cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
