"""
Data models for the Telegram Claim Bot.

This module defines the core data structures used throughout the application,
including user registration, claims, and user state management.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, Optional
import json
from enum import Enum


class UserRole(Enum):
    """User roles in the system."""
    STAFF = "Staff"
    MANAGER = "Manager"
    ADMIN = "Admin"


class ClaimCategory(Enum):
    """Available claim categories."""
    FOOD = "Food"
    TRANSPORTATION = "Transportation"
    FLIGHT = "Flight"
    EVENT = "Event"
    AI = "AI"
    OTHER = "Other"


class ClaimStatus(Enum):
    """Claim processing status."""
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class UserStateType(Enum):
    """User conversation states."""
    IDLE = "IDLE"
    REGISTERING_NAME = "REGISTERING_NAME"
    REGISTERING_PHONE = "REGISTERING_PHONE"
    REGISTERING_ROLE = "REGISTERING_ROLE"
    CLAIMING_CATEGORY = "CLAIMING_CATEGORY"
    CLAIMING_AMOUNT = "CLAIMING_AMOUNT"
    CLAIMING_PHOTO = "CLAIMING_PHOTO"
    CLAIMING_CONFIRM = "CLAIMING_CONFIRM"


@dataclass
class UserRegistration:
    """User registration data model."""
    telegram_user_id: int
    name: str
    phone: str
    role: UserRole
    register_date: datetime
    
    def __post_init__(self):
        """Validate data after initialization."""
        if not isinstance(self.telegram_user_id, int) or self.telegram_user_id <= 0:
            raise ValueError("telegram_user_id must be a positive integer")
        
        if not self.name or not self.name.strip():
            raise ValueError("name cannot be empty")
        
        if not self.phone or not self.phone.strip():
            raise ValueError("phone cannot be empty")
        
        if isinstance(self.role, str):
            self.role = UserRole(self.role)
        
        if not isinstance(self.register_date, datetime):
            raise ValueError("register_date must be a datetime object")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'telegram_user_id': self.telegram_user_id,
            'name': self.name,
            'phone': self.phone,
            'role': self.role.value,
            'register_date': self.register_date.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserRegistration':
        """Create instance from dictionary."""
        return cls(
            telegram_user_id=data['telegram_user_id'],
            name=data['name'],
            phone=data['phone'],
            role=UserRole(data['role']),
            register_date=datetime.fromisoformat(data['register_date'])
        )
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'UserRegistration':
        """Create instance from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class Claim:
    """Expense claim data model."""
    date: datetime
    category: ClaimCategory
    amount: float
    receipt_link: str
    submitted_by: int
    status: ClaimStatus = ClaimStatus.PENDING
    
    def __post_init__(self):
        """Validate data after initialization."""
        if not isinstance(self.date, datetime):
            raise ValueError("date must be a datetime object")
        
        if isinstance(self.category, str):
            self.category = ClaimCategory(self.category)
        
        if not isinstance(self.amount, (int, float)) or self.amount <= 0:
            raise ValueError("amount must be a positive number")
        
        if not self.receipt_link or not self.receipt_link.strip():
            raise ValueError("receipt_link cannot be empty")
        
        if not isinstance(self.submitted_by, int) or self.submitted_by <= 0:
            raise ValueError("submitted_by must be a positive integer")
        
        if isinstance(self.status, str):
            self.status = ClaimStatus(self.status)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'date': self.date.isoformat(),
            'category': self.category.value,
            'amount': self.amount,
            'receipt_link': self.receipt_link,
            'submitted_by': self.submitted_by,
            'status': self.status.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Claim':
        """Create instance from dictionary."""
        return cls(
            date=datetime.fromisoformat(data['date']),
            category=ClaimCategory(data['category']),
            amount=float(data['amount']),
            receipt_link=data['receipt_link'],
            submitted_by=data['submitted_by'],
            status=ClaimStatus(data.get('status', 'Pending'))
        )
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Claim':
        """Create instance from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class UserState:
    """User conversation state data model."""
    user_id: int
    current_state: UserStateType
    temp_data: Dict[str, Any]
    last_updated: datetime
    
    def __post_init__(self):
        """Validate data after initialization."""
        if not isinstance(self.user_id, int) or self.user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        
        if isinstance(self.current_state, str):
            self.current_state = UserStateType(self.current_state)
        
        if self.temp_data is None:
            self.temp_data = {}
        
        if not isinstance(self.temp_data, dict):
            raise ValueError("temp_data must be a dictionary")
        
        if not isinstance(self.last_updated, datetime):
            raise ValueError("last_updated must be a datetime object")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'user_id': self.user_id,
            'current_state': self.current_state.value,
            'temp_data': self.temp_data,
            'last_updated': self.last_updated.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserState':
        """Create instance from dictionary."""
        return cls(
            user_id=data['user_id'],
            current_state=UserStateType(data['current_state']),
            temp_data=data.get('temp_data', {}),
            last_updated=datetime.fromisoformat(data['last_updated'])
        )
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'UserState':
        """Create instance from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    def update_temp_data(self, key: str, value: Any) -> None:
        """Update temporary data and timestamp."""
        self.temp_data[key] = value
        self.last_updated = datetime.now()
    
    def clear_temp_data(self) -> None:
        """Clear temporary data and update timestamp."""
        self.temp_data.clear()
        self.last_updated = datetime.now()