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
                error_message="电话号码不能为空",
                suggestions=["请输入您的电话号码", "格式示例：+60123456789 或 0123456789"]
            )
        
        # Remove all spaces and dashes
        cleaned_phone = re.sub(r'[\s\-]', '', phone.strip())
        
        if not cleaned_phone:
            return ValidationResult(
                is_valid=False,
                error_message="电话号码不能为空",
                suggestions=["请输入您的电话号码"]
            )
        
        # Check for non-digit characters (except + at start)
        if not re.match(r'^\+?\d+$', cleaned_phone):
            return ValidationResult(
                is_valid=False,
                error_message="电话号码只能包含数字和开头的+号",
                suggestions=["请只输入数字和+号", "格式示例：+60123456789"]
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
                error_msg = "电话号码太短，+60后需要8-10位数字"
            elif len(cleaned_phone) > 13:
                error_msg = "电话号码太长，+60后最多10位数字"
            else:
                error_msg = "电话号码格式不正确"
        elif cleaned_phone.startswith('60'):
            if len(cleaned_phone) < 10:
                error_msg = "电话号码太短，60后需要8-10位数字"
            elif len(cleaned_phone) > 12:
                error_msg = "电话号码太长，60后最多10位数字"
            else:
                error_msg = "电话号码格式不正确"
        elif cleaned_phone.startswith('0'):
            if len(cleaned_phone) < 9:
                error_msg = "电话号码太短，0后需要8-10位数字"
            elif len(cleaned_phone) > 11:
                error_msg = "电话号码太长，0后最多10位数字"
            else:
                error_msg = "电话号码格式不正确"
        else:
            error_msg = "电话号码必须以+60、60或0开头"
        
        return ValidationResult(
            is_valid=False,
            error_message=error_msg,
            suggestions=[
                "格式示例：+60123456789",
                "格式示例：0123456789",
                "请确保号码长度正确"
            ]
        )
        
    except Exception as e:
        logger.error(f"Error validating phone number: {e}")
        return ValidationResult(
            is_valid=False,
            error_message="电话号码验证时出现错误，请重试",
            suggestions=["请重新输入电话号码"]
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
                error_message="金额不能为空",
                suggestions=["请输入金额", "格式示例：50.00 或 RM 100"]
            )
        
        # Remove RM prefix and whitespace
        cleaned_amount = amount_str.strip().upper()
        if cleaned_amount.startswith('RM'):
            cleaned_amount = cleaned_amount[2:].strip()
        
        if not cleaned_amount:
            return ValidationResult(
                is_valid=False,
                error_message="请输入具体金额",
                suggestions=["格式示例：50.00", "格式示例：RM 100"]
            )
        
        # Remove commas for thousands separator
        cleaned_amount = cleaned_amount.replace(',', '')
        
        # Check for invalid characters
        if not re.match(r'^\d+\.?\d*$', cleaned_amount):
            return ValidationResult(
                is_valid=False,
                error_message="金额只能包含数字和小数点",
                suggestions=[
                    "请只输入数字和小数点",
                    "格式示例：50.00",
                    "格式示例：100"
                ]
            )
        
        try:
            amount = float(cleaned_amount)
        except ValueError:
            return ValidationResult(
                is_valid=False,
                error_message="请输入有效的数字金额",
                suggestions=[
                    "格式示例：50.00",
                    "格式示例：RM 100",
                    "请确保只包含数字和小数点"
                ]
            )
        
        if amount <= 0:
            return ValidationResult(
                is_valid=False,
                error_message="金额必须大于零",
                suggestions=[
                    "请输入大于0的金额",
                    "格式示例：10.50"
                ]
            )
        
        if amount > 999999.99:
            return ValidationResult(
                is_valid=False,
                error_message="金额不能超过 RM 999,999.99",
                suggestions=[
                    "请输入较小的金额",
                    "如需申请大额报销，请联系管理员"
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
                error_message="金额不能小于 RM 0.01",
                suggestions=["请输入至少 RM 0.01 的金额"]
            )
        
        return ValidationResult(
            is_valid=True,
            value=amount
        )
        
    except Exception as e:
        logger.error(f"Error validating amount: {e}")
        return ValidationResult(
            is_valid=False,
            error_message="金额验证时出现错误，请重试",
            suggestions=["请重新输入金额"]
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
                error_message="照片文件不能为空",
                suggestions=["请选择并上传收据照片"]
            )
        
        # Check file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB in bytes
        file_size_mb = len(file_data) / (1024 * 1024)
        
        if len(file_data) > max_size:
            return ValidationResult(
                is_valid=False,
                error_message=f"照片文件大小不能超过 10MB（当前：{file_size_mb:.1f}MB）",
                suggestions=[
                    "请压缩图片后重新上传",
                    "可以使用手机相机的较低分辨率设置",
                    "建议文件大小在 1-5MB 之间"
                ]
            )
        
        # Check minimum file size (1KB)
        min_size = 1024  # 1KB in bytes
        if len(file_data) < min_size:
            return ValidationResult(
                is_valid=False,
                error_message="照片文件太小，请上传有效的图片文件",
                suggestions=[
                    "请确保上传的是完整的图片文件",
                    "建议文件大小至少 1KB"
                ]
            )
        
        # Validate file extension if filename is provided
        if filename:
            allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
            file_ext = filename.lower().split('.')[-1] if '.' in filename else ''
            
            if f'.{file_ext}' not in allowed_extensions:
                return ValidationResult(
                    is_valid=False,
                    error_message="请上传有效的图片文件格式",
                    suggestions=[
                        "支持的格式：JPG, PNG, GIF, BMP, WebP",
                        "请确保文件扩展名正确",
                        f"当前文件扩展名：{file_ext or '无'}"
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
                        error_message=f"图片尺寸太小（当前：{width}x{height}）",
                        suggestions=[
                            "最小尺寸要求：100x100 像素",
                            "请使用更高分辨率拍摄收据照片",
                            "确保收据内容清晰可见"
                        ]
                    )
                
                if width > 4000 or height > 4000:
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"图片尺寸太大（当前：{width}x{height}）",
                        suggestions=[
                            "最大尺寸限制：4000x4000 像素",
                            "请压缩图片或使用较低分辨率",
                            "建议尺寸：1000x1000 像素以内"
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
                error_message = "无法识别图片格式，请确保上传的是有效图片文件"
                suggestions = [
                    "请重新拍摄收据照片",
                    "确保文件没有损坏",
                    "尝试使用 JPG 或 PNG 格式"
                ]
            elif 'truncated' in error_str or 'incomplete' in error_str:
                error_message = "图片文件不完整或已损坏"
                suggestions = [
                    "请重新上传图片",
                    "确保网络连接稳定",
                    "尝试重新拍摄照片"
                ]
            else:
                error_message = "图片文件验证失败，请上传有效的图片"
                suggestions = [
                    "请重新拍摄收据照片",
                    "确保使用常见的图片格式（JPG, PNG）",
                    "检查文件是否完整"
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
            error_message="照片验证时出现错误，请重试",
            suggestions=["请重新上传照片"]
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
                error_message="姓名不能为空",
                suggestions=["请输入您的真实姓名"]
            )
        
        name = name.strip()
        
        if not name:
            return ValidationResult(
                is_valid=False,
                error_message="姓名不能为空",
                suggestions=["请输入您的真实姓名"]
            )
        
        if len(name) < 2:
            return ValidationResult(
                is_valid=False,
                error_message="姓名至少需要2个字符",
                suggestions=[
                    "请输入完整的姓名",
                    "格式示例：张三 或 John Doe"
                ]
            )
        
        if len(name) > 50:
            return ValidationResult(
                is_valid=False,
                error_message=f"姓名不能超过50个字符（当前：{len(name)}个字符）",
                suggestions=[
                    "请输入较短的姓名",
                    "可以使用常用名或简称"
                ]
            )
        
        # Check for excessive spaces
        if '  ' in name:  # Multiple consecutive spaces
            return ValidationResult(
                is_valid=False,
                error_message="姓名中不能包含多个连续空格",
                suggestions=[
                    "请使用单个空格分隔姓和名",
                    "格式示例：张 三 或 John Doe"
                ]
            )
        
        # Allow letters, spaces, and common punctuation for names
        if not re.match(r'^[a-zA-Z\u4e00-\u9fff\s\.\-\']+$', name):
            # Find invalid characters
            invalid_chars = re.findall(r'[^a-zA-Z\u4e00-\u9fff\s\.\-\']', name)
            invalid_chars_str = ''.join(set(invalid_chars))
            
            return ValidationResult(
                is_valid=False,
                error_message=f"姓名包含无效字符：{invalid_chars_str}",
                suggestions=[
                    "姓名只能包含字母、中文字符、空格、点号、连字符和撇号",
                    "格式示例：张三、John Doe、Mary-Jane、O'Connor"
                ]
            )
        
        # Check for names that are too short after removing spaces
        name_no_spaces = name.replace(' ', '')
        if len(name_no_spaces) < 2:
            return ValidationResult(
                is_valid=False,
                error_message="姓名内容太短",
                suggestions=[
                    "请输入至少2个有效字符的姓名",
                    "不能只包含空格和标点符号"
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
            error_message="姓名验证时出现错误，请重试",
            suggestions=["请重新输入姓名"]
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
                error_message="用户ID不能为空",
                suggestions=["请确保从 Telegram 正确获取用户ID"]
            )
        
        if not isinstance(user_id, int):
            # Try to convert if it's a string
            if isinstance(user_id, str) and user_id.isdigit():
                try:
                    user_id = int(user_id)
                except ValueError:
                    return ValidationResult(
                        is_valid=False,
                        error_message="用户ID格式无效",
                        suggestions=["用户ID必须是数字"]
                    )
            else:
                return ValidationResult(
                    is_valid=False,
                    error_message="用户ID必须是整数",
                    suggestions=["请确保用户ID是有效的数字"]
                )
        
        if user_id <= 0:
            return ValidationResult(
                is_valid=False,
                error_message="用户ID必须是正整数",
                suggestions=["Telegram 用户ID应该是大于0的数字"]
            )
        
        # Telegram user IDs are typically large positive integers
        # But also check for reasonable bounds
        if user_id > 2**63 - 1:
            return ValidationResult(
                is_valid=False,
                error_message="用户ID超出有效范围",
                suggestions=["请检查用户ID是否正确"]
            )
        
        # Check if it's a reasonable Telegram user ID (typically > 1000)
        if user_id < 1000:
            return ValidationResult(
                is_valid=False,
                error_message="用户ID似乎不是有效的 Telegram 用户ID",
                suggestions=["Telegram 用户ID通常是较大的数字"]
            )
        
        return ValidationResult(
            is_valid=True,
            value=user_id
        )
        
    except Exception as e:
        logger.error(f"Error validating telegram user ID: {e}")
        return ValidationResult(
            is_valid=False,
            error_message="用户ID验证时出现错误",
            suggestions=["请重试或联系管理员"]
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
            "📱 电话号码格式帮助：\n\n"
            "✅ 正确格式：\n"
            "• +60123456789\n"
            "• 0123456789\n"
            "• 012-345-6789\n"
            "• 012 345 6789\n\n"
            "❌ 错误格式：\n"
            "• 123456789（缺少国家代码或0）\n"
            "• +60-12-345-6789（格式不标准）"
        ),
        'amount': (
            "💰 金额格式帮助：\n\n"
            "✅ 正确格式：\n"
            "• 50\n"
            "• 50.00\n"
            "• RM 50\n"
            "• RM 1,234.56\n\n"
            "❌ 错误格式：\n"
            "• -50（负数）\n"
            "• 50.123（超过2位小数）\n"
            "• abc（非数字）"
        ),
        'name': (
            "👤 姓名格式帮助：\n\n"
            "✅ 正确格式：\n"
            "• 张三\n"
            "• John Doe\n"
            "• Mary-Jane\n"
            "• O'Connor\n\n"
            "❌ 错误格式：\n"
            "• 张（太短）\n"
            "• John123（包含数字）\n"
            "• 张  三（多个空格）"
        ),
        'photo': (
            "📷 照片格式帮助：\n\n"
            "✅ 要求：\n"
            "• 格式：JPG, PNG, GIF, BMP, WebP\n"
            "• 大小：1KB - 10MB\n"
            "• 尺寸：100x100 - 4000x4000 像素\n"
            "• 内容清晰可见\n\n"
            "💡 建议：\n"
            "• 使用手机相机拍摄\n"
            "• 确保收据内容清晰\n"
            "• 避免模糊或过暗的照片"
        )
    }
    
    return help_messages.get(field, "请按照提示输入正确的信息格式。")