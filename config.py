"""
Configuration module for Telegram Claim Bot
Handles environment variables and application settings
"""
import os
import json
from typing import Optional

class Config:
    """Configuration class for managing environment variables"""
    
    def __init__(self):
        """Initialize configuration from environment variables"""
        print("[CONFIG DEBUG] Starting Config initialization...")
        
        # Telegram Bot Configuration
        self.TELEGRAM_BOT_TOKEN = self._get_required_env('TELEGRAM_BOT_TOKEN')
        print(f"[CONFIG DEBUG] TELEGRAM_BOT_TOKEN loaded: {bool(self.TELEGRAM_BOT_TOKEN)}")
        
        # Google API Configuration - OAuth Only
        self.GOOGLE_TOKEN_JSON = self._get_required_env('GOOGLE_TOKEN_JSON')  # OAuth token required
        self.GOOGLE_SPREADSHEET_ID = self._get_required_env('GOOGLE_SPREADSHEET_ID')
        self.GOOGLE_DRIVE_FOLDER_ID = self._get_required_env('GOOGLE_DRIVE_FOLDER_ID')
        # Debug: Check ADMIN_IDS environment variable
        admin_ids_env = os.getenv('ADMIN_IDS', '')
        print(f"[CONFIG DEBUG] ADMIN_IDS env var: {repr(admin_ids_env)}")
        
        try:
            self.ADMIN_IDS = [int(id.strip()) for id in admin_ids_env.split(',') if id.strip()]
            print(f"[CONFIG DEBUG] Parsed ADMIN_IDS: {self.ADMIN_IDS}")
        except Exception as e:
            print(f"[CONFIG DEBUG] Error parsing ADMIN_IDS: {e}")
            self.ADMIN_IDS = []
        
        # Category-specific Google Drive Folder IDs
        self.AI_FOLDER_ID = self._get_required_env('AI_FOLDER_ID')
        self.EVENT_FOLDER_ID = self._get_required_env('EVENT_FOLDER_ID')
        self.FLIGHT_FOLDER_ID = self._get_required_env('FLIGHT_FOLDER_ID')
        self.FOOD_FOLDER_ID = self._get_required_env('FOOD_FOLDER_ID')
        self.OTHER_FOLDER_ID = self._get_required_env('OTHER_FOLDER_ID')
        self.RECEPTION_FOLDER_ID = self._get_required_env('RECEPTION_FOLDER_ID')
        self.TRANSPORT_FOLDER_ID = self._get_required_env('TRANSPORT_FOLDER_ID')
        
        # Deployment Configuration
        self.WEBHOOK_URL = os.getenv('WEBHOOK_URL')
        self.PORT = int(os.getenv('PORT', '8000'))
        
        # Validate Google OAuth token
        self._validate_google_token()
        
        print(f"[CONFIG DEBUG] Config initialization completed. ADMIN_IDS: {getattr(self, 'ADMIN_IDS', 'NOT_SET')}")
        print(f"[CONFIG DEBUG] Config object attributes: {[attr for attr in dir(self) if not attr.startswith('_')]}")
    
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
