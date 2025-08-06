"""
Keyboard Builder for Telegram Bot Interface Components

This module provides the KeyboardBuilder class that generates various inline keyboards
for the Telegram Claim Bot, including role selection, claim categories, and confirmation dialogs.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Tuple


class KeyboardBuilder:
    """
    Builder class for creating inline keyboards used throughout the Telegram bot interface.
    All user interactions use inline keyboards to provide a consistent and intuitive experience.
    """

    @staticmethod
    def role_selection_keyboard() -> InlineKeyboardMarkup:
        """
        Create inline keyboard for user role selection during registration.
        
        Returns:
            InlineKeyboardMarkup: Keyboard with Staff, Manager, Ambassador options
        """
        keyboard = [
            [InlineKeyboardButton("Staff", callback_data="role_staff")],
            [InlineKeyboardButton("Manager", callback_data="role_manager")],
            [InlineKeyboardButton("Ambassador", callback_data="role_ambassador")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def claim_categories_keyboard() -> InlineKeyboardMarkup:
        """
        Create inline keyboard for expense claim category selection.
        
        Returns:
            InlineKeyboardMarkup: Keyboard with all expense categories and emojis in 2-column layout
        """
        keyboard = [
            [
                InlineKeyboardButton("Food 🍔", callback_data="category_food"),
                InlineKeyboardButton("Transportation 🚗", callback_data="category_transportation")
            ],
            [
                InlineKeyboardButton("Flight ✈️", callback_data="category_flight"),
                InlineKeyboardButton("Event 🎉", callback_data="category_event")
            ],
            [
                InlineKeyboardButton("AI 🤖", callback_data="category_ai"),
                InlineKeyboardButton("Reception 🎪", callback_data="category_reception")
            ],
            [
                InlineKeyboardButton("Other 📦", callback_data="category_other")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def confirmation_keyboard() -> InlineKeyboardMarkup:
        """
        Create inline keyboard for confirmation dialogs.
        
        Returns:
            InlineKeyboardMarkup: Keyboard with Yes/No confirmation options
        """
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data="confirm_yes"),
                InlineKeyboardButton("❌ Cancel", callback_data="confirm_no")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def registration_complete_keyboard() -> InlineKeyboardMarkup:
        """
        Create inline keyboard shown after successful registration.
        
        Returns:
            InlineKeyboardMarkup: Keyboard with option to start making claims
        """
        keyboard = [
            [InlineKeyboardButton("Start Claim Process 💰", callback_data="start_claim")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def register_now_keyboard() -> InlineKeyboardMarkup:
        """
        Create inline keyboard for unregistered users in /start command.
        
        Returns:
            InlineKeyboardMarkup: Keyboard with register now button
        """
        keyboard = [
            [InlineKeyboardButton("Register NOW 📝", callback_data="register_now")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def start_claim_keyboard() -> InlineKeyboardMarkup:
        """
        Create inline keyboard for registered users in /start command.
        
        Returns:
            InlineKeyboardMarkup: Keyboard with start claim button
        """
        keyboard = [
            [InlineKeyboardButton("Start Claim Process 💰", callback_data="start_claim")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def claim_complete_keyboard() -> InlineKeyboardMarkup:
        """
        Create inline keyboard shown after successful claim submission.
        
        Returns:
            InlineKeyboardMarkup: Keyboard with option for new claim
        """
        keyboard = [
            [InlineKeyboardButton("Submit New Claim 📝", callback_data="new_claim")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def back_keyboard() -> InlineKeyboardMarkup:
        """
        Create inline keyboard with back button for navigation.
        
        Returns:
            InlineKeyboardMarkup: Keyboard with back button
        """
        keyboard = [
            [InlineKeyboardButton("⬅️ Back", callback_data="back")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def cancel_keyboard() -> InlineKeyboardMarkup:
        """
        Create inline keyboard with cancel button for ongoing processes.
        
        Returns:
            InlineKeyboardMarkup: Keyboard with cancel button
        """
        keyboard = [
            [InlineKeyboardButton("❌ Cancel Operation", callback_data="cancel")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def dayoff_type_keyboard() -> InlineKeyboardMarkup:
        """
        Create inline keyboard for day-off type selection.
        
        Returns:
            InlineKeyboardMarkup: Keyboard with One-day and Multiple-day options
        """
        keyboard = [
            [InlineKeyboardButton("One-day", callback_data="dayoff_type_oneday")],
            [InlineKeyboardButton("Multiple-day", callback_data="dayoff_type_multiday")],
            [InlineKeyboardButton("❌ Cancel Operation", callback_data="cancel")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def custom_keyboard(buttons: List[Tuple[str, str]], columns: int = 1) -> InlineKeyboardMarkup:
        """
        Create custom inline keyboard with specified buttons.
        
        Args:
            buttons: List of tuples containing (text, callback_data)
            columns: Number of columns to arrange buttons in
            
        Returns:
            InlineKeyboardMarkup: Custom keyboard layout
        """
        keyboard = []
        for i in range(0, len(buttons), columns):
            row = []
            for j in range(columns):
                if i + j < len(buttons):
                    text, callback_data = buttons[i + j]
                    row.append(InlineKeyboardButton(text, callback_data=callback_data))
            keyboard.append(row)
        return InlineKeyboardMarkup(keyboard)
