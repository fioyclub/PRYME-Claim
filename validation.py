"""
Input validation functions for the Telegram Claim Bot.

This module provides validation functions for user inputs including
phone numbers, amounts, and photo files with comprehensive error handling.
"""

import re
import logging
from typing import Optional, Tuple, Dict, Any
from io import BytesIO
from PIL import Image

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors."""
    
    def __init__(self, message: str, field: str = None, value: Any = None):
        super().__init__(message)
        self.field = field
        self.value = value
        self.user_message = message


class ValidationResult:
    """Result of a validation operation"""
    
    def __init__(self, is_valid: bool, value: Any = None, error_message: str = None, 
                 suggestions: list = None):
        self.is_valid = is_valid
        self.value = value
        self.error_message = error_message
        self.suggestions = suggestions or []
    
    def to_tuple(self) -> Tuple[bool, Any, Optional[str]]:
        """Convert to tuple format for backward compatibility"""
        return self.is_valid, self.value, self.error_message


def validate_phone_number(phone: str) -> ValidationResult:
    """
    Validate phone number format with comprehensive error handling.
    
    Accepts Malaysian phone numbers in various formats:
    - +60123456789
    - 60123456789
    - 0123456789
    - 012-3456789
    - 012 3456 789
    
    Args:
        phone: Phone number string to validate
        
    Returns:
        ValidationResult object
    """
    try:
        if not phone or not isinstance(phone, str):
            return ValidationResult(
                is_valid=False,
                error_message="Phone number cannot be empty",
                suggestions=["Please enter your phone number", "Format example: +60123456789 or 0123456789"]
            )
        
        # Remove all spaces and dashes
        cleaned_phone = re.sub(r'[\s\-]', '', phone.strip())
        
        if not cleaned_phone:
            return ValidationResult(
                is_valid=False,
                error_message="Phone number cannot be empty",
                suggestions=["Please enter your phone number"]
            )
        
        # Check for non-digit characters (except + at start)
        if not re.match(r'^\+?\d+$', cleaned_phone):
            return ValidationResult(
                is_valid=False,
                error_message="Phone number can only contain digits and + at the beginning",
                suggestions=["Please only enter digits and + sign", "Format example: +60123456789"]
            )
        
        # Malaysian phone number patterns
        patterns = [
            (r'^\+60[1-9]\d{7,9}$', "+60xxxxxxxxx"),  # +60xxxxxxxxx (8-10 digits after +60)
            (r'^60[1-9]\d{7,9}$', "60xxxxxxxxx"),     # 60xxxxxxxxx (8-10 digits after 60)
            (r'^0[1-9]\d{7,9}$', "0xxxxxxxxx"),       # 0xxxxxxxxx (8-10 digits after 0)
        ]
        
        for pattern, format_example in patterns:
            if re.match(pattern, cleaned_phone):
                return ValidationResult(
                    is_valid=True,
                    value=cleaned_phone
                )
        
        # Provide specific error messages based on common mistakes
        if cleaned_phone.startswith('+60'):
            if len(cleaned_phone) < 11:
                error_msg = "Phone number too short, need 8-10 digits after +60"
            elif len(cleaned_phone) > 13:
                error_msg = "Phone number too long, maximum 10 digits after +60"
            else:
                error_msg = "Phone number format incorrect"
        elif cleaned_phone.startswith('60'):
            if len(cleaned_phone) < 10:
                error_msg = "Phone number too short, need 8-10 digits after 60"
            elif len(cleaned_phone) > 12:
                error_msg = "Phone number too long, maximum 10 digits after 60"
            else:
                error_msg = "Phone number format incorrect"
        elif cleaned_phone.startswith('0'):
            if len(cleaned_phone) < 9:
                error_msg = "Phone number too short, need 8-10 digits after 0"
            elif len(cleaned_phone) > 11:
                error_msg = "Phone number too long, maximum 10 digits after 0"
            else:
                error_msg = "Phone number format incorrect"
        else:
            error_msg = "Phone number must start with +60, 60 or 0"
        
        return ValidationResult(
            is_valid=False,
            error_message=error_msg,
            suggestions=[
                "Format example: +60123456789",
                "Format example: 0123456789",
                "Please ensure number length is correct"
            ]
        )
        
    except Exception as e:
        logger.error(f"Error validating phone number: {e}")
        return ValidationResult(
            is_valid=False,
            error_message="Error validating phone number, please try again",
            suggestions=["Please re-enter phone number"]
        )


# Backward compatibility function
def validate_phone_number_legacy(phone: str) -> Tuple[bool, Optional[str]]:
    """Legacy function for backward compatibility"""
    result = validate_phone_number(phone)
    return result.is_valid, result.error_message


def validate_amount(amount_str: str) -> ValidationResult:
    """
    Validate and parse amount input with comprehensive error handling.
    
    Args:
        amount_str: Amount string to validate
        
    Returns:
        ValidationResult object
    """
    try:
        if not amount_str or not isinstance(amount_str, str):
            return ValidationResult(
                is_valid=False,
                error_message="Amount cannot be empty",
                suggestions=["Please enter amount", "Format example: 50.00 or RM 100"]
            )
        
        # Remove RM prefix and whitespace
        cleaned_amount = amount_str.strip().upper()
        if cleaned_amount.startswith('RM'):
            cleaned_amount = cleaned_amount[2:].strip()
        
        if not cleaned_amount:
            return ValidationResult(
                is_valid=False,
                error_message="Please enter specific amount",
                suggestions=["Format example: 50.00", "Format example: RM 100"]
            )
        
        # Remove commas for thousands separator
        cleaned_amount = cleaned_amount.replace(',', '')
        
        # Check for invalid characters
        if not re.match(r'^\d+\.?\d*$', cleaned_amount):
            return ValidationResult(
                is_valid=False,
                error_message="Amount can only contain digits and decimal point",
                suggestions=[
                    "Please only enter digits and decimal point",
                    "Format example: 50.00",
                    "Format example: 100"
                ]
            )
        
        try:
            amount = float(cleaned_amount)
        except ValueError:
            return ValidationResult(
                is_valid=False,
                error_message="Please enter valid numeric amount",
                suggestions=[
                    "Format example: 50.00",
                    "Format example: RM 100",
                    "Please ensure only digits and decimal point"
                ]
            )
        
        if amount <= 0:
            return ValidationResult(
                is_valid=False,
                error_message="Amount must be greater than zero",
                suggestions=[
                    "Please enter amount greater than 0",
                    "Format example: 10.50"
                ]
            )
        
        if amount > 999999.99:
            return ValidationResult(
                is_valid=False,
                error_message="Amount cannot exceed RM 999,999.99",
                suggestions=[
                    "Please enter a smaller amount",
                    "For large expense claims, please contact administrator"
                ]
            )
        
        # Check for reasonable decimal places
        decimal_places = len(str(amount).split('.')[-1]) if '.' in str(amount) else 0
        if decimal_places > 2:
            amount = round(amount, 2)
        
        # Check for very small amounts
        if amount < 0.01:
            return ValidationResult(
                is_valid=False,
                error_message="Amount cannot be less than RM 0.01",
                suggestions=["Please enter at least RM 0.01"]
            )
        
        return ValidationResult(
            is_valid=True,
            value=amount
        )
        
    except Exception as e:
        logger.error(f"Error validating amount: {e}")
        return ValidationResult(
            is_valid=False,
            error_message="Error validating amount, please try again",
            suggestions=["Please re-enter amount"]
        )


# Backward compatibility function
def validate_amount_legacy(amount_str: str) -> Tuple[bool, Optional[float], Optional[str]]:
    """Legacy function for backward compatibility"""
    result = validate_amount(amount_str)
    return result.is_valid, result.value, result.error_message


def format_amount(amount: float) -> str:
    """
    Format amount for display.
    
    Args:
        amount: Amount to format
        
    Returns:
        Formatted amount string
    """
    return f"RM {amount:,.2f}"


def validate_photo_file(file_data: bytes, filename: str = None) -> ValidationResult:
    """
    Validate photo file type and size with comprehensive error handling.
    
    Args:
        file_data: Photo file data as bytes
        filename: Optional filename for additional validation
        
    Returns:
        ValidationResult object
    """
    try:
        if not file_data:
            return ValidationResult(
                is_valid=False,
                error_message="Photo file cannot be empty",
                suggestions=["Please select and upload receipt photo"]
            )
        
        # Check file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB in bytes
        file_size_mb = len(file_data) / (1024 * 1024)
        
        if len(file_data) > max_size:
            return ValidationResult(
                is_valid=False,
                error_message=f"Photo file size cannot exceed 10MB (current: {file_size_mb:.1f}MB)",
                suggestions=[
                    "Please compress image and re-upload",
                    "Use lower resolution setting on phone camera",
                    "Recommended file size: 1-5MB"
                ]
            )
        
        # Check minimum file size (1KB)
        min_size = 1024  # 1KB in bytes
        if len(file_data) < min_size:
            return ValidationResult(
                is_valid=False,
                error_message="Photo file too small, please upload valid image file",
                suggestions=[
                    "Please ensure uploaded file is complete image",
                    "Recommended minimum file size: 1KB"
                ]
            )
        
        # Validate file extension if filename is provided
        if filename:
            allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
            file_ext = filename.lower().split('.')[-1] if '.' in filename else ''
            
            if f'.{file_ext}' not in allowed_extensions:
                return ValidationResult(
                    is_valid=False,
                    error_message="Please upload valid image file format",
                    suggestions=[
                        "Supported formats: JPG, PNG, GIF, BMP, WebP",
                        "Please ensure file extension is correct",
                        f"Current file extension: {file_ext or 'None'}"
                    ]
                )
        
        # Validate image format using PIL
        try:
            # Create a copy of the data for verification
            img_data = BytesIO(file_data)
            
            with Image.open(img_data) as img:
                # Get image info before verification
                width, height = img.size
                format_name = img.format
                
                # Check image dimensions (minimum 100x100, maximum 4000x4000)
                if width < 100 or height < 100:
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Image dimensions too small (current: {width}x{height})",
                        suggestions=[
                            "Minimum size requirement: 100x100 pixels",
                            "Please use higher resolution to capture receipt photo",
                            "Ensure receipt content is clearly visible"
                        ]
                    )
                
                if width > 4000 or height > 4000:
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Image dimensions too large (current: {width}x{height})",
                        suggestions=[
                            "Maximum size limit: 4000x4000 pixels",
                            "Please compress image or use lower resolution",
                            "Recommended size: within 1000x1000 pixels"
                        ]
                    )
                
                # Verify the image can be processed
                img.verify()
                
                return ValidationResult(
                    is_valid=True,
                    value={
                        'size': len(file_data),
                        'dimensions': (width, height),
                        'format': format_name
                    }
                )
                
        except Exception as img_error:
            logger.error(f"Image validation error: {img_error}")
            
            # Provide specific error messages based on common issues
            error_str = str(img_error).lower()
            
            if 'cannot identify image file' in error_str:
                error_message = "Cannot identify image format, please ensure uploaded file is valid image"
                suggestions = [
                    "Please retake receipt photo",
                    "Ensure file is not corrupted",
                    "Try using JPG or PNG format"
                ]
            elif 'truncated' in error_str or 'incomplete' in error_str:
                error_message = "Image file incomplete or corrupted"
                suggestions = [
                    "Please re-upload image",
                    "Ensure stable network connection",
                    "Try retaking photo"
                ]
            else:
                error_message = "Image file validation failed, please upload valid image"
                suggestions = [
                    "Please retake receipt photo",
                    "Ensure using common image formats (JPG, PNG)",
                    "Check if file is complete"
                ]
            
            return ValidationResult(
                is_valid=False,
                error_message=error_message,
                suggestions=suggestions
            )
            
    except Exception as e:
        logger.error(f"Error validating photo file: {e}")
        return ValidationResult(
            is_valid=False,
            error_message="Error validating photo, please try again",
            suggestions=["Please re-upload photo"]
        )


# Backward compatibility function
def validate_photo_file_legacy(file_data: bytes, filename: str = None) -> Tuple[bool, Optional[str]]:
    """Legacy function for backward compatibility"""
    result = validate_photo_file(file_data, filename)
    return result.is_valid, result.error_message


def validate_name(name: str) -> ValidationResult:
    """
    Validate user name input with comprehensive error handling.
    
    Args:
        name: Name string to validate
        
    Returns:
        ValidationResult object
    """
    try:
        if not name or not isinstance(name, str):
            return ValidationResult(
                is_valid=False,
                error_message="Name cannot be empty",
                suggestions=["Please enter your real name"]
            )
        
        name = name.strip()
        
        if not name:
            return ValidationResult(
                is_valid=False,
                error_message="Name cannot be empty",
                suggestions=["Please enter your real name"]
            )
        
        if len(name) < 2:
            return ValidationResult(
                is_valid=False,
                error_message="Name must be at least 2 characters",
                suggestions=[
                    "Please enter complete name",
                    "Format example: Zhang San or John Doe"
                ]
            )
        
        if len(name) > 50:
            return ValidationResult(
                is_valid=False,
                error_message=f"Name cannot exceed 50 characters (current: {len(name)} characters)",
                suggestions=[
                    "Please enter shorter name",
                    "Can use common name or abbreviation"
                ]
            )
        
        # Check for excessive spaces
        if '  ' in name:  # Multiple consecutive spaces
            return ValidationResult(
                is_valid=False,
                error_message="Name cannot contain multiple consecutive spaces",
                suggestions=[
                    "Please use single space to separate first and last name",
                    "Format example: Zhang San or John Doe"
                ]
            )
        
        # Allow letters, spaces, and common punctuation for names
        if not re.match(r'^[a-zA-Z\u4e00-\u9fff\s\.\-\']+$', name):
            # Find invalid characters
            invalid_chars = re.findall(r'[^a-zA-Z\u4e00-\u9fff\s\.\-\']', name)
            invalid_chars_str = ''.join(set(invalid_chars))
            
            return ValidationResult(
                is_valid=False,
                error_message=f"Name contains invalid characters: {invalid_chars_str}",
                suggestions=[
                    "Name can only contain letters, Chinese characters, spaces, dots, hyphens and apostrophes",
                    "Format examples: Zhang San, John Doe, Mary-Jane, O'Connor"
                ]
            )
        
        # Check for names that are too short after removing spaces
        name_no_spaces = name.replace(' ', '')
        if len(name_no_spaces) < 2:
            return ValidationResult(
                is_valid=False,
                error_message="Name content too short",
                suggestions=[
                    "Please enter name with at least 2 valid characters",
                    "Cannot contain only spaces and punctuation"
                ]
            )
        
        return ValidationResult(
            is_valid=True,
            value=name
        )
        
    except Exception as e:
        logger.error(f"Error validating name: {e}")
        return ValidationResult(
            is_valid=False,
            error_message="Error validating name, please try again",
            suggestions=["Please re-enter name"]
        )


# Backward compatibility function
def validate_name_legacy(name: str) -> Tuple[bool, Optional[str]]:
    """Legacy function for backward compatibility"""
    result = validate_name(name)
    return result.is_valid, result.error_message


def sanitize_input(text: str) -> str:
    """
    Sanitize user input by removing potentially harmful characters.
    
    Args:
        text: Input text to sanitize
        
    Returns:
        Sanitized text
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Remove control characters and excessive whitespace
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    return sanitized.strip()


