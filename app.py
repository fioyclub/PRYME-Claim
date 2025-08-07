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
        if bot_instance is None:
            return "Bot not initialized", 503
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
    
    @app.route('/', methods=['GET'])
    def index():
        """Root endpoint for direct access"""
        return {"status": "OK", "message": "Pryme Claim Bot is running"}, 200
    
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
        """Application status endpoint with memory monitoring"""
        status_data = {
            'status': 'running',
            'bot_initialized': bot_instance is not None,
            'uptime_seconds': time.time() - start_time,
            'server': 'gunicorn'
        }
        
        # Add basic memory information if available
        if bot_instance is not None:
            try:
                import psutil
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                status_data['memory'] = {
                    'rss_mb': round(memory_mb, 2),
                    'available': True
                }
            except Exception as e:
                status_data['memory'] = {'error': str(e)}
        
        return jsonify(status_data), 200
    
    @app.route('/memory')
    def memory_stats():
        """Dedicated memory monitoring endpoint"""
        if bot_instance is None:
            return jsonify({'error': 'Bot not initialized'}), 503
        
        try:
            import psutil
            process = psutil.Process()
            memory_info = {
                'rss_mb': round(process.memory_info().rss / 1024 / 1024, 2),
                'available': True,
                'state_management': 'ConversationHandler (built-in)'
            }
            return jsonify(memory_info), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return app

def initialize_bot():
    """Initialize the Telegram bot instance with lazy loading"""
    global bot_instance
    
    try:
        from config import Config
        from bot_handler import TelegramBot
        from user_manager import UserManager
        from claims_manager import ClaimsManager
        from dayoff_manager import DayOffManager
        # StateManager removed - using ConversationHandler now
        from lazy_client_manager import get_lazy_client_manager
        
        logger.info("Initializing bot for Gunicorn deployment with lazy loading...")
        
        # Memory monitoring - start
        try:
            import psutil
            process = psutil.Process()
            memory_start = process.memory_info().rss / 1024 / 1024
            logger.info(f"[MEMORY] Bot initialization start: {memory_start:.2f} MB")
        except ImportError:
            memory_start = 0
            logger.warning("psutil not available, memory monitoring disabled")
        
        # Load configuration
        config = Config()
        
        # Import AdminCommands and pass it to TelegramBot
        from admin_commands import AdminCommands
        
        # Initialize lazy client manager (no Google API clients initialized yet)
        lazy_client_manager = get_lazy_client_manager(config)
        
        # Initialize managers with lazy loading (ConversationHandler manages state)
        user_manager = UserManager(lazy_client_manager)
        claims_manager = ClaimsManager(lazy_client_manager, config)
        dayoff_manager = DayOffManager(lazy_client_manager, user_manager)
        
        # Initialize AdminCommands
        admin_commands = AdminCommands(lazy_client_manager)
        
        # Initialize bot handler
        bot_instance = TelegramBot(
            token=config.TELEGRAM_BOT_TOKEN,
            user_manager=user_manager,
            claims_manager=claims_manager,
            dayoff_manager=dayoff_manager,
            admin_commands=admin_commands
        )
        
        # Note: ConversationHandler state is maintained in-memory and is not shared between workers
        # To prevent state loss during conversations, we use a single Gunicorn worker
        # See gunicorn.conf.py for worker configuration
        
        # Set webhook if URL is provided
        if config.WEBHOOK_URL:
            bot_instance.updater.bot.set_webhook(url=config.WEBHOOK_URL)
            logger.info(f"Webhook set to: {config.WEBHOOK_URL}")
        
        # Memory monitoring - end
        if memory_start > 0:
            try:
                memory_end = process.memory_info().rss / 1024 / 1024
                memory_diff = memory_end - memory_start
                logger.info(f"[MEMORY] Bot initialization end: {memory_end:.2f} MB (diff: {memory_diff:+.2f} MB)")
                
                # Force garbage collection
                import gc
                gc.collect()
                memory_after_gc = process.memory_info().rss / 1024 / 1024
                gc_freed = memory_end - memory_after_gc
                logger.info(f"[MEMORY] After GC: {memory_after_gc:.2f} MB (GC freed: {gc_freed:.2f} MB)")
                
            except Exception as e:
                logger.error(f"Error in memory monitoring: {e}")
        
        logger.info("Bot initialized successfully with lazy loading - Google API clients will be loaded on demand")
        
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
