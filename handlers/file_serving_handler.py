import telebot
import logging
import json
import os
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class FileServingHandler:
    """Handler for serving files using Telegram file IDs with fallback support"""
    
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
    
    def send_product_image(self, chat_id, image_data, caption=None):
        """
        Send a product image using file ID with automatic fallback
        
        Args:
            chat_id: Telegram chat ID
            image_data: Dict containing image information
            caption: Optional caption for the image
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            if image_data.get('storage_type') == 'telegram_file_id':
                return self._send_from_file_id(chat_id, image_data, caption)
            else:
                return self._send_from_local_storage(chat_id, image_data, caption)
        except Exception as e:
            logger.error(f"Error sending product image: {e}")
            return False
    
    def _send_from_file_id(self, chat_id, image_data, caption=None):
        """Send image using Telegram file ID"""
        try:
            file_id = image_data['file_id']
            file_type = image_data.get('type', 'image')
            
            if file_type == 'video':
                message = self.bot.send_video(
                    chat_id=chat_id,
                    video=file_id,
                    caption=caption
                )
            else:  # image
                message = self.bot.send_photo(
                    chat_id=chat_id,
                    photo=file_id,
                    caption=caption
                )
            
            logger.info(f"Successfully sent image via file ID: {file_id}")
            return True
            
        except telebot.apihelper.ApiTelegramException as e:
            logger.warning(f"Failed to send via file ID {file_id}: {e}")
            
            # Handle FILE_REFERENCE_EXPIRED or similar errors
            if "FILE_REFERENCE_EXPIRED" in str(e) or "file not found" in str(e).lower():
                logger.info("File reference expired, trying to refresh...")
                # You could implement file reference refresh here if needed
                # For now, we'll just log the issue
                return False
            else:
                # Other API errors
                raise e
    
    def _send_from_local_storage(self, chat_id, image_data, caption=None):
        """Send image from local storage (fallback method)"""
        try:
            if 'local_path' not in image_data:
                logger.error("No local path available for image")
                return False
            
            local_path = image_data['local_path']
            if not os.path.exists(local_path):
                logger.error(f"Local file not found: {local_path}")
                return False
            
            file_type = image_data.get('type', 'image')
            
            with open(local_path, 'rb') as file:
                if file_type == 'video':
                    message = self.bot.send_video(
                        chat_id=chat_id,
                        video=file,
                        caption=caption
                    )
                else:  # image
                    message = self.bot.send_photo(
                        chat_id=chat_id,
                        photo=file,
                        caption=caption
                    )
            
            logger.info(f"Successfully sent image from local storage: {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send from local storage: {e}")
            return False
    
    def send_product_gallery(self, chat_id, product_images, product_name=None):
        """
        Send multiple product images as a media group
        
        Args:
            chat_id: Telegram chat ID
            product_images: List of image data dicts
            product_name: Optional product name for caption
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not product_images:
            return False
        
        try:
            media_group = []
            
            for i, image_data in enumerate(product_images[:10]):  # Telegram limit is 10 media items
                file_id = image_data.get('file_id')
                file_type = image_data.get('type', 'image')
                
                if not file_id:
                    continue
                
                # Add caption to first image
                caption = None
                if i == 0 and product_name:
                    caption = f"📦 {product_name}"
                
                if file_type == 'video':
                    media_item = telebot.types.InputMediaVideo(
                        media=file_id,
                        caption=caption
                    )
                else:  # image
                    media_item = telebot.types.InputMediaPhoto(
                        media=file_id,
                        caption=caption
                    )
                
                media_group.append(media_item)
            
            if media_group:
                self.bot.send_media_group(chat_id=chat_id, media=media_group)
                return True
            else:
                return False
                
        except telebot.apihelper.ApiTelegramException as e:
            logger.warning(f"Failed to send media group: {e}")
            # Fallback to sending images individually
            success_count = 0
            for image_data in product_images:
                if self.send_product_image(chat_id, image_data):
                    success_count += 1
            
            return success_count > 0
        except Exception as e:
            logger.error(f"Error sending product gallery: {e}")
            return False
    
    def send_downloadable_file(self, chat_id, file_data, caption=None):
        """
        Send a downloadable product file using file ID with automatic fallback
        
        Args:
            chat_id: Telegram chat ID
            file_data: Dict containing file information
            caption: Optional caption for the file
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            if file_data.get('storage_type') == 'telegram_file_id':
                return self._send_file_from_file_id(chat_id, file_data, caption)
            else:
                return self._send_file_from_local_storage(chat_id, file_data, caption)
        except Exception as e:
            logger.error(f"Error sending downloadable file: {e}")
            return False
    
    def _send_file_from_file_id(self, chat_id, file_data, caption=None):
        """Send file using Telegram file ID"""
        try:
            file_id = file_data['file_id']
            file_type = file_data.get('type', 'document')
            
            if file_type == 'video':
                message = self.bot.send_video(
                    chat_id=chat_id,
                    video=file_id,
                    caption=caption
                )
            elif file_type in ['jpg', 'jpeg', 'png', 'gif']:
                message = self.bot.send_photo(
                    chat_id=chat_id,
                    photo=file_id,
                    caption=caption
                )
            else:  # document
                message = self.bot.send_document(
                    chat_id=chat_id,
                    document=file_id,
                    caption=caption
                )
            
            logger.info(f"Successfully sent file via file ID: {file_id}")
            return True
            
        except telebot.apihelper.ApiTelegramException as e:
            logger.warning(f"Failed to send file via file ID {file_id}: {e}")
            
            # Handle FILE_REFERENCE_EXPIRED or similar errors
            if "FILE_REFERENCE_EXPIRED" in str(e) or "file not found" in str(e).lower():
                logger.info("File reference expired for downloadable file")
                return False
            else:
                # Other API errors
                raise e
    
    def _send_file_from_local_storage(self, chat_id, file_data, caption=None):
        """Send file from local storage (fallback method)"""
        try:
            if 'local_path' not in file_data:
                logger.error("No local path available for file")
                return False
            
            local_path = file_data['local_path']
            if not os.path.exists(local_path):
                logger.error(f"Local file not found: {local_path}")
                return False
            
            file_type = file_data.get('type', 'document')
            
            with open(local_path, 'rb') as file:
                if file_type == 'video':
                    message = self.bot.send_video(
                        chat_id=chat_id,
                        video=file,
                        caption=caption
                    )
                elif file_type in ['jpg', 'jpeg', 'png', 'gif']:
                    message = self.bot.send_photo(
                        chat_id=chat_id,
                        photo=file,
                        caption=caption
                    )
                else:  # document
                    message = self.bot.send_document(
                        chat_id=chat_id,
                        document=file,
                        caption=caption
                    )
            
            logger.info(f"Successfully sent file from local storage: {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send file from local storage: {e}")
            return False
    
    def send_product_files(self, chat_id, product_files, product_name=None):
        """
        Send multiple product files for downloadable products
        
        Args:
            chat_id: Telegram chat ID
            product_files: List of file data dicts
            product_name: Optional product name for caption
            
        Returns:
            int: Number of files sent successfully
        """
        if not product_files:
            return 0
        
        success_count = 0
        
        for i, file_data in enumerate(product_files):
            # Add caption to first file
            caption = None
            if i == 0 and product_name:
                caption = f"📦 {product_name} - File {i+1}/{len(product_files)}"
            elif product_name:
                caption = f"📦 {product_name} - File {i+1}/{len(product_files)}"
            
            if self.send_downloadable_file(chat_id, file_data, caption):
                success_count += 1
            else:
                logger.warning(f"Failed to send file {i+1}/{len(product_files)}: {file_data.get('file_name', 'unknown')}")
        
        return success_count

    def get_file_info(self, file_data):
        """
        Get formatted information about a file (works for both images and downloadable files)
        
        Args:
            file_data: Dict containing file information
            
        Returns:
            str: Formatted file information
        """
        info_parts = []
        
        if file_data.get('storage_type') == 'telegram_file_id':
            info_parts.append("📡 Stored via Telegram")
        else:
            info_parts.append("💾 Stored locally")
        
        if 'size' in file_data:
            size_mb = file_data['size'] / (1024 * 1024)
            info_parts.append(f"📊 {size_mb:.1f}MB")
        
        if 'width' in file_data and 'height' in file_data:
            info_parts.append(f"📐 {file_data['width']}x{file_data['height']}")
        
        if file_data.get('type') == 'video' and 'duration' in file_data:
            info_parts.append(f"⏱️ {file_data['duration']}s")
        
        if 'mime_type' in file_data:
            info_parts.append(f"🗂️ {file_data['mime_type']}")
        
        if 'original_name' in file_data:
            info_parts.append(f"📄 {file_data['original_name']}")
        
        return " | ".join(info_parts)
    
    # Keep the old method for backward compatibility
    def get_image_info(self, image_data):
        """Backward compatibility - delegates to get_file_info"""
        return self.get_file_info(image_data)
    
    def validate_file_id(self, file_id):
        """
        Validate if a file ID is still accessible
        
        Args:
            file_id: Telegram file ID to validate
            
        Returns:
            bool: True if file ID is valid, False otherwise
        """
        try:
            # Try to get file info
            file_info = self.bot.get_file(file_id)
            return True
        except telebot.apihelper.ApiTelegramException as e:
            if "FILE_REFERENCE_EXPIRED" in str(e) or "file not found" in str(e).lower():
                return False
            else:
                # Other errors might be temporary
                logger.warning(f"Validation error for file ID {file_id}: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error validating file ID {file_id}: {e}")
            return False
