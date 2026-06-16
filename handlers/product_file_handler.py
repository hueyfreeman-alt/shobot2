import telebot
import logging
import json
import os
import uuid
import time
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class ProductFileHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.products_dir = 'products'
        self.images_dir = 'images'
        
        # File size limits
        self.IMAGE_SIZE_LIMIT = 10 * 1024 * 1024  # 10MB for images
        self.PRODUCT_SIZE_LIMIT = 50 * 1024 * 1024  # 50MB for product files
        self.MAX_IMAGES = 5
        
        # Supported file types (all lowercase for consistent comparison)
        self.IMAGE_TYPES = ['jpg', 'jpeg', 'png', 'gif', 'mp4']
        self.PRODUCT_FILE_TYPES = ['txt', 'png', 'jpg', 'jpeg', 'zip', 'rar', 'pdf']
    
    def handle_file_input(self, message):
        """Handle file/photo/video uploads during product creation"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        # Check if user is in a file upload state
        if not user_state or not (
            user_state['state'] == 'creating_product_step_5' or  # Images
            user_state['state'] == 'creating_product_step_7_downloadable' or  # Downloadable files
            user_state['state'] == 'creating_product_step_7_line_file' or  # Line file
            user_state['state'] == 'uploading_more_lines'  # Upload more lines
        ):
            return False
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            return False
        
        try:
            # user_state['data'] is already parsed by database.py
            state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
            lang_code = state_data['lang_code']
            
            # For uploading_more_lines, we don't need product_data
            if user_state['state'] == 'uploading_more_lines':
                return self.handle_upload_more_lines(message, user_id, lang_code, state_data)
            
            # For other states, we need product_data
            product_data = state_data['product_data']
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error parsing state data: {e}")
            return False
        
        # Handle different file types based on current step
        if user_state['state'] == 'creating_product_step_5':
            return self.handle_image_upload(message, user_id, lang_code, product_data)
        elif user_state['state'] == 'creating_product_step_7_downloadable':
            return self.handle_product_file_upload(message, user_id, lang_code, product_data)
        elif user_state['state'] == 'creating_product_step_7_line_file':
            return self.handle_line_file_upload(message, user_id, lang_code, product_data)
        
        return False
    
    def handle_image_upload(self, message, user_id, lang_code, product_data):
        """Handle image/video upload for product images using Telegram file IDs"""
        # Check if we've reached the limit
        if len(product_data['images']) >= self.MAX_IMAGES:
            quota_text = self.language.get_text('quota_exceeded', lang_code)
            formatted_text = quota_text.format(max_count=self.MAX_IMAGES, max_size=10)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        # Get file info based on message type
        file_info = None
        file_name = None
        file_type = None
        
        if message.photo:
            # Get the largest photo size
            file_info = message.photo[-1]
            file_name = f"image_{len(product_data['images'])}.jpg"
            file_type = 'image'
        elif message.video:
            file_info = message.video
            file_name = f"video_{len(product_data['images'])}.mp4"
            file_type = 'video'
        elif message.document:
            file_info = message.document
            original_name = message.document.file_name or f"file_{len(product_data['images'])}"
            file_name = original_name
            
            # Check if document is an image or video by extension
            file_ext = original_name.split('.')[-1].lower() if '.' in original_name else ''
            if file_ext in self.IMAGE_TYPES:
                if file_ext == 'mp4':
                    file_type = 'video'
                else:
                    file_type = 'image'
            else:
                # Invalid file type for images
                invalid_text = self.language.get_text('invalid_file_type', lang_code)
                formatted_text = invalid_text.format(supported_types="JPG, PNG, GIF, MP4")
                self.bot.send_message(message.chat.id, formatted_text)
                return True
        
        if not file_info:
            invalid_text = self.language.get_text('invalid_file_type', lang_code)
            formatted_text = invalid_text.format(supported_types="JPG, PNG, GIF, MP4")
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        # Check file size
        if file_info.file_size > self.IMAGE_SIZE_LIMIT:
            large_text = self.language.get_text('file_too_large', lang_code)
            formatted_text = large_text.format(max_size=10)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        # Calculate total size with existing images
        total_size = sum(img.get('size', 0) for img in product_data['images']) + file_info.file_size
        if total_size > self.IMAGE_SIZE_LIMIT:
            quota_text = self.language.get_text('quota_exceeded', lang_code)
            formatted_text = quota_text.format(max_count=self.MAX_IMAGES, max_size=10)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        # Store file data using Telegram file ID (no download needed!)
        try:
            # Create image data with file ID - no local storage needed
            image_data = {
                'file_id': file_info.file_id,
                'file_unique_id': file_info.file_unique_id,
                'file_name': file_name,
                'size': file_info.file_size,
                'type': file_type,
                'storage_type': 'telegram_file_id',  # Mark as using file ID storage
                'uploaded_at': int(time.time())  # Track when uploaded
            }
            
            # Add additional metadata for different file types
            if file_type == 'image' and message.photo:
                image_data.update({
                    'width': file_info.width,
                    'height': file_info.height
                })
            elif file_type == 'video' and message.video:
                image_data.update({
                    'width': file_info.width,
                    'height': file_info.height,
                    'duration': file_info.duration
                })
            
            product_data['images'].append(image_data)
            
            # Update state
            self.db.set_user_state(
                user_id=user_id,
                state='creating_product_step_5',
                data=json.dumps({
                    'lang_code': lang_code,
                    'product_data': product_data
                })
            )
            
            # Send updated status
            self.send_image_upload_status(message, lang_code, product_data)
            
        except Exception as e:
            logger.error(f"Error handling image upload: {e}")
            error_text = "❌ Error uploading file. Please try again."
            self.bot.send_message(message.chat.id, error_text)
        
        return True
    
    def send_image_upload_status(self, message, lang_code, product_data):
        """Send updated image upload status"""
        total_size = sum(img.get('size', 0) for img in product_data['images'])
        
        step_text = self.language.get_text('product_images_step', lang_code)
        formatted_text = step_text.format(
            product_name=product_data['name'],
            product_code=product_data['code'],
            price=product_data['price'],
            upload_count=len(product_data['images']),
            total_size=self.format_file_size(total_size)
        )
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Proceed button (always available)
        proceed_text = self.language.get_text('proceed_with_images', lang_code)
        formatted_proceed = proceed_text.format(count=len(product_data['images']))
        markup.add(telebot.types.InlineKeyboardButton(
            text=formatted_proceed,
            callback_data='prod_proceed_step_6'
        ))
        
        # Upload more button (if not at limit)
        if len(product_data['images']) < self.MAX_IMAGES:
            more_text = self.language.get_text('upload_more_images', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=more_text,
                callback_data='prod_upload_more_images'
            ))
        
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=formatted_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def handle_product_file_upload(self, message, user_id, lang_code, product_data):
        """Handle product file upload for downloadable products using Telegram file IDs"""
        # Get file info based on message type (accept photo, video, or document)
        file_info = None
        file_name = None
        file_type = None
        
        if message.photo:
            # Get the largest photo size
            file_info = message.photo[-1]
            file_name = f"image_{len(product_data['files'])}.jpg"
            file_type = 'image'
        elif message.video:
            file_info = message.video
            file_name = f"video_{len(product_data['files'])}.mp4"
            file_type = 'video'
        elif message.document:
            file_info = message.document
            file_name = file_info.file_name or f"file_{len(product_data['files'])}"
            file_type = 'document'
        
        if not file_info:
            invalid_text = self.language.get_text('invalid_file_type', lang_code)
            formatted_text = invalid_text.format(supported_types="TXT, PNG, JPG, JPEG, ZIP, RAR, PDF")
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        # Check file type (case-insensitive)
        file_ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
        
        if file_ext not in self.PRODUCT_FILE_TYPES:
            invalid_text = self.language.get_text('invalid_file_type', lang_code)
            formatted_text = invalid_text.format(supported_types="TXT, PNG, JPG, JPEG, ZIP, RAR, PDF")
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        # Check file size
        if file_info.file_size > self.PRODUCT_SIZE_LIMIT:
            large_text = self.language.get_text('file_too_large', lang_code)
            formatted_text = large_text.format(max_size=50)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        # Calculate total size
        total_size = sum(f.get('size', 0) for f in product_data['files']) + file_info.file_size
        if total_size > self.PRODUCT_SIZE_LIMIT:
            quota_text = self.language.get_text('quota_exceeded', lang_code)
            formatted_text = quota_text.format(max_count="unlimited", max_size=50)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        # Store file data using Telegram file ID (no download needed!)
        try:
            # Create file data with file ID - no local storage needed
            file_data = {
                'file_id': file_info.file_id,
                'file_unique_id': file_info.file_unique_id,
                'file_name': file_name,
                'size': file_info.file_size,
                'type': file_ext,
                'storage_type': 'telegram_file_id',  # Mark as using file ID storage
                'uploaded_at': int(time.time())  # Track when uploaded
            }
            
            # Add additional metadata for different file types
            if hasattr(file_info, 'mime_type'):
                file_data['mime_type'] = file_info.mime_type
            
            # For documents, add more metadata if available
            if message.document and hasattr(file_info, 'file_name'):
                file_data['original_name'] = file_info.file_name
                if hasattr(file_info, 'thumb') and file_info.thumb:
                    file_data['has_thumbnail'] = True
                    file_data['thumb_file_id'] = file_info.thumb.file_id
            
            # For videos, add duration and dimensions
            if message.video:
                if hasattr(file_info, 'duration'):
                    file_data['duration'] = file_info.duration
                if hasattr(file_info, 'width') and hasattr(file_info, 'height'):
                    file_data.update({
                        'width': file_info.width,
                        'height': file_info.height
                    })
                if hasattr(file_info, 'thumb') and file_info.thumb:
                    file_data['thumb_file_id'] = file_info.thumb.file_id
            
            product_data['files'].append(file_data)
            
            # Update state
            self.db.set_user_state(
                user_id=user_id,
                state='creating_product_step_7_downloadable',
                data=json.dumps({
                    'lang_code': lang_code,
                    'product_data': product_data
                })
            )
            
            # Send updated status
            self.send_product_file_status(message, lang_code, product_data)
            
        except Exception as e:
            logger.error(f"Error handling product file upload: {e}")
            error_text = "❌ Error uploading file. Please try again."
            self.bot.send_message(message.chat.id, error_text)
        
        return True
    
    def send_product_file_status(self, message, lang_code, product_data):
        """Send updated product file upload status"""
        total_size = sum(f.get('size', 0) for f in product_data['files'])
        
        step_text = self.language.get_text('downloadable_files_step', lang_code)
        formatted_text = step_text.format(
            product_name=product_data['name'],
            upload_count=len(product_data['files']),
            total_size=self.format_file_size(total_size)
        )
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Complete button (if files uploaded)
        if len(product_data['files']) > 0:
            complete_text = self.language.get_text('upload_complete', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=complete_text,
                callback_data='prod_files_complete'
            ))
        
        # Continue uploading button
        continue_text = self.language.get_text('continue_uploading', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=continue_text,
            callback_data='prod_continue_uploading'
        ))
        
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=formatted_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def handle_line_file_upload(self, message, user_id, lang_code, product_data):
        """Handle line-based file upload"""
        if not message.document:
            invalid_text = self.language.get_text('invalid_file_type', lang_code)
            formatted_text = invalid_text.format(supported_types="TXT")
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        file_info = message.document
        file_name = file_info.file_name or "file.txt"
        
        # Check if it's a text file
        file_ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
        if file_ext != 'txt':
            invalid_text = self.language.get_text('invalid_file_type', lang_code)
            formatted_text = invalid_text.format(supported_types="TXT")
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        # Check file size
        if file_info.file_size > self.PRODUCT_SIZE_LIMIT:
            large_text = self.language.get_text('file_too_large', lang_code)
            formatted_text = large_text.format(max_size=50)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        # Download and process the file
        try:
            file_path = self.bot.get_file(file_info.file_id)
            downloaded_file = self.bot.download_file(file_path.file_path)
            
            # Try different encodings to read the file
            content = None
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    content = downloaded_file.decode(encoding)
                    break
                except:
                    continue
            
            # If all encodings fail, use utf-8 with ignore
            if content is None:
                content = downloaded_file.decode('utf-8', errors='ignore')
            
            # Read file content and count lines
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            
            if len(lines) == 0:
                error_text = "❌ File is empty or contains no valid lines."
                self.bot.send_message(message.chat.id, error_text)
                return True
            
            # Create or reuse temp folder for this product
            product_code = product_data.get('code', 'temp')
            
            # Look for existing temp folder for this product code
            temp_base_dir = os.path.join(self.products_dir, 'temp')
            os.makedirs(temp_base_dir, exist_ok=True)
            
            temp_folder = None
            temp_folder_name = None
            
            # Try to find existing temp folder for this product
            if os.path.exists(temp_base_dir):
                for folder_name in os.listdir(temp_base_dir):
                    if folder_name.startswith(f"{product_code}_"):
                        temp_folder_name = folder_name
                        temp_folder = os.path.join(temp_base_dir, folder_name)
                        break
            
            # If no existing folder found, create new one
            if not temp_folder:
                unix_time = int(time.time())
                temp_folder_name = f"{product_code}_{unix_time}"
                temp_folder = os.path.join(temp_base_dir, temp_folder_name)
                os.makedirs(temp_folder, exist_ok=True)
            
            # Convert to JSON format where each line is a separate product entry
            json_file_name = file_name.replace('.txt', '.json')
            local_path = os.path.join(temp_folder, json_file_name)
            
            # Create JSON structure with each line as a product entry
            json_data = {
                'total_products': len(lines),
                'products': []
            }
            
            for i, line in enumerate(lines, 1):
                product_entry = {
                    'id': i,
                    'content': line,
                    'status': 'available'
                }
                json_data['products'].append(product_entry)
            
            # Save as JSON file
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            # Add to product data (store relative path)
            relative_path = os.path.join('products', 'temp', temp_folder_name, json_file_name)
            file_data = {
                'file_id': file_info.file_id,
                'file_name': json_file_name,
                'original_file_name': file_name,
                'local_path': local_path,
                'relative_path': relative_path,
                'size': file_info.file_size,
                'type': 'json',
                'line_count': len(lines)
            }
            product_data['files'] = [file_data]  # Only one file for line-based products
            product_data['stock'] = len(lines)
            
            # Update state and proceed to summary
            self.db.set_user_state(
                user_id=user_id,
                state='creating_product_summary',
                data=json.dumps({
                    'lang_code': lang_code,
                    'product_data': product_data
                })
            )
            
            # Import and use creation handler to proceed to review settings
            from handlers.product_creation_handler import ProductCreationHandler
            creation_handler = ProductCreationHandler(self.bot, self.db, self.language, self.config)
            creation_handler.proceed_to_review_settings(message, user_id, lang_code, product_data)
            
        except Exception as e:
            import traceback
            logger.error(f"Error handling line file upload: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            error_text = f"❌ Error processing file: {str(e)}\n\nPlease ensure:\n• File is a valid .txt file\n• File contains at least one line\n• File is not corrupted\n• File uses standard text encoding"
            self.bot.send_message(message.chat.id, error_text)
        
        return True
    
    def handle_upload_more_lines(self, message, user_id, lang_code, state_data):
        """Handle uploading more lines to an existing line-based product"""
        if not message.document:
            error_text = "❌ Please upload a .txt file"
            self.bot.send_message(message.chat.id, error_text)
            return True
        
        file_info = message.document
        file_name = file_info.file_name or "file.txt"
        
        # Check if it's a text file
        file_ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
        if file_ext != 'txt':
            error_text = "❌ Only .txt files are supported"
            self.bot.send_message(message.chat.id, error_text)
            return True
        
        # Check file size
        if file_info.file_size > self.PRODUCT_SIZE_LIMIT:
            error_text = f"❌ File too large. Maximum size: 50MB"
            self.bot.send_message(message.chat.id, error_text)
            return True
        
        try:
            # Get product ID from state
            product_id = state_data.get('product_id')
            
            # Load products data
            products_data = self.load_products()
            product = None
            product_index = None
            
            for i, p in enumerate(products_data.get('products', [])):
                if p['id'] == product_id:
                    product = p
                    product_index = i
                    break
            
            if not product:
                error_text = "❌ Product not found"
                self.bot.send_message(message.chat.id, error_text)
                self.db.clear_user_state(user_id)
                return True
            
            # Download and read the new file
            file_path = self.bot.get_file(file_info.file_id)
            downloaded_file = self.bot.download_file(file_path.file_path)
            
            # Try different encodings
            content = None
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    content = downloaded_file.decode(encoding)
                    break
                except:
                    continue
            
            if content is None:
                content = downloaded_file.decode('utf-8', errors='ignore')
            
            # Parse new lines
            new_lines = [line.strip() for line in content.split('\n') if line.strip()]
            
            if len(new_lines) == 0:
                error_text = "❌ File is empty or contains no valid lines"
                self.bot.send_message(message.chat.id, error_text)
                return True
            
            # Load existing JSON file
            files = product.get('files', [])
            if not files:
                error_text = "❌ Product has no existing data file"
                self.bot.send_message(message.chat.id, error_text)
                self.db.clear_user_state(user_id)
                return True
            
            file_data = files[0]
            json_file_path = file_data.get('local_path') or file_data.get('relative_path')
            
            if not json_file_path or not os.path.exists(json_file_path):
                error_text = f"❌ Product data file not found: {json_file_path}"
                self.bot.send_message(message.chat.id, error_text)
                self.db.clear_user_state(user_id)
                return True
            
            # Read existing JSON
            with open(json_file_path, 'r', encoding='utf-8') as f:
                line_data = json.load(f)
            
            # Get current max ID
            existing_products = line_data.get('products', [])
            max_id = max([p.get('id', 0) for p in existing_products]) if existing_products else 0
            
            # Add new lines with incremented IDs
            for i, line_content in enumerate(new_lines, start=1):
                new_product_entry = {
                    'id': max_id + i,
                    'content': line_content,
                    'status': 'available'
                }
                existing_products.append(new_product_entry)
            
            # Update JSON data
            line_data['products'] = existing_products
            line_data['total_products'] = len(existing_products)
            
            # Save updated JSON file
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(line_data, f, indent=2, ensure_ascii=False)
            
            # Update stock in products.json
            new_stock = product.get('stock', 0) + len(new_lines)
            products_data['products'][product_index]['stock'] = new_stock
            
            # Update file line_count
            products_data['products'][product_index]['files'][0]['line_count'] = line_data['total_products']
            
            # Save products.json
            save_json_safely('products.json', products_data)
            
            # Clear user state
            self.db.clear_user_state(user_id)
            
            # Send success message
            success_text = f"✅ <b>Successfully added {len(new_lines)} lines!</b>\n\n<b>Product:</b> {product['name']}\n<b>Previous Stock:</b> {product.get('stock', 0)} lines\n<b>New Stock:</b> {new_stock} lines\n<b>Total Lines:</b> {line_data['total_products']}"
            
            self.bot.send_message(
                message.chat.id,
                success_text,
                parse_mode='HTML'
            )
            
            logger.info(f"Added {len(new_lines)} lines to product {product_id}. New stock: {new_stock}")
            
        except Exception as e:
            import traceback
            logger.error(f"Error uploading more lines: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            error_text = f"❌ Error processing file: {str(e)}"
            self.bot.send_message(message.chat.id, error_text)
            self.db.clear_user_state(user_id)
        
        return True
    
    def handle_text_input(self, message):
        """Handle text input during file upload states"""
        # This handler doesn't process text input, only files
        return False
    
    def load_products(self):
        """Load products from JSON file"""
        try:
            with open('products.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading products: {e}")
            return {'products': []}
    
    def format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        elif size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
