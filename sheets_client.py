"""
Google Sheets Client for Telegram Claim Bot
Handles all Google Sheets API operations including authentication,
worksheet management, and data operations.
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

logger = logging.getLogger(__name__)

class SheetsClient:
    """Client for Google Sheets API operations"""
    
    def __init__(self, spreadsheet_id: str):
        """
        Initialize Google Sheets client with OAuth credentials
        
        Args:
            spreadsheet_id: Google Sheets spreadsheet ID
        """
        self.spreadsheet_id = spreadsheet_id
        self._service = None
        self._credentials = self._create_oauth_credentials()
        
    def _create_oauth_credentials(self) -> Credentials:
        """Create Google OAuth 2.0 user credentials from token.json file"""
        # Define scopes for both Drive and Sheets access
        scopes = [
            'https://www.googleapis.com/auth/drive.file',
            'https://www.googleapis.com/auth/spreadsheets'
        ]
        
        try:
            logger.info("Loading OAuth 2.0 user credentials from token.json")
            credentials = Credentials.from_authorized_user_file("token.json", scopes)
            logger.info("Successfully loaded OAuth credentials for Google Sheets")
            return credentials
        except FileNotFoundError:
            logger.error("token.json file not found. Make sure GOOGLE_TOKEN_JSON environment variable is set.")
            raise ValueError("token.json file not found. Check GOOGLE_TOKEN_JSON environment variable.")
        except Exception as e:
            logger.error(f"Failed to create OAuth credentials: {e}")
            raise ValueError(f"Invalid OAuth credentials: {e}")
    
    def _get_service(self):
        """Get or create Google Sheets service instance"""
        if self._service is None:
            try:
                self._service = build('sheets', 'v4', credentials=self._credentials)
            except Exception as e:
                logger.error(f"Failed to build Google Sheets service: {e}")
                raise
        return self._service
    
    async def create_worksheet_if_not_exists(self, title: str) -> bool:
        """
        Create a worksheet if it doesn't already exist
        
        Args:
            title: Name of the worksheet to create
            
        Returns:
            bool: True if worksheet was created, False if it already existed
        """
        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._create_worksheet_sync, title
            )
        except Exception as e:
            logger.error(f"Failed to create worksheet {title}: {e}")
            raise
    
    def _create_worksheet_sync(self, title: str) -> bool:
        """Synchronous worksheet creation"""
        service = self._get_service()
        
        try:
            # Check if worksheet already exists
            spreadsheet = service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            existing_sheets = [sheet['properties']['title'] 
                             for sheet in spreadsheet['sheets']]
            
            if title in existing_sheets:
                logger.info(f"Worksheet '{title}' already exists")
                return False
            
            # Create new worksheet
            request_body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': title
                        }
                    }
                }]
            }
            
            service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=request_body
            ).execute()
            
            logger.info(f"Created worksheet '{title}'")
            return True
            
        except HttpError as e:
            logger.error(f"HTTP error creating worksheet {title}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating worksheet {title}: {e}")
            raise    
    
    async def append_registration_data(self, worksheet: str, user_data: Dict[str, Any]) -> bool:
        """
        Append user registration data to specified worksheet
        
        Args:
            worksheet: Name of the worksheet to append to
            user_data: Dictionary containing user registration data
            
        Returns:
            bool: True if data was successfully appended
        """
        try:
            # Ensure worksheet exists
            await self.create_worksheet_if_not_exists(worksheet)
            
            # Prepare data row
            values = [
                user_data.get('telegram_user_id', ''),
                user_data.get('name', ''),
                user_data.get('phone', ''),
                user_data.get('role', ''),
                user_data.get('register_date', datetime.now().isoformat())
            ]
            
            # Run in thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._append_data_sync, worksheet, [values], 'A:E'
            )
            
        except Exception as e:
            logger.error(f"Failed to append registration data: {e}")
            raise
    
    async def append_claim_data(self, claim_data: Dict[str, Any]) -> bool:
        """
        Append claim data to Claims worksheet
        
        Args:
            claim_data: Dictionary containing claim data
            
        Returns:
            bool: True if data was successfully appended
        """
        try:
            worksheet = "Claims"
            await self.create_worksheet_if_not_exists(worksheet)
            
            # Prepare data row
            values = [
                claim_data.get('date', datetime.now().isoformat()),
                claim_data.get('category', ''),
                str(claim_data.get('amount', 0)),
                claim_data.get('receipt_link', ''),
                str(claim_data.get('submitted_by', '')),
                claim_data.get('status', 'Pending')
            ]
            
            # Run in thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._append_data_sync, worksheet, [values], 'A:F'
            )
            
        except Exception as e:
            logger.error(f"Failed to append claim data: {e}")
            raise
    
    async def append_dayoff_data(self, dayoff_data: Dict[str, Any]) -> bool:
        """
        Append day-off request data to Request Day-off worksheet
        
        Args:
            dayoff_data: Dictionary containing day-off request data
            
        Returns:
            bool: True if data was successfully appended
        """
        try:
            worksheet = "Request Day-off"
            await self.create_worksheet_if_not_exists(worksheet)
            
            # Format request date to Malaysia timezone format (DD/MM/YYYY HH:MMam/pm)
            request_date_str = dayoff_data.get('request_date', datetime.now().isoformat())
            formatted_request_date = self._format_malaysia_datetime(request_date_str)
            
            # Prepare data row
            values = [
                formatted_request_date,
                dayoff_data.get('dayoff_date', ''),
                dayoff_data.get('reason', ''),
                dayoff_data.get('submitted_by_name', ''),
                dayoff_data.get('status', 'Pending')
            ]
            
            # Run in thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._append_data_sync, worksheet, [values], 'A:E'
            )
            
        except Exception as e:
            logger.error(f"Failed to append day-off data: {e}")
            raise
    
    def _format_malaysia_datetime(self, datetime_str: str) -> str:
        """
        Format datetime string to Malaysia timezone format (DD/MM/YYYY HH:MMam/pm).
        
        Args:
            datetime_str: ISO format datetime string
            
        Returns:
            Formatted datetime string
        """
        try:
            import pytz
            
            # Parse the datetime string
            if '+' in datetime_str or 'Z' in datetime_str:
                # Already has timezone info
                dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            else:
                # Assume it's already in Malaysia timezone
                dt = datetime.fromisoformat(datetime_str)
                malaysia_tz = pytz.timezone('Asia/Kuala_Lumpur')
                if dt.tzinfo is None:
                    dt = malaysia_tz.localize(dt)
            
            # Convert to Malaysia timezone if needed
            malaysia_tz = pytz.timezone('Asia/Kuala_Lumpur')
            if dt.tzinfo != malaysia_tz:
                dt = dt.astimezone(malaysia_tz)
            
            # Format as DD/MM/YYYY HH:MMam/pm
            formatted_date = dt.strftime('%d/%m/%Y')
            formatted_time = dt.strftime('%I:%M%p').lower()
            
            return f"{formatted_date} {formatted_time}"
            
        except Exception as e:
            logger.error(f"Error formatting Malaysia datetime: {e}")
            # Fallback to simple format
            try:
                dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                return dt.strftime('%d/%m/%Y %I:%M%p').lower()
            except:
                return datetime_str
    
    def _append_data_sync(self, worksheet: str, values: List[List], range_name: str) -> bool:
        """Synchronous data append operation"""
        service = self._get_service()
        
        try:
            # First, ensure the worksheet exists
            self._ensure_worksheet_exists(worksheet)
            
            # Check if headers exist, add them if not
            self._ensure_headers_exist(worksheet, range_name)
            
            # Append data
            request_body = {
                'values': values
            }
            
            result = service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{worksheet}!{range_name}",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=request_body
            ).execute()
            
            logger.info(f"Appended {len(values)} rows to {worksheet}")
            return True
            
        except HttpError as e:
            logger.error(f"HTTP error appending data to {worksheet}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error appending data to {worksheet}: {e}")
            raise
    
    def _ensure_worksheet_exists(self, worksheet: str):
        """Ensure worksheet exists, create if it doesn't"""
        service = self._get_service()
        
        try:
            # Check if worksheet already exists
            spreadsheet = service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            existing_sheets = [sheet['properties']['title'] 
                             for sheet in spreadsheet['sheets']]
            
            if worksheet not in existing_sheets:
                logger.info(f"Creating worksheet '{worksheet}' as it doesn't exist")
                # Create new worksheet
                request_body = {
                    'requests': [{
                        'addSheet': {
                            'properties': {
                                'title': worksheet
                            }
                        }
                    }]
                }
                
                service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body=request_body
                ).execute()
                
                logger.info(f"Successfully created worksheet '{worksheet}'")
            else:
                logger.info(f"Worksheet '{worksheet}' already exists")
                
        except HttpError as e:
            logger.error(f"HTTP error ensuring worksheet {worksheet} exists: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error ensuring worksheet {worksheet} exists: {e}")
            raise
    
    def _ensure_headers_exist(self, worksheet: str, range_name: str):
        """Ensure worksheet has proper headers"""
        service = self._get_service()
        
        try:
            # Check if worksheet has data
            result = service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{worksheet}!A1:Z1"
            ).execute()
            
            values = result.get('values', [])
            
            # Add headers if worksheet is empty
            if not values:
                if worksheet in ["Claims", "Staff Claims", "Manager Claims", "Ambassador Claims"]:
                    # Claims worksheets (role-specific claims sheets)
                    headers = [['Date', 'Category', 'Amount', 'Receipt Link', 'Submitted By', 'Status']]
                elif worksheet == "Request Day-off":
                    # Day-off request worksheet
                    headers = [['Date of Request', 'Requested Day-off Date', 'Reason', 'Submitted By', 'Status']]
                elif worksheet in ["Staff", "Manager", "Ambassador"]:
                    # Registration worksheets (user information only)
                    headers = [['Telegram User ID', 'Name', 'Phone', 'Role', 'Register Date']]
                else:
                    # Default to registration format for unknown worksheets
                    headers = [['Telegram User ID', 'Name', 'Phone', 'Role', 'Register Date']]
                
                service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{worksheet}!A1",
                    valueInputOption='RAW',
                    body={'values': headers}
                ).execute()
                
                logger.info(f"Added headers to worksheet {worksheet}")
                
        except HttpError as e:
            logger.error(f"HTTP error ensuring headers for {worksheet}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error ensuring headers for {worksheet}: {e}")
            raise 
   
    async def get_user_by_telegram_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user data by Telegram user ID from all registration worksheets
        
        Args:
            user_id: Telegram user ID to search for
            
        Returns:
            Dict containing user data if found, None otherwise
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._get_user_sync, user_id
            )
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            raise
    
    def _get_user_sync(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Optimized synchronous user lookup with memory management"""
        import gc
        
        service = self._get_service()
        
        # Search in all possible role worksheets
        worksheets = ['Staff', 'Manager', 'Ambassador']
        
        for worksheet in worksheets:
            result = None
            values = None
            
            try:
                # Use batch request to limit data retrieval
                # First, try to get only the first 100 rows to limit memory usage
                result = service.spreadsheets().values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{worksheet}!A1:E100"  # Limit to first 100 rows
                ).execute()
                
                values = result.get('values', [])
                
                # Skip header row if it exists
                if values and len(values) > 1:
                    for row_idx, row in enumerate(values[1:], 1):  # Start from row 1 (skip header)
                        if len(row) > 0 and str(row[0]) == str(user_id):
                            user_data = {
                                'telegram_user_id': int(row[0]) if row[0] else None,
                                'name': row[1] if len(row) > 1 else '',
                                'phone': row[2] if len(row) > 2 else '',
                                'role': row[3] if len(row) > 3 else worksheet,
                                'register_date': row[4] if len(row) > 4 else ''
                            }
                            
                            # Clear large objects immediately
                            del result, values
                            gc.collect()
                            
                            return user_data
                
                # If not found in first 100 rows, try next batch
                if len(values) >= 100:  # If we got 100 rows, there might be more
                    # Clear current data before next request
                    del result, values
                    gc.collect()
                    
                    # Get next batch (rows 101-200)
                    result = service.spreadsheets().values().get(
                        spreadsheetId=self.spreadsheet_id,
                        range=f"{worksheet}!A101:E200"
                    ).execute()
                    
                    values = result.get('values', [])
                    
                    for row in values:
                        if len(row) > 0 and str(row[0]) == str(user_id):
                            user_data = {
                                'telegram_user_id': int(row[0]) if row[0] else None,
                                'name': row[1] if len(row) > 1 else '',
                                'phone': row[2] if len(row) > 2 else '',
                                'role': row[3] if len(row) > 3 else worksheet,
                                'register_date': row[4] if len(row) > 4 else ''
                            }
                            
                            # Clear large objects immediately
                            del result, values
                            gc.collect()
                            
                            return user_data
                            
            except HttpError as e:
                if e.resp.status == 400:
                    # Worksheet doesn't exist, continue searching
                    continue
                else:
                    logger.error(f"Error searching in worksheet {worksheet}: {e}")
                    continue
            except Exception as e:
                logger.error(f"Unexpected error searching in worksheet {worksheet}: {e}")
                continue
            finally:
                # Always clean up large objects
                try:
                    if result:
                        del result
                    if values:
                        del values
                    gc.collect()
                except:
                    pass
        
        return None
    
    async def validate_spreadsheet_access(self) -> bool:
        """
        Validate that the client can access the spreadsheet
        
        Returns:
            bool: True if spreadsheet is accessible
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._validate_access_sync
            )
        except Exception as e:
            logger.error(f"Failed to validate spreadsheet access: {e}")
            return False
    
    def _validate_access_sync(self) -> bool:
        """Synchronous access validation"""
        try:
            service = self._get_service()
            spreadsheet = service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            logger.info(f"Successfully accessed spreadsheet: {spreadsheet.get('properties', {}).get('title', 'Unknown')}")
            return True
            
        except HttpError as e:
            logger.error(f"HTTP error validating access: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error validating access: {e}")
            return False
    
    async def get_all_claims(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get all claims from Claims worksheet
        
        Args:
            limit: Optional limit on number of claims to return
            
        Returns:
            List of claim dictionaries
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._get_claims_sync, limit
            )
        except Exception as e:
            logger.error(f"Failed to get claims: {e}")
            raise
    
    def _get_claims_sync(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Synchronous claims retrieval"""
        service = self._get_service()
        
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range="Claims!A:F"
            ).execute()
            
            values = result.get('values', [])
            claims = []
            
            # Skip header row if it exists
            if values and len(values) > 1:
                rows_to_process = values[1:limit+1] if limit else values[1:]
                
                for row in rows_to_process:
                    if len(row) >= 6:
                        claims.append({
                            'date': row[0],
                            'category': row[1],
                            'amount': float(row[2]) if row[2] else 0.0,
                            'receipt_link': row[3],
                            'submitted_by': int(row[4]) if row[4] else None,
                            'status': row[5]
                        })
            
            return claims
            
        except HttpError as e:
            if e.resp.status == 400:
                # Claims worksheet doesn't exist yet
                return []
            else:
                logger.error(f"HTTP error getting claims: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error getting claims: {e}")
            raise
