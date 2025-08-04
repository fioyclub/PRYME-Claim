"""
Telegram Bot Handler
Handles Telegram webhook/polling and message routing with comprehensive error handling
"""

import logging
from typing import Optional
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.constants import ParseMode

from user_manager import UserManager
from claims_manager import ClaimsManager
from state_manager import StateManager
from models import UserStateType
from keyboards import KeyboardBuilder
from error_handler import global_error_handler, with_error_handling

logger = logging.getLogger(__name__)


class TelegramBot:
    """Main Telegram Bot handler class"""
    
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
        
        # Create application
        self.application = Application.builder().token(token).build()
        
        # Setup handlers
        self._setup_handlers()
        
        logger.info("TelegramBot initialized with token")
    
    def _setup_handlers(self):
        """Setup all message and callback handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.handle_start_command))
        self.application.add_handler(CommandHandler("register", self.handle_register_command))
        self.application.add_handler(CommandHandler("claim", self.handle_claim_command))
        self.application.add_handler(CommandHandler("help", self.handle_help_command))
        
        # Callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Message handlers
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_input))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo_upload))
        
        # Error handler
        self.application.add_error_handler(self.handle_error)
        
        logger.info("Bot handlers setup complete")
    
    async def start_webhook(self, webhook_url: str, port: int = 8000):
        """
        Start webhook for production deployment
        
        Args:
            webhook_url: URL for webhook
            port: Port to listen on
        """
        try:
            logger.info(f"Starting webhook on {webhook_url}:{port}")
            
            await self.application.initialize()
            await self.application.start()
            
            # Set webhook
            await self.application.bot.set_webhook(url=webhook_url)
            
            # Start webhook server with health check support
            from flask import Flask, jsonify
            import time
            
            # Create Flask app for webhook and health check
            app = Flask(__name__)
            start_time = time.time()
            health_check_count = 0
            
            @app.route('/health')
            def health_check():
                """Health check endpoint for monitoring - optimized for 10-minute intervals"""
                nonlocal health_check_count
                health_check_count += 1
                
                uptime_seconds = time.time() - start_time
                uptime_hours = uptime_seconds / 3600
                
                # Format uptime in human readable format
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
                    'deployment': 'render_production'
                }), 200
            
            @app.route('/status')
            def status_check():
                """Detailed status endpoint for debugging"""
                uptime_seconds = time.time() - start_time
                return jsonify({
                    'service': 'telegram-claim-bot',
                    'status': 'running',
                    'mode': 'webhook',
                    'timestamp': time.time(),
                    'start_time': start_time,
                    'uptime_seconds': uptime_seconds,
                    'health_checks_total': health_check_count,
                    'webhook_url': webhook_url,
                    'port': port,
                    'version': '1.0.0'
                }), 200
            
            # Start webhook server - simplified approach for python-telegram-bot 20.7
            import asyncio
            
            # Start the webhook using the application's built-in method
            webserver = self.application.run_webhook(
                listen="0.0.0.0",
                port=port,
                webhook_url=webhook_url
            )
            
            # Keep running
            await webserver
            
        except Exception as e:
            logger.error(f"Failed to start webhook: {e}")
            raise
    
    async def start_polling(self):
        """Start polling for development"""
        try:
            logger.info("Starting polling mode")
            await self.application.run_polling()
            
        except Exception as e:
            logger.error(f"Failed to start polling: {e}")
            raise
    
    async def handle_start_command(self, update: Update, context):
        """Handle /start command"""
        try:
            user_id = update.effective_user.id
            user_name = update.effective_user.first_name or "用户"
            
            logger.info(f"User {user_id} ({user_name}) started bot")
            
            # Check if user is registered
            is_registered = await self.user_manager.is_user_registered(user_id)
            
            if is_registered:
                message = (
                    f"欢迎回来，{user_name}！👋\n\n"
                    "你已经注册过了，可以直接使用以下功能：\n"
                    "• /claim - 提交报销申请\n"
                    "• /help - 查看帮助信息"
                )
                keyboard = KeyboardBuilder.claim_complete_keyboard()
            else:
                message = (
                    f"欢迎使用报销申请系统，{user_name}！👋\n\n"
                    "请先注册你的信息才能使用系统：\n"
                    "• /register - 注册用户信息\n"
                    "• /help - 查看帮助信息"
                )
                keyboard = KeyboardBuilder.registration_complete_keyboard()
            
            await update.message.reply_text(
                message,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"Error handling start command: {e}")
            await self._send_error_message(update, "启动命令处理失败，请稍后重试。")
    
    async def handle_help_command(self, update: Update, context):
        """Handle /help command"""
        try:
            help_message = (
                "📋 <b>报销申请系统帮助</b>\n\n"
                "<b>可用命令：</b>\n"
                "• /start - 开始使用系统\n"
                "• /register - 注册用户信息\n"
                "• /claim - 提交报销申请\n"
                "• /help - 显示此帮助信息\n\n"
                "<b>使用流程：</b>\n"
                "1. 使用 /register 注册你的信息\n"
                "2. 使用 /claim 提交报销申请\n"
                "3. 选择类别、输入金额、上传收据\n"
                "4. 确认提交申请\n\n"
                "<b>支持的报销类别：</b>\n"
                "• 🍔 Food - 餐饮费用\n"
                "• 🚗 Transportation - 交通费用\n"
                "• ✈️ Flight - 机票费用\n"
                "• 🎉 Event - 活动费用\n"
                "• 🤖 AI - AI工具费用\n"
                "• 📦 Other - 其他费用\n\n"
                "如有问题，请联系管理员。"
            )
            
            await update.message.reply_text(
                help_message,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"Error handling help command: {e}")
            await self._send_error_message(update, "帮助信息获取失败，请稍后重试。")
    
    async def handle_register_command(self, update: Update, context):
        """Handle /register command"""
        try:
            user_id = update.effective_user.id
            
            logger.info(f"User {user_id} initiated registration")
            
            # Start registration process
            result = await self.user_manager.start_registration(user_id)
            
            if result['success']:
                keyboard = None
                if result.get('next_step') == UserStateType.REGISTERING_ROLE.value:
                    keyboard = KeyboardBuilder.role_selection_keyboard()
                
                await update.message.reply_text(
                    result['message'],
                    reply_markup=keyboard
                )
            else:
                await update.message.reply_text(result['message'])
                
        except Exception as e:
            logger.error(f"Error handling register command: {e}")
            await self._send_error_message(update, "注册命令处理失败，请稍后重试。")
    
    async def handle_claim_command(self, update: Update, context):
        """Handle /claim command"""
        try:
            user_id = update.effective_user.id
            
            logger.info(f"User {user_id} initiated claim process")
            
            # Check if user is registered
            has_permission, error_msg = await self.user_manager.check_user_permission(user_id)
            
            if not has_permission:
                await update.message.reply_text(error_msg)
                return
            
            # Start claim process
            result = await self.claims_manager.start_claim_process(user_id)
            
            if result['success']:
                await update.message.reply_text(
                    result['message'],
                    reply_markup=result['keyboard']
                )
            else:
                await update.message.reply_text(result['message'])
                
        except Exception as e:
            logger.error(f"Error handling claim command: {e}")
            await self._send_error_message(update, "申请命令处理失败，请稍后重试。")
    
    async def handle_callback_query(self, update: Update, context):
        """Handle inline keyboard callbacks"""
        try:
            query = update.callback_query
            user_id = query.from_user.id
            callback_data = query.data
            
            logger.info(f"User {user_id} pressed callback: {callback_data}")
            
            # Answer callback query to remove loading state
            await query.answer()
            
            # Get current user state
            current_state, temp_data = self.state_manager.get_user_state(user_id)
            
            # Handle different callback types
            if callback_data.startswith('role_'):
                await self._handle_role_callback(query, callback_data, current_state, temp_data)
            
            elif callback_data.startswith('category_'):
                await self._handle_category_callback(query, callback_data, current_state, temp_data)
            
            elif callback_data.startswith('confirm_'):
                await self._handle_confirmation_callback(query, callback_data, current_state, temp_data)
            
            elif callback_data == 'start_claim':
                await self._handle_start_claim_callback(query)
            
            elif callback_data == 'new_claim':
                await self._handle_new_claim_callback(query)
            
            elif callback_data == 'cancel':
                await self._handle_cancel_callback(query, current_state)
            
            elif callback_data.startswith('help_'):
                await self._handle_help_callback(query, callback_data)
            
            elif callback_data.startswith('skip_'):
                await self._handle_skip_callback(query, callback_data, current_state, temp_data)
            
            else:
                logger.warning(f"Unknown callback data: {callback_data}")
                await query.edit_message_text("未知的操作，请重新开始。")
                
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            await self._send_callback_error(update.callback_query, "操作处理失败，请稍后重试。")
    
    async def handle_text_input(self, update: Update, context):
        """Handle text input from users"""
        try:
            user_id = update.effective_user.id
            text = update.message.text.strip()
            
            logger.info(f"User {user_id} sent text: {text[:50]}...")
            
            # Get current user state
            current_state, temp_data = self.state_manager.get_user_state(user_id)
            
            # Handle based on current state
            if current_state == UserStateType.REGISTERING_NAME:
                await self._handle_registration_text(update, 'name', text)
            
            elif current_state == UserStateType.REGISTERING_PHONE:
                await self._handle_registration_text(update, 'phone', text)
            
            elif current_state == UserStateType.CLAIMING_AMOUNT:
                await self._handle_claim_text(update, 'amount', text)
            
            elif current_state == UserStateType.IDLE:
                # User sent text while idle - provide guidance
                await update.message.reply_text(
                    "请使用以下命令：\n"
                    "• /register - 注册用户信息\n"
                    "• /claim - 提交报销申请\n"
                    "• /help - 查看帮助信息"
                )
            
            else:
                logger.warning(f"Unexpected text input in state {current_state}")
                await update.message.reply_text("请按照提示操作或使用 /help 查看帮助。")
                
        except Exception as e:
            logger.error(f"Error handling text input: {e}")
            await self._send_error_message(update, "文本处理失败，请稍后重试。")
    
    async def handle_photo_upload(self, update: Update, context):
        """Handle photo uploads"""
        try:
            user_id = update.effective_user.id
            
            logger.info(f"User {user_id} uploaded photo")
            
            # Get current user state
            current_state, temp_data = self.state_manager.get_user_state(user_id)
            
            if current_state != UserStateType.CLAIMING_PHOTO:
                await update.message.reply_text(
                    "请先使用 /claim 命令开始申请流程，然后按提示上传收据照片。"
                )
                return
            
            # Get photo data
            photo = update.message.photo[-1]  # Get highest resolution
            photo_file = await photo.get_file()
            photo_data = await photo_file.download_as_bytearray()
            
            # Process photo upload
            result = await self.claims_manager.process_claim_step(
                user_id, 'photo', bytes(photo_data)
            )
            
            if result['success']:
                await update.message.reply_text(
                    result['message'],
                    reply_markup=result['keyboard']
                )
            else:
                await update.message.reply_text(
                    result['message'],
                    reply_markup=result.get('keyboard')
                )
                
        except Exception as e:
            logger.error(f"Error handling photo upload: {e}")
            await self._send_error_message(update, "照片处理失败，请稍后重试。")
    
    async def handle_error(self, update: Update, context):
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
            await self._send_error_message(update, user_message)
        
        # Reset user state if error is severe
        if user_id and error_severity.value in ['high', 'critical']:
            try:
                self.state_manager.clear_user_state(user_id)
                logger.info(f"Cleared state for user {user_id} due to severe error")
            except Exception as state_error:
                logger.error(f"Failed to clear state for user {user_id}: {state_error}")
    
    # Helper methods for callback handling
    
    async def _handle_role_callback(self, query, callback_data, current_state, temp_data):
        """Handle role selection callback"""
        if current_state != UserStateType.REGISTERING_ROLE:
            await query.edit_message_text("请先使用 /register 命令开始注册。")
            return
        
        role = callback_data.replace('role_', '')
        result = await self.user_manager.process_registration_step(
            query.from_user.id, 'role', role
        )
        
        if result['success']:
            keyboard = KeyboardBuilder.claim_complete_keyboard() if result.get('user_data') else None
            await query.edit_message_text(
                result['message'],
                reply_markup=keyboard
            )
        else:
            keyboard = KeyboardBuilder.role_selection_keyboard() if result.get('show_role_keyboard') else None
            await query.edit_message_text(
                result['message'],
                reply_markup=keyboard
            )
    
    async def _handle_category_callback(self, query, callback_data, current_state, temp_data):
        """Handle category selection callback"""
        if current_state != UserStateType.CLAIMING_CATEGORY:
            await query.edit_message_text("请先使用 /claim 命令开始申请。")
            return
        
        result = await self.claims_manager.process_claim_step(
            query.from_user.id, 'category', callback_data
        )
        
        await query.edit_message_text(
            result['message'],
            reply_markup=result.get('keyboard')
        )
    
    async def _handle_confirmation_callback(self, query, callback_data, current_state, temp_data):
        """Handle confirmation callback"""
        if current_state != UserStateType.CLAIMING_CONFIRM:
            await query.edit_message_text("没有待确认的申请。")
            return
        
        result = await self.claims_manager.process_claim_step(
            query.from_user.id, 'confirm', callback_data
        )
        
        await query.edit_message_text(
            result['message'],
            reply_markup=result.get('keyboard')
        )
    
    async def _handle_start_claim_callback(self, query):
        """Handle start claim callback"""
        user_id = query.from_user.id
        
        # Check permission
        has_permission, error_msg = await self.user_manager.check_user_permission(user_id)
        
        if not has_permission:
            await query.edit_message_text(error_msg)
            return
        
        # Start claim process
        result = await self.claims_manager.start_claim_process(user_id)
        
        await query.edit_message_text(
            result['message'],
            reply_markup=result['keyboard']
        )
    
    async def _handle_new_claim_callback(self, query):
        """Handle new claim callback"""
        user_id = query.from_user.id
        
        # Check permission
        has_permission, error_msg = await self.user_manager.check_user_permission(user_id)
        
        if not has_permission:
            await query.edit_message_text(error_msg)
            return
        
        # Start new claim process
        result = await self.claims_manager.start_claim_process(user_id)
        
        await query.edit_message_text(
            result['message'],
            reply_markup=result['keyboard']
        )
    
    async def _handle_cancel_callback(self, query, current_state):
        """Handle cancel callback"""
        user_id = query.from_user.id
        
        if self.state_manager.is_user_registering(user_id):
            result = self.user_manager.cancel_registration(user_id)
            await query.edit_message_text(result['message'])
        
        elif self.state_manager.is_user_claiming(user_id):
            result = await self.claims_manager.cancel_claim_process(user_id)
            await query.edit_message_text(
                result['message'],
                reply_markup=result.get('keyboard')
            )
        
        else:
            await query.edit_message_text("没有正在进行的操作可以取消。")
    
    async def _handle_registration_text(self, update, field, text):
        """Handle text input during registration"""
        user_id = update.effective_user.id
        
        result = await self.user_manager.process_registration_step(
            user_id, field, text
        )
        
        keyboard = None
        if result.get('show_role_keyboard'):
            keyboard = KeyboardBuilder.role_selection_keyboard()
        elif result.get('user_data'):
            keyboard = KeyboardBuilder.claim_complete_keyboard()
        
        await update.message.reply_text(
            result['message'],
            reply_markup=keyboard
        )
    
    async def _handle_claim_text(self, update, field, text):
        """Handle text input during claim process"""
        user_id = update.effective_user.id
        
        result = await self.claims_manager.process_claim_step(
            user_id, field, text
        )
        
        await update.message.reply_text(
            result['message'],
            reply_markup=result.get('keyboard')
        )
    
    async def _send_error_message(self, update, message):
        """Send error message to user"""
        try:
            if update.message:
                await update.message.reply_text(f"❌ {message}")
            elif update.callback_query:
                await update.callback_query.message.reply_text(f"❌ {message}")
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
    
    async def _send_callback_error(self, query, message):
        """Send error message for callback query"""
        try:
            await query.edit_message_text(f"❌ {message}")
        except Exception as e:
            logger.error(f"Failed to send callback error: {e}")
    
    async def _handle_help_callback(self, query, callback_data):
        """Handle help request callbacks"""
        try:
            field = callback_data.replace('help_', '')
            
            from validation_helper import global_validation_helper
            help_message = global_validation_helper.handle_validation_help_request(field)
            
            # Send help message
            await query.edit_message_text(
                f"📚 {help_message}\n\n请继续输入{field}信息：",
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"Error handling help callback: {e}")
            await query.edit_message_text("❌ 获取帮助信息失败，请重试。")
    
    async def _handle_skip_callback(self, query, callback_data, current_state, temp_data):
        """Handle skip field callbacks"""
        try:
            field = callback_data.replace('skip_', '')
            user_id = query.from_user.id
            
            # Only allow skipping for certain fields in specific contexts
            if field == 'phone' and current_state == UserStateType.REGISTERING_PHONE:
                # Skip phone number - use placeholder
                self.state_manager.update_user_data(user_id, 'phone', 'N/A')
                self.state_manager.set_user_state(user_id, UserStateType.REGISTERING_ROLE)
                
                await query.edit_message_text(
                    "⏭️ 已跳过电话号码输入\n\n请选择你的身份：",
                    reply_markup=KeyboardBuilder.role_selection_keyboard()
                )
            else:
                await query.edit_message_text("❌ 此字段不能跳过，请继续输入。")
                
        except Exception as e:
            logger.error(f"Error handling skip callback: {e}")
            await query.edit_message_text("❌ 跳过操作失败，请重试。")
    
    def get_application(self) -> Application:
        """Get the telegram application instance"""
        return self.application
