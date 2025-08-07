"""
Conversation states for Telegram Bot ConversationHandler
Defines all state constants for multi-step conversations
"""

# Registration conversation states
REGISTER_NAME = 1
REGISTER_PHONE = 2
REGISTER_ROLE = 3

# Claim conversation states
CLAIM_CATEGORY = 10
CLAIM_AMOUNT = 11
CLAIM_OTHER_DESCRIPTION = 12
CLAIM_PHOTO = 13
CLAIM_CONFIRM = 14

# Day-off conversation states
DAYOFF_TYPE = 20
DAYOFF_DATE = 21
DAYOFF_START_DATE = 22
DAYOFF_END_DATE = 23
DAYOFF_REASON = 24

# Admin conversation states
SELECT_ROLE = 30
SELECT_USER = 31
SHOW_STATS = 32
CONFIRM_DELETE = 33
