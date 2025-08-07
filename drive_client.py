"""
Google Drive Client for Telegram Claim Bot
Handles file uploads, folder management, and shareable link generation
for receipt photos organized by category and date.
"""

import json
import io
from datetime import datetime
from typing import Dict, List, Optional, Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
import logging

logger = logging.getLogger(__name__)

class DriveClient:
    """Client for Google Drive API operations"""
    
    def __init__(self, root_folder_id: Optional[str] = None):
        """
        Initialize Google Drive client with OAuth credentials
        
        Args:
            root_folder_id: Optional root folder ID for organizing files
        """
        self.root_folder_id = root_folder_id
        self._service = None
        self._credentials = self._create_oauth_credentials()
        self._folder_cache = {}  # Cache folder IDs to avoid repeated API calls
        
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
            logger.info("Successfully loaded OAuth credentials for Google Drive")
            return credentials
        except FileNotFoundError:
            logger.error("token.json file not found. Make sure GOOGLE_TOKEN_JSON environment variable is set.")
            raise ValueError("token.json file not found. Check GOOGLE_TOKEN_JSON environment variable.")
        except Exception as e:
            logger.error(f"Failed to create OAuth credentials: {e}")
            raise ValueError(f"Invalid OAuth credentials: {e}")
    
    def _get_service(self):
        """Get or create Google Drive service instance"""
        if self._service is None:
            try:
                self._service = build('drive', 'v3', credentials=self._credentials)
            except Exception as e:
                logger.error(f"Failed to build Google Drive service: {e}")
                raise
        return self._service
    
    def generate_folder_path(self, category: str, date: str) -> str:
        """
        Generate folder path based on category and date
        
        Args:
            category: Expense category (Food, Transportation, etc.)
            date: Date string in YYYY-MM-DD format
            
        Returns:
            str: Folder path in format "Category/YYYY-MM-DD"
        """
        try:
            # Parse date to ensure proper format
            if isinstance(date, str):
                date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
            else:
                date_obj = date
            
            date_str = date_obj.strftime('%Y-%m-%d')
            return f"{category}/{date_str}"
            
        except Exception as e:
            logger.error(f"Error generating folder path: {e}")
            # Fallback to current date
            current_date = datetime.now().strftime('%Y-%m-%d')
            return f"{category}/{current_date}"
    
    def create_folder_if_not_exists(self, folder_path: str) -> str:
        """
        Create folder structure if it doesn't exist
        
        Args:
            folder_path: Path like "Category/YYYY-MM-DD"
            
        Returns:
            str: Folder ID of the final folder
        """
        try:
            return self._create_folder_sync(folder_path)
        except Exception as e:
            logger.error(f"Failed to create folder {folder_path}: {e}")
            raise
    
    def _create_folder_sync(self, folder_path: str) -> str:
        """Synchronous folder creation"""
        service = self._get_service()
        
        # Check cache first
        if folder_path in self._folder_cache:
            return self._folder_cache[folder_path]
        
        try:
            # If no root folder specified, return None to upload to accessible location
            if not self.root_folder_id:
                logger.warning("No root folder specified, files will be uploaded to default location")
                return None
            
            # Split path into components
            path_parts = folder_path.split('/')
            current_parent_id = self.root_folder_id
            
            for part in path_parts:
                if not part:  # Skip empty parts
                    continue
                
                # Check if folder exists
                folder_id = self._find_folder_by_name(part, current_parent_id)
                
                if folder_id:
                    current_parent_id = folder_id
                else:
                    # Create folder
                    folder_metadata = {
                        'name': part,
                        'mimeType': 'application/vnd.google-apps.folder'
                    }
                    
                    if current_parent_id:
                        folder_metadata['parents'] = [current_parent_id]
                    
                    try:
                        folder = service.files().create(
                            body=folder_metadata,
                            fields='id'
                        ).execute()
                        
                        current_parent_id = folder.get('id')
                        logger.info(f"Created folder '{part}' with ID: {current_parent_id}")
                    except HttpError as folder_error:
                        if folder_error.resp.status == 403:
                            logger.warning(f"Cannot create folder '{part}', using parent folder instead")
                            # Use parent folder if can't create subfolder
                            break
                        else:
                            raise
            
            # Cache the result
            self._folder_cache[folder_path] = current_parent_id
            return current_parent_id
            
        except HttpError as e:
            logger.error(f"HTTP error creating folder {folder_path}: {e}")
            # Return root folder as fallback
            return self.root_folder_id
        except Exception as e:
            logger.error(f"Unexpected error creating folder {folder_path}: {e}")
            # Return root folder as fallback
            return self.root_folder_id
    
    def _find_folder_by_name(self, name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """Find folder by name within parent folder"""
        service = self._get_service()
        
        try:
            query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = service.files().list(
                q=query,
                fields='files(id, name)'
            ).execute()
            
            files = results.get('files', [])
            if files:
                return files[0]['id']
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding folder {name}: {e}")
            return None   
 
    def upload_photo(self, photo_data: bytes, filename: str, folder_id: str) -> str:
        """
        Upload photo to Google Drive
        
        Args:
            photo_data: Photo data as bytes
            filename: Name for the uploaded file
            folder_id: ID of the folder to upload to
            
        Returns:
            str: File ID of uploaded photo
        """
        try:
            return self._upload_photo_sync(photo_data, filename, folder_id)
        except Exception as e:
            logger.error(f"Failed to upload photo {filename}: {e}")
            raise
    
    def _upload_photo_sync(self, photo_data: bytes, filename: str, folder_id: str) -> str:
        """Synchronous photo upload to shared folder with memory optimization"""
        service = self._get_service()
        media_stream = None
        
        try:
            # Create file metadata
            file_metadata = {
                'name': filename
            }
            
            # Always upload to the specified shared folder (user's personal Drive)
            target_folder_id = folder_id or self.root_folder_id
            
            if not target_folder_id:
                raise ValueError("No target folder specified. Please set GOOGLE_DRIVE_FOLDER_ID environment variable.")
            
            file_metadata['parents'] = [target_folder_id]
            
            logger.debug(f"Uploading {filename} ({len(photo_data)} bytes) to folder {target_folder_id}")
            
            # Create media upload object with explicit stream management
            media_stream = io.BytesIO(photo_data)
            media = MediaIoBaseUpload(
                media_stream,
                mimetype='image/jpeg',
                resumable=False  # Changed to False to avoid keeping upload buffers
            )
            
            # Upload file
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file.get('id')
            logger.debug(f"Uploaded photo {filename} with ID: {file_id}")
            
            # Set file permissions
            try:
                permission = {
                    'role': 'reader',
                    'type': 'anyone'
                }
                service.permissions().create(
                    fileId=file_id,
                    body=permission
                ).execute()
                logger.debug(f"Set public read permissions for file {file_id}")
            except HttpError as perm_error:
                logger.warning(f"Could not set public permissions for file {file_id}: {perm_error}")
            
            # Release memory immediately after successful upload to reduce memory usage
            if media_stream is not None:
                media_stream.close()
                del media_stream
                import gc
                gc.collect()
                logger.info("[MEMORY] Released file_data after successful Drive upload")
            
            return file_id
            
        except HttpError as e:
            logger.error(f"HTTP error uploading photo {filename}: {e}")
            # Provide more specific error messages based on the error type
            if e.resp.status == 403:
                if 'storageQuotaExceeded' in str(e):
                    if 'Service Accounts do not have storage quota' in str(e):
                        error_msg = (
                            f"Service Account has no storage quota. Current settings:\n"
                            f"- Target folder: {target_folder_id}\n"
                            f"- Service Account: telegram-bot-service@pryme-468004.iam.gserviceaccount.com\n"
                            f"Please confirm the folder is properly shared with the Service Account with editor permissions."
                        )
                    else:
                        error_msg = (
                            f"Storage quota exceeded. Solutions:\n"
                            f"1. Ensure folder {target_folder_id} belongs to a user account with storage space\n"
                            f"2. The folder needs to be shared with Service Account with edit permissions\n"
                            f"3. Check if the folder owner's Google Drive storage space is sufficient"
                        )
                elif 'insufficientFilePermissions' in str(e):
                    error_msg = (
                        f"Insufficient permissions. Solutions:\n"
                        f"1. Please share folder {target_folder_id} with Service Account email\n"
                        f"2. Ensure 'Editor' permissions are granted\n"
                        f"3. Service Account email can be found in Google Cloud Console"
                    )
                else:
                    error_msg = f"Access denied (HTTP 403). Please check permissions for folder {target_folder_id}."
                logger.error(error_msg)
                raise ValueError(error_msg)
            elif e.resp.status == 404:
                error_msg = (
                    f"Folder does not exist or is inaccessible (HTTP 404). Solutions:\n"
                    f"1. Check if GOOGLE_DRIVE_FOLDER_ID is correct: {target_folder_id}\n"
                    f"2. Ensure the folder is shared with Service Account\n"
                    f"3. Folder ID can be obtained from Google Drive URL"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            else:
                logger.error(f"Google Drive API error (HTTP {e.resp.status}): {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error uploading photo {filename}: {e}")
            raise
        finally:
            # Fallback low-frequency timed GC (every 15 minutes) to prevent small object accumulation
            # Note: Implement a background task in __init__ for timed GC
            pass  # Placeholder; actual implementation in class init
    
    def get_shareable_link(self, file_id: str) -> str:
        """
        Generate shareable link for a file
        
        Args:
            file_id: Google Drive file ID
            
        Returns:
            str: Shareable link URL
        """
        try:
            return self._get_shareable_link_sync(file_id)
        except Exception as e:
            logger.error(f"Failed to get shareable link for {file_id}: {e}")
            raise
    
    def _get_shareable_link_sync(self, file_id: str) -> str:
        """Synchronous shareable link generation"""
        service = self._get_service()
        
        try:
            # Make file publicly viewable
            permission = {
                'role': 'reader',
                'type': 'anyone'
            }
            
            service.permissions().create(
                fileId=file_id,
                body=permission
            ).execute()
            
            # Get file info to construct shareable link
            file_info = service.files().get(
                fileId=file_id,
                fields='webViewLink'
            ).execute()
            
            shareable_link = file_info.get('webViewLink')
            logger.info(f"Generated shareable link for file {file_id}")
            return shareable_link
            
        except HttpError as e:
            logger.error(f"HTTP error getting shareable link for {file_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting shareable link for {file_id}: {e}")
            raise
    
    def upload_receipt_with_organization(self, photo_data: bytes, category: str, 
                                            user_id: int, timestamp: Optional[datetime] = None) -> str:
        """
        Upload receipt photo with automatic folder organization
        
        Args:
            photo_data: Photo data as bytes
            category: Expense category
            user_id: Telegram user ID for filename
            timestamp: Optional timestamp, defaults to current time
            
        Returns:
            str: Shareable link to the uploaded photo
        """
        try:
            if timestamp is None:
                timestamp = datetime.now()
            
            # Generate filename with category and timestamp info
            filename = f"receipt_{user_id}_{category}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            
            # Try to upload with folder organization first
            try:
                # Generate folder path
                folder_path = self.generate_folder_path(category, timestamp.isoformat())
                
                # Create folder structure
                folder_id = self.create_folder_if_not_exists(folder_path)
                
                # Upload photo
                file_id = self.upload_photo(photo_data, filename, folder_id)
                
            except HttpError as e:
                if e.resp.status == 403 and 'storageQuotaExceeded' in str(e):
                    logger.warning(f"Storage quota exceeded, uploading to root folder for user {user_id}")
                    # Fallback: upload directly to root folder without organization
                    file_id = self.upload_photo(photo_data, filename, self.root_folder_id)
                else:
                    raise
            
            # Generate shareable link
            shareable_link = self.get_shareable_link(file_id)
            
            logger.info(f"Successfully uploaded receipt for user {user_id} in category {category}")
            return shareable_link
            
        except Exception as e:
            logger.error(f"Failed to upload receipt with organization: {e}")
            raise
    
    def validate_drive_access(self) -> bool:
        """
        Validate that the client can access Google Drive
        
        Returns:
            bool: True if Drive is accessible
        """
        try:
            return self._validate_access_sync()
        except Exception as e:
            logger.error(f"Failed to validate Drive access: {e}")
            return False
    
    def _validate_access_sync(self) -> bool:
        """Synchronous access validation"""
        try:
            service = self._get_service()
            
            # Try to get information about the root folder or user's Drive
            if self.root_folder_id:
                file_info = service.files().get(
                    fileId=self.root_folder_id,
                    fields='id,name'
                ).execute()
                logger.info(f"Successfully accessed root folder: {file_info.get('name', 'Unknown')}")
            else:
                # Test basic Drive access
                results = service.files().list(
                    pageSize=1,
                    fields='files(id,name)'
                ).execute()
                logger.info("Successfully accessed Google Drive")
            
            return True
            
        except HttpError as e:
            logger.error(f"HTTP error validating Drive access: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error validating Drive access: {e}")
            return False
    
    def list_files_in_folder(self, folder_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        List files in a specific folder
        
        Args:
            folder_id: Google Drive folder ID
            limit: Maximum number of files to return
            
        Returns:
            List of file information dictionaries
        """
        try:
            return self._list_files_sync(folder_id, limit)
        except Exception as e:
            logger.error(f"Failed to list files in folder {folder_id}: {e}")
            raise
    
    def _list_files_sync(self, folder_id: str, limit: int) -> List[Dict[str, Any]]:
        """Synchronous file listing"""
        service = self._get_service()
        
        try:
            query = f"'{folder_id}' in parents and trashed=false"
            
            results = service.files().list(
                q=query,
                pageSize=limit,
                fields='files(id,name,createdTime,size,webViewLink)'
            ).execute()
            
            files = results.get('files', [])
            return files
            
        except HttpError as e:
            logger.error(f"HTTP error listing files in folder {folder_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing files in folder {folder_id}: {e}")
            raise

def delete_file(self, file_id: str) -> bool:
    """
    Delete a file from Google Drive
    
    Args:
        file_id: Google Drive file ID
        
    Returns:
        bool: True if successfully deleted
    """
    try:
        return self._delete_file_sync(file_id)
    except Exception as e:
        logger.error(f"Failed to delete file {file_id}: {e}")
        return False

def _delete_file_sync(self, file_id: str) -> bool:
    """Synchronous file deletion"""
    service = self._get_service()
    try:
        service.files().delete(fileId=file_id).execute()
        logger.info(f"Deleted file {file_id}")
        return True
    except HttpError as e:
        logger.error(f"HTTP error deleting file {file_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error deleting file {file_id}: {e}")
        return False

def delete_user_files(self, user_id: int) -> Dict[str, Any]:
    """
    Delete all files associated with a specific user ID
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Dict with count of deleted files and any errors
    """
    try:
        return self._delete_user_files_sync(user_id)
    except Exception as e:
        logger.error(f"Failed to delete files for user {user_id}: {e}")
        return {"deleted_count": 0, "error": str(e)}

def _delete_user_files_sync(self, user_id: int) -> Dict[str, Any]:
    """Synchronous deletion of all files associated with a user"""
    import gc
    service = self._get_service()
    deleted_count = 0
    errors = []
    
    try:
        # Search for files with user ID in filename
        query = f"name contains 'receipt_{user_id}_' and trashed=false"
        
        # Get all matching files
        results = service.files().list(
            q=query,
            fields="files(id,name)"
        ).execute()
        
        files = results.get('files', [])
        logger.info(f"Found {len(files)} files for user {user_id}")
        
        # Delete each file
        for file in files:
            try:
                file_id = file.get('id')
                service.files().delete(fileId=file_id).execute()
                deleted_count += 1
                logger.info(f"Deleted file {file.get('name')} (ID: {file_id})")
            except Exception as file_error:
                error_msg = f"Error deleting file {file.get('name')}: {file_error}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # Force garbage collection
        del results, files
        gc.collect()
        
        return {
            "deleted_count": deleted_count,
            "errors": errors if errors else None
        }
        
    except HttpError as e:
        logger.error(f"HTTP error searching for user files {user_id}: {e}")
        return {"deleted_count": deleted_count, "error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error deleting user files {user_id}: {e}")
        return {"deleted_count": deleted_count, "error": str(e)}
