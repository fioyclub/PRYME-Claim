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
        
        # Add memory information if bot is initialized
        if bot_instance is not None:
            try:
                memory_info = bot_instance.state_manager.get_memory_usage()
                status_data['memory'] = memory_info
                
                # Check if memory is high and trigger cleanup
                if memory_info.get('available') and memory_info.get('rss_mb', 0) > 350:
                    cleanup_performed = bot_instance.state_manager.check_memory_and_cleanup(350.0)
                    status_data['memory']['cleanup_triggered'] = cleanup_performed
                    
            except Exception as e:
                status_data['memory'] = {'error': str(e)}
        
        return jsonify(status_data), 200
    
    @app.route('/memory')
    def memory_stats():
        """Dedicated memory monitoring endpoint"""
        if bot_instance is None:
            return jsonify({'error': 'Bot not initialized'}), 503
        
        try:
            memory_info = bot_instance.state_manager.get_memory_usage()
            return jsonify(memory_info), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/states')
    def states_info():
        """State management monitoring endpoint"""
        if bot_instance is None:
            return jsonify({'error': 'Bot not initialized'}), 503
        
        try:
            sync_status = bot_instance.state_manager.get_sync_status()
            return jsonify(sync_status), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/states/sync', methods=['POST'])
    def force_sync_states():
        """Force sync states with Google Sheets"""
        if bot_instance is None:
            return jsonify({'error': 'Bot not initialized'}), 503
        
        try:
            success = bot_instance.state_manager.force_sync_with_sheets()
            return jsonify({'success': success}), 200
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
        from state_manager import StateManager
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
        
        # Initialize lazy client manager (no Google API clients initialized yet)
        lazy_client_manager = get_lazy_client_manager(config)
        
        # Initialize managers with lazy loading and persistent state storage
        state_manager = StateManager(lazy_client_manager, cleanup_interval_minutes=5)  # Google Sheets persistence
        user_manager = UserManager(lazy_client_manager, state_manager)
        claims_manager = ClaimsManager(lazy_client_manager, state_manager, config)
        dayoff_manager = DayOffManager(lazy_client_manager, state_manager, user_manager)
        
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
