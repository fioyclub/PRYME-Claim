"""
Google Drive Client for Telegram Claim Bot
Handles file uploads, folder management, and shareable link generation
for receipt photos organized by category and date.
"""
import asyncio
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
    
    async def create_folder_if_not_exists(self, folder_path: str) -> str:
        """
        Create folder structure if it doesn't exist
        
        Args:
            folder_path: Path like "Category/YYYY-MM-DD"
            
        Returns:
            str: Folder ID of the final folder
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._create_folder_sync, folder_path
            )
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
 
    async def upload_photo(self, photo_data: bytes, filename: str, folder_id: str) -> str:
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
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._upload_photo_sync, photo_data, filename, folder_id
            )
        except Exception as e:
            logger.error(f"Failed to upload photo {filename}: {e}")
            raise
    
    def _upload_photo_sync(self, photo_data: bytes, filename: str, folder_id: str) -> str:
        """Synchronous photo upload to shared folder"""
        service = self._get_service()
        
        try:
            # Create file metadata
            file_metadata = {
                'name': filename
            }
            
            # Always upload to the specified shared folder (user's personal Drive)
            # This folder should be owned by a user account with storage quota
            # and shared with the service account with Editor permissions
            target_folder_id = folder_id or self.root_folder_id
            
            if not target_folder_id:
                raise ValueError("No target folder specified. Please set GOOGLE_DRIVE_FOLDER_ID environment variable.")
            
            # Force upload to the shared folder - never upload to service account's root
            file_metadata['parents'] = [target_folder_id]
            
            logger.info(f"Uploading {filename} to shared folder {target_folder_id} (not service account drive)")
            
            # Create media upload object
            media = MediaIoBaseUpload(
                io.BytesIO(photo_data),
                mimetype='image/jpeg',  # Assume JPEG for receipts
                resumable=True
            )
            
            # Upload file using OAuth user credentials to personal Drive
            logger.info(f"Uploading {filename} using OAuth user credentials to personal Drive")
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file.get('id')
            logger.info(f"Uploaded photo {filename} with ID: {file_id} to shared folder: {target_folder_id}")
            
            # Set file permissions to make it viewable by anyone with the link
            try:
                permission = {
                    'role': 'reader',
                    'type': 'anyone'
                }
                service.permissions().create(
                    fileId=file_id,
                    body=permission
                ).execute()
                logger.info(f"Set public read permissions for file {file_id}")
            except HttpError as perm_error:
                logger.warning(f"Could not set public permissions for file {file_id}: {perm_error}")
                # Continue anyway - the file might still be accessible
            
            return file_id
            
        except HttpError as e:
            logger.error(f"HTTP error uploading photo {filename}: {e}")
            # Provide more specific error messages based on the error type
            if e.resp.status == 403:
                if 'storageQuotaExceeded' in str(e):
                    if 'Service Accounts do not have storage quota' in str(e):
                        error_msg = (
                            f"Service Account没有存储配额。当前设置：\n"
                            f"- 目标文件夹: {target_folder_id}\n"
                            f"- Service Account: telegram-bot-service@pryme-468004.iam.gserviceaccount.com\n"
                            f"请确认文件夹已正确共享给Service Account并设为编辑者权限。"
                        )
                    else:
                        error_msg = (
                            f"存储配额已满。解决方案：\n"
                            f"1. 请确保文件夹 {target_folder_id} 属于有存储空间的用户账号\n"
                            f"2. 该文件夹需要与Service Account共享并给予编辑权限\n"
                            f"3. 检查文件夹所有者的Google Drive存储空间是否充足"
                        )
                elif 'insufficientFilePermissions' in str(e):
                    error_msg = (
                        f"权限不足。解决方案：\n"
                        f"1. 请将文件夹 {target_folder_id} 与Service Account邮箱共享\n"
                        f"2. 确保给予'编辑者'权限\n"
                        f"3. Service Account邮箱可在Google Cloud Console中找到"
                    )
                else:
                    error_msg = f"访问被拒绝 (HTTP 403)。请检查文件夹 {target_folder_id} 的权限设置。"
                logger.error(error_msg)
                raise ValueError(error_msg)
            elif e.resp.status == 404:
                error_msg = (
                    f"文件夹不存在或无法访问 (HTTP 404)。解决方案：\n"
                    f"1. 检查GOOGLE_DRIVE_FOLDER_ID是否正确：{target_folder_id}\n"
                    f"2. 确保该文件夹与Service Account共享\n"
                    f"3. 文件夹ID可从Google Drive URL中获取"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            else:
                logger.error(f"Google Drive API错误 (HTTP {e.resp.status}): {e}")
                raise
        except Exception as e:
            logger.error(f"上传照片时发生意外错误 {filename}: {e}")
            raise
    
    async def get_shareable_link(self, file_id: str) -> str:
        """
        Generate shareable link for a file
        
        Args:
            file_id: Google Drive file ID
            
        Returns:
            str: Shareable link URL
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._get_shareable_link_sync, file_id
            )
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
    
    async def upload_receipt_with_organization(self, photo_data: bytes, category: str, 
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
                folder_id = await self.create_folder_if_not_exists(folder_path)
                
                # Upload photo
                file_id = await self.upload_photo(photo_data, filename, folder_id)
                
            except HttpError as e:
                if e.resp.status == 403 and 'storageQuotaExceeded' in str(e):
                    logger.warning(f"Storage quota exceeded, uploading to root folder for user {user_id}")
                    # Fallback: upload directly to root folder without organization
                    file_id = await self.upload_photo(photo_data, filename, self.root_folder_id)
                else:
                    raise
            
            # Generate shareable link
            shareable_link = await self.get_shareable_link(file_id)
            
            logger.info(f"Successfully uploaded receipt for user {user_id} in category {category}")
            return shareable_link
            
        except Exception as e:
            logger.error(f"Failed to upload receipt with organization: {e}")
            raise
    
    async def validate_drive_access(self) -> bool:
        """
        Validate that the client can access Google Drive
        
        Returns:
            bool: True if Drive is accessible
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._validate_access_sync
            )
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
    
    async def list_files_in_folder(self, folder_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        List files in a specific folder
        
        Args:
            folder_id: Google Drive folder ID
            limit: Maximum number of files to return
            
        Returns:
            List of file information dictionaries
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._list_files_sync, folder_id, limit
            )
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