def validate_telegram_user_id(user_id) -> ValidationResult:
    """
    Validate Telegram user ID with comprehensive error handling.
    
    Args:
        user_id: User ID to validate
        
    Returns:
        ValidationResult object
    """
    try:
        if user_id is None:
            return ValidationResult(
                is_valid=False,
                error_message="User ID cannot be empty",
                suggestions=["Please ensure user ID is correctly obtained from Telegram"]
            )
        
        if not isinstance(user_id, int):
            # Try to convert if it's a string
            if isinstance(user_id, str) and user_id.isdigit():
                try:
                    user_id = int(user_id)
                except ValueError:
                    return ValidationResult(
                        is_valid=False,
                        error_message="User ID format invalid",
                        suggestions=["User ID must be numeric"]
                    )
            else:
                return ValidationResult(
                    is_valid=False,
                    error_message="User ID must be integer",
                    suggestions=["Please ensure user ID is valid number"]
                )
        
        if user_id <= 0:
            return ValidationResult(
                is_valid=False,
                error_message="User ID must be positive integer",
                suggestions=["Telegram user ID should be number greater than 0"]
            )
        
        # Telegram user IDs are typically large positive integers
        # But also check for reasonable bounds
        if user_id > 2**63 - 1:
            return ValidationResult(
                is_valid=False,
                error_message="User ID exceeds valid range",
                suggestions=["Please check if user ID is correct"]
            )
        
        # Check if it's a reasonable Telegram user ID (typically > 1000)
        if user_id < 1000:
            return ValidationResult(
                is_valid=False,
                error_message="User ID does not seem to be valid Telegram user ID",
                suggestions=["Telegram user IDs are typically larger numbers"]
            )
        
        return ValidationResult(
            is_valid=True,
            value=user_id
        )
        
    except Exception as e:
        logger.error(f"Error validating telegram user ID: {e}")
        return ValidationResult(
            is_valid=False,
            error_message="Error validating user ID",
            suggestions=["Please try again or contact administrator"]
        )


