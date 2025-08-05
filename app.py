"""
Flask WSGI Application for Telegram Claim Bot
Separates Flask app from bot logic for Gunicorn deployment
"""

import os
import logging
import time
from flask import Flask, request, jsonify
from telegram import Update

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variables for bot instance and app state
bot_instance = None
start_time = time.time()
health_check_count = 0

def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)
    
    @app.route('/health', methods=['GET', 'HEAD'])
    def health():
        """Simple health check endpoint for uptime monitoring"""
        return "OK", 200
    
    @app.route('/health/detailed')
    def health_detailed():
        """Detailed health check endpoint for monitoring"""
        global health_check_count
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
            'deployment': 'render_production_gunicorn',
            'telegram_bot_version': '13.15',
            'wsgi_server': 'gunicorn'
        }), 200
    
    @app.route('/', methods=['POST'])
    def webhook():
        """Handle incoming webhook updates from Telegram"""
        try:
            if not bot_instance:
                logger.error("Bot instance not initialized")
                return 'Bot not ready', 503
            
            update_data = request.get_json()
            if update_data:
                # Create update object and process it
                update = Update.de_json(update_data, bot_instance.updater.bot)
                bot_instance.dispatcher.process_update(update)
            
            return '', 200
        except Exception as e:
            logger.error(f"Webhook processing error: {e}")
            return '', 500
    
    @app.route('/status')
    def status():
        """Application status endpoint"""
        return jsonify({
            'status': 'running',
            'bot_initialized': bot_instance is not None,
            'uptime_seconds': time.time() - start_time,
            'server': 'gunicorn'
        }), 200
    
    return app

def initialize_bot():
    """Initialize the Telegram bot instance"""
    global bot_instance
    
    try:
        from config import Config
        from bot_handler import TelegramBot
        from user_manager import UserManager
        from claims_manager import ClaimsManager
        from dayoff_manager import DayOffManager
        from state_manager import StateManager
        from sheets_client import SheetsClient
        from drive_client import DriveClient
        
        logger.info("Initializing bot for Gunicorn deployment...")
        
        # Load configuration
        config = Config()
        
        # Create token.json file from environment variable
        with open("token.json", "w") as f:
            f.write(config.GOOGLE_TOKEN_JSON)
        
        # Initialize Google API clients
        sheets_client = SheetsClient(spreadsheet_id=config.GOOGLE_SPREADSHEET_ID)
        drive_client = DriveClient(root_folder_id=config.GOOGLE_DRIVE_FOLDER_ID)
        
        # Initialize managers
        state_manager = StateManager()
        user_manager = UserManager(sheets_client, state_manager)
        claims_manager = ClaimsManager(sheets_client, drive_client, state_manager, config)
        dayoff_manager = DayOffManager(sheets_client, state_manager, user_manager)
        
        # Initialize bot handler
        bot_instance = TelegramBot(
            token=config.TELEGRAM_BOT_TOKEN,
            user_manager=user_manager,
            claims_manager=claims_manager,
            dayoff_manager=dayoff_manager,
            state_manager=state_manager
        )
        
        # Set webhook if URL is provided
        if config.WEBHOOK_URL:
            bot_instance.updater.bot.set_webhook(url=config.WEBHOOK_URL)
            logger.info(f"Webhook set to: {config.WEBHOOK_URL}")
        
        logger.info("Bot initialized successfully for Gunicorn")
        
    except Exception as e:
        logger.error(f"Failed to initialize bot: {e}")
        raise

# Create Flask app
app = create_app()

# Initialize bot when module is imported
if __name__ != '__main__':
    # This runs when imported by Gunicorn
    initialize_bot()

if __name__ == '__main__':
    # This runs when executed directly (for testing)
    initialize_bot()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)), debug=False)