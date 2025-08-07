"""
Telegram Claim Bot - Main Application Entry Point
Integrates all components and handles application startup with webhook/polling support
"""
import os
import logging
from config import Config
from health import HealthServer
from bot_handler import TelegramBot
from user_manager import UserManager
from claims_manager import ClaimsManager
from dayoff_manager import DayOffManager
# StateManager removed - using ConversationHandler now
from sheets_client import SheetsClient
from drive_client import DriveClient

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def initialize_google_clients(config: Config):
    """Initialize Google API clients with OAuth credentials"""
    try:
        logger.info("Initializing Google API clients with OAuth credentials...")
        
        # Create token.json file from GOOGLE_TOKEN_JSON environment variable
        logger.info("Creating token.json file from GOOGLE_TOKEN_JSON environment variable")
        with open("token.json", "w") as f:
            f.write(config.GOOGLE_TOKEN_JSON)
        logger.info("token.json file created successfully")
        
        # Initialize Google Sheets client with OAuth
        sheets_client = SheetsClient(
            spreadsheet_id=config.GOOGLE_SPREADSHEET_ID
        )
        
        # Initialize Google Drive client with OAuth
        drive_client = DriveClient(
            root_folder_id=config.GOOGLE_DRIVE_FOLDER_ID
        )
        
        logger.info("Google API clients initialized successfully with OAuth credentials")
        return sheets_client, drive_client
        
    except Exception as e:
        logger.error(f"Failed to initialize Google API clients: {e}")
        raise

# This function is no longer needed as we use lazy loading and ConversationHandler
# def initialize_managers(sheets_client, drive_client, config):

def start_bot_application(config: Config):
    """Start the main bot application with lazy loading"""
    try:
        from lazy_client_manager import get_lazy_client_manager
        from admin_commands import AdminCommands
        
        # Memory monitoring - start
        try:
            import psutil
            process = psutil.Process()
            memory_start = process.memory_info().rss / 1024 / 1024
            logger.info(f"[MEMORY] Bot application start: {memory_start:.2f} MB")
        except ImportError:
            memory_start = 0
            logger.warning("psutil not available, memory monitoring disabled")
        
        # Initialize lazy client manager (no Google API clients initialized yet)
        lazy_client_manager = get_lazy_client_manager(config)
        
        # Initialize managers with lazy loading (ConversationHandler manages state)
        user_manager = UserManager(lazy_client_manager)
        claims_manager = ClaimsManager(lazy_client_manager, config)
        dayoff_manager = DayOffManager(lazy_client_manager, user_manager)
        admin_commands = AdminCommands(lazy_client_manager)
        
        # Initialize bot handler
        logger.info("Initializing Telegram bot handler with ConversationHandler...")
        bot = TelegramBot(
            token=config.TELEGRAM_BOT_TOKEN,
            user_manager=user_manager,
            claims_manager=claims_manager,
            dayoff_manager=dayoff_manager,
            admin_commands=admin_commands
        )
        
        # Memory monitoring - after bot init
        if memory_start > 0:
            try:
                memory_after_bot = process.memory_info().rss / 1024 / 1024
                bot_memory_diff = memory_after_bot - memory_start
                logger.info(f"[MEMORY] After bot init: {memory_after_bot:.2f} MB (diff: {bot_memory_diff:+.2f} MB)")
            except Exception as e:
                logger.error(f"Error in memory monitoring: {e}")
        
        logger.info("Telegram Claim Bot initialized successfully with lazy loading")
        
        # Start the bot based on deployment mode
        if config.WEBHOOK_URL:
            # Production mode with webhook (Gunicorn handles Flask server)
            logger.info(f"Setting webhook for production deployment: {config.WEBHOOK_URL}")
            logger.info("Note: Use 'gunicorn -c gunicorn.conf.py app:app' to start the server")
            bot.start_webhook(config.WEBHOOK_URL, config.PORT)
        else:
            # Development mode with polling
            logger.info("Starting polling mode for development")
            bot.start_polling()
            
    except Exception as e:
        logger.error(f"Failed to start bot application: {e}")
        raise

def main():
    """Main application entry point"""
    try:
        # Load configuration from environment variables
        logger.info("Loading application configuration...")
        config = Config()
        logger.info("Configuration loaded successfully")
        
        # Start health check server for monitoring (Render platform requirement)
        # Only start separate health server in development mode (polling)
        if not config.WEBHOOK_URL:
            logger.info("Starting health check server for development mode...")
            health_server = HealthServer()
            health_port = config.PORT + 1
            health_server.start(health_port)
            logger.info(f"Health check server started on port {health_port}")
        else:
            logger.info("Health check will be handled by webhook server in production mode")
        
        # Start the main bot application
        logger.info("Starting Telegram Claim Bot application...")
        start_bot_application(config)
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Critical error in main application: {e}")
        raise
    finally:
        logger.info("Application shutdown complete")

if __name__ == '__main__':
    # Run the main application (v13.15 - synchronous)
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        exit(1)
