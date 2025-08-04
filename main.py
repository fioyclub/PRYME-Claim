"""
Telegram Claim Bot - Main Application Entry Point
Integrates all components and handles application startup with webhook/polling support
"""
import os
import logging
import asyncio
from config import Config
from health import HealthServer
from bot_handler import TelegramBot
from user_manager import UserManager
from claims_manager import ClaimsManager
from state_manager import StateManager
from sheets_client import SheetsClient
from drive_client import DriveClient

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def initialize_google_clients(config: Config):
    """Initialize Google API clients with proper error handling"""
    try:
        logger.info("Initializing Google API clients...")
        
        # Initialize Google Sheets client
        sheets_client = SheetsClient(
            credentials_json=config.GOOGLE_CREDENTIALS_JSON,
            spreadsheet_id=config.GOOGLE_SPREADSHEET_ID
        )
        
        # Initialize Google Drive client
        drive_client = DriveClient(
            credentials_json=config.GOOGLE_CREDENTIALS_JSON,
            root_folder_id=config.GOOGLE_DRIVE_FOLDER_ID
        )
        
        logger.info("Google API clients initialized successfully")
        return sheets_client, drive_client
        
    except Exception as e:
        logger.error(f"Failed to initialize Google API clients: {e}")
        raise

async def initialize_managers(sheets_client, drive_client):
    """Initialize application managers"""
    try:
        logger.info("Initializing application managers...")
        
        # Initialize state manager
        state_manager = StateManager()
        
        # Initialize user manager
        user_manager = UserManager(sheets_client, state_manager)
        
        # Initialize claims manager
        claims_manager = ClaimsManager(sheets_client, drive_client, state_manager)
        
        logger.info("Application managers initialized successfully")
        return state_manager, user_manager, claims_manager
        
    except Exception as e:
        logger.error(f"Failed to initialize managers: {e}")
        raise

async def start_bot_application(config: Config):
    """Start the main bot application"""
    try:
        # Initialize Google API clients
        sheets_client, drive_client = await initialize_google_clients(config)
        
        # Initialize managers
        state_manager, user_manager, claims_manager = await initialize_managers(
            sheets_client, drive_client
        )
        
        # Initialize bot handler
        logger.info("Initializing Telegram bot handler...")
        bot = TelegramBot(
            token=config.TELEGRAM_BOT_TOKEN,
            user_manager=user_manager,
            claims_manager=claims_manager,
            state_manager=state_manager
        )
        
        logger.info("Telegram Claim Bot initialized successfully")
        
        # Start the bot based on deployment mode
        if config.WEBHOOK_URL:
            # Production mode with webhook
            logger.info(f"Starting webhook mode on {config.WEBHOOK_URL}:{config.PORT}")
            await bot.start_webhook(config.WEBHOOK_URL, config.PORT)
        else:
            # Development mode with polling
            logger.info("Starting polling mode for development")
            await bot.start_polling()
            
    except Exception as e:
        logger.error(f"Failed to start bot application: {e}")
        raise

async def main():
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
        await start_bot_application(config)
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Critical error in main application: {e}")
        raise
    finally:
        logger.info("Application shutdown complete")

if __name__ == '__main__':
    # Run the main application
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        exit(1)
