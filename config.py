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
        
        # Google API Configuration
        # Support both Service Account (legacy) and OAuth Token (new)
        self.GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')  # Optional now
        self.GOOGLE_TOKEN_JSON = os.getenv('GOOGLE_TOKEN_JSON')  # New OAuth token
        self.GOOGLE_SPREADSHEET_ID = self._get_required_env('GOOGLE_SPREADSHEET_ID')
        self.GOOGLE_DRIVE_FOLDER_ID = self._get_required_env('GOOGLE_DRIVE_FOLDER_ID')
        
        # Deployment Configuration
        self.WEBHOOK_URL = os.getenv('WEBHOOK_URL')
        self.PORT = int(os.getenv('PORT', '8000'))
        
        # Validate Google credentials
        self._validate_google_credentials()
    
    def _get_required_env(self, key: str) -> str:
        """Get required environment variable or raise error"""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value
    
    def _validate_google_credentials(self):
        """Validate Google credentials"""
        if self.GOOGLE_TOKEN_JSON:
            # Validate OAuth token JSON format
            try:
                json.loads(self.GOOGLE_TOKEN_JSON)
            except json.JSONDecodeError:
                raise ValueError("GOOGLE_TOKEN_JSON is not valid JSON")
        elif self.GOOGLE_CREDENTIALS_JSON:
            # Validate Service Account JSON format (legacy)
            try:
                json.loads(self.GOOGLE_CREDENTIALS_JSON)
            except json.JSONDecodeError:
                raise ValueError("GOOGLE_CREDENTIALS_JSON is not valid JSON")
        else:
            raise ValueError("Either GOOGLE_TOKEN_JSON or GOOGLE_CREDENTIALS_JSON must be provided")
    
    def get_google_credentials_dict(self) -> dict:
        """Get Google credentials as dictionary (legacy method)"""
        if self.GOOGLE_CREDENTIALS_JSON:
            return json.loads(self.GOOGLE_CREDENTIALS_JSON)
        else:
            raise ValueError("GOOGLE_CREDENTIALS_JSON not available")
    
    def get_google_token_dict(self) -> dict:
        """Get Google OAuth token as dictionary"""
        if self.GOOGLE_TOKEN_JSON:
            return json.loads(self.GOOGLE_TOKEN_JSON)
        else:
            raise ValueError("GOOGLE_TOKEN_JSON not available")
    
    def use_oauth_credentials(self) -> bool:
        """Check if we should use OAuth credentials instead of Service Account"""
        return bool(self.GOOGLE_TOKEN_JSON)
