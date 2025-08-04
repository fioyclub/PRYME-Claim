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
        # Telegram Bot Configuration
        self.TELEGRAM_BOT_TOKEN = self._get_required_env('TELEGRAM_BOT_TOKEN')
        
        # Google API Configuration - OAuth Only
        self.GOOGLE_TOKEN_JSON = self._get_required_env('GOOGLE_TOKEN_JSON')  # OAuth token required
        self.GOOGLE_SPREADSHEET_ID = self._get_required_env('GOOGLE_SPREADSHEET_ID')
        self.GOOGLE_DRIVE_FOLDER_ID = self._get_required_env('GOOGLE_DRIVE_FOLDER_ID')
        
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
    
    def get_google_token_dict(self) -> dict:
        """Get Google OAuth token as dictionary"""
        return json.loads(self.GOOGLE_TOKEN_JSON)
