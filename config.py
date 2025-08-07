"""
Configuration module for Telegram Claim Bot
Handles environment variables and application settings
"""
import os
import json
import logging
from typing import Optional

# Configure logger
logger = logging.getLogger(__name__)

class Config:
    """Configuration class for managing environment variables"""
    
    def __init__(self):
        """Initialize configuration from environment variables"""
        # Telegram Bot Configuration
        self.TELEGRAM_BOT_TOKEN = self._get_required_env('TELEGRAM_BOT_TOKEN')
        
        # Google API Configuration - OAuth Only
        self.GOOGLE_TOKEN_JSON = self._get_required_env('GOOGLE_TOKEN_JSON')  # OAuth token required
        self.GOOGLE_SPREADSHEET_ID = self._get_required_env('GOOGLE_SPREADSHEET_ID')
        self.GOOGLE_DRIVE_FOLDER_ID = self._get_required_env('GOOGLE_DRIVE_FOLDER_ID')
        
        # Category-specific Google Drive Folder IDs
        self.AI_FOLDER_ID = self._get_required_env('AI_FOLDER_ID')
        self.EVENT_FOLDER_ID = self._get_required_env('EVENT_FOLDER_ID')
        self.FLIGHT_FOLDER_ID = self._get_required_env('FLIGHT_FOLDER_ID')
        self.FOOD_FOLDER_ID = self._get_required_env('FOOD_FOLDER_ID')
        self.OTHER_FOLDER_ID = self._get_required_env('OTHER_FOLDER_ID')
        self.RECEPTION_FOLDER_ID = self._get_required_env('RECEPTION_FOLDER_ID')
        self.TRANSPORT_FOLDER_ID = self._get_required_env('TRANSPORT_FOLDER_ID')
        
        # Admin Configuration
        self.ADMIN_IDS = self._parse_admin_ids(os.getenv('ADMIN_IDS', ''))
        
        # Deployment Configuration
        self.WEBHOOK_URL = os.getenv('WEBHOOK_URL')
        self.PORT = int(os.getenv('PORT', '8000'))
        
        # Validate Google OAuth token
        self._validate_google_token()
    
    def _get_required_env(self, key: str) -> str:
        """Get required environment variable or raise error"""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value
    
    def _validate_google_token(self):
        """Validate Google OAuth token JSON format"""
        try:
            json.loads(self.GOOGLE_TOKEN_JSON)
        except json.JSONDecodeError:
            raise ValueError("GOOGLE_TOKEN_JSON is not valid JSON")
    
    def _parse_admin_ids(self, admin_ids_str: str) -> list:
        """Parse admin IDs from comma-separated string"""
        if not admin_ids_str:
            logger.warning("No admin IDs configured. Admin commands will not be available.")
            return []
        
        try:
            # Parse comma-separated list of admin IDs
            admin_ids = [int(id_str.strip()) for id_str in admin_ids_str.split(',') if id_str.strip()]
            logger.info(f"Configured {len(admin_ids)} admin IDs")
            return admin_ids
        except ValueError as e:
            logger.error(f"Error parsing admin IDs: {e}. Format should be comma-separated integers.")
            return []
    
    def get_google_token_dict(self) -> dict:
        """Get Google OAuth token as dictionary"""
        return json.loads(self.GOOGLE_TOKEN_JSON)
    
    def get_category_folder_id(self, category: str) -> str:
        """Get Google Drive folder ID for specific category"""
        category_folder_mapping = {
            'Food': self.FOOD_FOLDER_ID,
            'Transportation': self.TRANSPORT_FOLDER_ID,
            'Flight': self.FLIGHT_FOLDER_ID,
            'Event': self.EVENT_FOLDER_ID,
            'AI': self.AI_FOLDER_ID,
            'Reception': self.RECEPTION_FOLDER_ID,
            'Other': self.OTHER_FOLDER_ID
        }
        
        folder_id = category_folder_mapping.get(category)
        if not folder_id:
            # Fallback to default folder if category not found
            return self.GOOGLE_DRIVE_FOLDER_ID
        
        return folder_id