# Backward compatibility function
def validate_telegram_user_id_legacy(user_id) -> Tuple[bool, Optional[str]]:
    """Legacy function for backward compatibility"""
    result = validate_telegram_user_id(user_id)
    return result.is_valid, result.error_message


def get_validation_help_message(field: str) -> str:
    """
    Get help message for specific validation fields
    
    Args:
        field: Field name (phone, amount, name, photo)
        
    Returns:
        Help message string
    """
    help_messages = {
        'phone': (
            "📱 Phone Number Format Help:\n\n"
            "✅ Correct formats:\n"
            "• +60123456789\n"
            "• 0123456789\n"
            "• 012-345-6789\n"
            "• 012 345 6789\n\n"
            "❌ Incorrect formats:\n"
            "• 123456789 (missing country code or 0)\n"
            "• +60-12-345-6789 (non-standard format)"
        ),
        'amount': (
            "💰 Amount Format Help:\n\n"
            "✅ Correct formats:\n"
            "• 50\n"
            "• 50.00\n"
            "• RM 50\n"
            "• RM 1,234.56\n\n"
            "❌ Incorrect formats:\n"
            "• -50 (negative number)\n"
            "• 50.123 (more than 2 decimal places)\n"
            "• abc (non-numeric)"
        ),
        'name': (
            "👤 Name Format Help:\n\n"
            "✅ Correct formats:\n"
            "• Zhang San\n"
            "• John Doe\n"
            "• Mary-Jane\n"
            "• O'Connor\n\n"
            "❌ Incorrect formats:\n"
            "• Zhang (too short)\n"
            "• John123 (contains numbers)\n"
            "• Zhang  San (multiple spaces)"
        ),
        'photo': (
            "📷 Photo Format Help:\n\n"
            "✅ Requirements:\n"
            "• Format: JPG, PNG, GIF, BMP, WebP\n"
            "• Size: 1KB - 10MB\n"
            "• Dimensions: 100x100 - 4000x4000 pixels\n"
            "• Content clearly visible\n\n"
            "💡 Suggestions:\n"
            "• Use phone camera to capture\n"
            "• Ensure receipt content is clear\n"
            "• Avoid blurry or too dark photos"
        )
    }
    
    return help_messages.get(field, "Please follow the prompts to enter correct information format.")
