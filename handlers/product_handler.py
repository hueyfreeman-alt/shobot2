import telebot
import logging
import json
import os
import shutil
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class ProductHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.categories_file = 'categories.json'
        self.products_file = 'products.json'
        self.images_dir = 'images'
        self.products_dir = 'products'
        
        # Initialize product creation handler
        from handlers.product_creation_handler import ProductCreationHandler
        self.creation_handler = ProductCreationHandler(bot, db, language, config)
        
        # Initialize product file handler
        from handlers.product_file_handler import ProductFileHandler
        self.file_handler = ProductFileHandler(bot, db, language, config)
    
    def load_categories(self):
        """Load categories from JSON file with caching"""
        try:
            from json_cache import json_cache
            if os.path.exists(self.categories_file):
                data = json_cache.get(self.categories_file)
                return data if data else {"categories": []}
            return {"categories": []}
        except Exception as e:
            logger.error(f"Error loading categories: {e}")
            return {"categories": []}
    
    def load_products(self):
        """Load products from JSON file with caching"""
        try:
            from json_cache import json_cache
            if os.path.exists(self.products_file):
                data = json_cache.get(self.products_file)
                return data if data else {"products": []}
            return {"products": []}
        except Exception as e:
            logger.error(f"Error loading products: {e}")
            return {"products": []}
    
    def get_category_product_count(self, category_id):
        """Get total product count for a category"""
        products_data = self.load_products()
        count = 0
        for product in products_data.get('products', []):
            if (product.get('category_id') == category_id and 
                product.get('status') == 'saved'):
                count += 1
        return count
    
    def get_subcategory_product_count(self, category_id, subcategory_id):
        """Get product count for a subcategory"""
        products_data = self.load_products()
        count = 0
        for product in products_data.get('products', []):
            if (product.get('category_id') == category_id and 
                product.get('subcategory_id') == subcategory_id and 
                product.get('status') == 'saved'):
                count += 1
        return count
    
    def handle_products_management(self, call):
        """Handle main products management screen - show categories"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Clean up any pending products before showing products management
        self.creation_handler.cleanup_pending_products()
        
        # Load categories
        categories_data = self.load_categories()
        categories = categories_data.get('categories', [])
        
        # Get products management text
        menu_text = self.language.get_text('products_management', lang_code)
        
        # Create categories buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        if categories:
            # Add existing categories with product counts
            for category in categories:
                product_count = self.get_category_product_count(category['id'])
                button_text = f"{category['name']} ({product_count})"
                markup.add(telebot.types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f'prod_cat_{category["id"]}'
                ))
        else:
            # No categories message
            no_categories_text = self.language.get_text('no_categories_for_products', lang_code)
            menu_text = no_categories_text
        
        # Add back button
        back_admin_text = self.language.get_text('back_to_admin_panel', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_admin_text,
            callback_data='admin_panel'
        ))
        
        # Edit the message
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=menu_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_product_category_view(self, call):
        """Handle viewing subcategories in a category for products"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract category ID
        category_id = call.data.replace('prod_cat_', '')
        
        # Load categories and find the specific one
        categories_data = self.load_categories()
        category = None
        for cat in categories_data.get('categories', []):
            if cat['id'] == category_id:
                category = cat
                break
        
        if not category:
            self.bot.answer_callback_query(call.id, "❌ Category not found")
            return
        
        # Build category view text
        menu_text = f"<b>📂 {category['name']}</b>\n\nSelect subcategory to manage products:"
        
        subcategories = category.get('subcategories', [])
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        if subcategories:
            # Add subcategory buttons with product counts
            for subcat in subcategories:
                product_count = self.get_subcategory_product_count(category_id, subcat['id'])
                button_text = f"{subcat['name']} ({product_count})"
                markup.add(telebot.types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f'prod_subcat_{category_id}_{subcat["id"]}'
                ))
        else:
            # No subcategories message
            no_subcats_text = self.language.get_text('no_subcategories_for_products', lang_code)
            menu_text = f"<b>📂 {category['name']}</b>\n\n{no_subcats_text}"
        
        # Back button
        back_text = self.language.get_text('back_to_product_categories', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='admin_products'
        ))
        
        # Edit the message
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=menu_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_product_subcategory_view(self, call):
        """Handle viewing products in a subcategory"""
        user_id = call.from_user.id
        
        # Clear any input state when navigating back to product list
        self.db.clear_user_state(user_id)
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract category and subcategory IDs
        parts = call.data.replace('prod_subcat_', '').split('_')
        category_id = parts[0]
        subcategory_id = parts[1]
        
        # Load categories and find the subcategory
        categories_data = self.load_categories()
        category = None
        subcategory = None
        for cat in categories_data.get('categories', []):
            if cat['id'] == category_id:
                category = cat
                for subcat in cat.get('subcategories', []):
                    if subcat['id'] == subcategory_id:
                        subcategory = subcat
                        break
                break
        
        if not category or not subcategory:
            self.bot.answer_callback_query(call.id, "❌ Category/Subcategory not found")
            return
        
        # Load products and filter for this subcategory (only saved products)
        products_data = self.load_products()
        products = [p for p in products_data.get('products', []) 
                   if (p.get('category_id') == category_id and 
                       p.get('subcategory_id') == subcategory_id and 
                       p.get('status') == 'saved')]
        
        # Build subcategory view text
        menu_text = f"<b>📁 {subcategory['name']}</b>\n<i>in {category['name']}</i>\n\n"
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        if products:
            menu_text += f"<b>Products ({len(products)}):</b>\n"
            # Add product buttons with edit options
            for product in products:
                # Product info row
                product_status = "👁️" if product.get('hidden', False) else "✅"
                markup.add(telebot.types.InlineKeyboardButton(
                    text=f"{product_status} {product['name']} - ${product['price']}",
                    callback_data=f'prod_view_{product["id"]}'
                ))
        else:
            # No products message
            no_products_text = self.language.get_text('no_products_found', lang_code)
            menu_text += no_products_text
        
        # Add new product button
        add_new_text = self.language.get_text('add_new_product', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=add_new_text,
            callback_data=f'prod_add_{category_id}_{subcategory_id}'
        ))
        
        # Back button
        back_text = self.language.get_text('back_to_product_subcategories', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data=f'prod_cat_{category_id}'
        ))
        
        # Edit the message
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=menu_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_product_view(self, call):
        """Handle viewing and editing a specific product"""
        user_id = call.from_user.id
        
        # Clear any input state when viewing product (back button effect)
        self.db.clear_user_state(user_id)
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract product ID
        product_id = call.data.replace('prod_view_', '')
        
        # Load products and find the specific one (only saved products)
        products_data = self.load_products()
        product = None
        for prod in products_data.get('products', []):
            if prod['id'] == product_id and prod.get('status') == 'saved':
                product = prod
                break
        
        if not product:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        # Build product view text
        status = "Hidden" if product.get('hidden', False) else "Active"
        reviews_status = "Enabled" if product.get('reviews_enabled', True) else "Disabled"
        menu_text = f"<b>📦 {product['name']}</b>\n\n"
        menu_text += f"🏷️ <b>Code:</b> <code>{product['code']}</code>\n"
        menu_text += f"💰 <b>Price:</b> ${product['price']}\n"
        menu_text += f"📋 <b>Type:</b> {product['type']}\n"
        menu_text += f"📊 <b>Status:</b> {status}\n"
        menu_text += f"📂 <b>Stock/Files:</b> {product.get('stock', 'N/A')}\n"
        menu_text += f"⭐ <b>Reviews:</b> {reviews_status}\n\n"
        menu_text += f"<b>Description:</b>\n{product.get('description', 'No description')}"
        
        # Create edit buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Edit options
        edit_name_text = self.language.get_text('edit_product_name', lang_code)
        edit_code_text = self.language.get_text('edit_product_code', lang_code)
        edit_desc_text = self.language.get_text('edit_product_description', lang_code)
        edit_price_text = self.language.get_text('edit_product_price', lang_code)
        edit_quantity_text = self.language.get_text('edit_product_quantity', lang_code)
        hide_text = self.language.get_text('hide_product', lang_code)
        delete_text = self.language.get_text('delete_product', lang_code)
        change_category_text = self.language.get_text('change_product_category', lang_code)
        
        # Row 1: Edit name, code
        markup.row(
            telebot.types.InlineKeyboardButton(text=edit_name_text, callback_data=f'prod_edit_name_{product_id}'),
            telebot.types.InlineKeyboardButton(text=edit_code_text, callback_data=f'prod_edit_code_{product_id}')
        )
        
        # Row 2: Edit description, price
        markup.row(
            telebot.types.InlineKeyboardButton(text=edit_desc_text, callback_data=f'prod_edit_desc_{product_id}'),
            telebot.types.InlineKeyboardButton(text=edit_price_text, callback_data=f'prod_edit_price_{product_id}')
        )
        
        # Row 3: Edit quantity/upload more based on product type, reviews
        hide_show_text = "👁️ Show" if product.get('hidden', False) else "🙈 Hide"
        edit_reviews_text = self.language.get_text('edit_review_settings', lang_code)
        
        # Different button based on product type
        product_type = product.get('type', 'delivered')
        if product_type == 'delivered':
            # Delivered products can edit quantity
            quantity_button_text = edit_quantity_text
            quantity_callback = f'prod_edit_quantity_{product_id}'
        else:
            # Downloadable and line_file products show "Upload More"
            quantity_button_text = "📤 Upload More"
            quantity_callback = f'prod_upload_more_{product_id}'
        
        markup.row(
            telebot.types.InlineKeyboardButton(text=quantity_button_text, callback_data=quantity_callback),
            telebot.types.InlineKeyboardButton(text=edit_reviews_text, callback_data=f'prod_edit_reviews_{product_id}')
        )
        markup.row(
            telebot.types.InlineKeyboardButton(text=hide_show_text, callback_data=f'prod_toggle_visibility_{product_id}')
        )
        
        # Row 4: Premium features (show alert)
        markup.row(
            telebot.types.InlineKeyboardButton(text=change_category_text, callback_data=f'prod_premium_alert'),
            telebot.types.InlineKeyboardButton(text=delete_text, callback_data=f'prod_delete_{product_id}')
        )
        
        # Back button
        back_text = self.language.get_text('back_to_products', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data=f'prod_subcat_{product["category_id"]}_{product["subcategory_id"]}'
        ))
        
        # Edit the message
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=menu_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_premium_alert(self, call):
        """Show premium feature alert"""
        user = self.db.get_user(call.from_user.id)
        lang_code = user['language_code'] if user else 'en'
        
        alert_text = self.language.get_text('premium_feature_alert', lang_code)
        self.bot.answer_callback_query(call.id, alert_text, show_alert=True)
    
    def handle_add_new_product(self, call):
        """Handle adding a new product - delegate to creation handler"""
        # Delegate to creation handler
        self.creation_handler.start_product_creation(call)
    
    def handle_text_input(self, message):
        """Handle text input - delegate to appropriate handler"""
        # Check if it's a creation process
        if self.creation_handler.handle_text_input(message):
            return True
        
        # Check if it's a file upload process
        if self.file_handler.handle_text_input(message):
            return True
        
        # Check if it's a product editing process
        if self.handle_product_edit_input(message):
            return True
        
        return False
    
    def handle_file_input(self, message):
        """Handle file/photo input - delegate to file handler"""
        return self.file_handler.handle_file_input(message)
    
    def handle_product_edit_input(self, message):
        """Handle text input during product editing"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        # Check if user is in product editing state
        if not user_state or not user_state['state'].startswith('editing_product_'):
            return False
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            return False
        
        try:
            # user_state['data'] is already parsed by database.py
            state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
            lang_code = state_data['lang_code']
            product_id = state_data['product_id']
            edit_type = state_data['edit_type']
        except (json.JSONDecodeError, KeyError):
            return False
        
        user_input = message.text.strip()
        
        # Load products
        products_data = self.load_products()
        product_index = None
        for i, product in enumerate(products_data.get('products', [])):
            if product['id'] == product_id and product.get('status') == 'saved':
                product_index = i
                break
        
        if product_index is None:
            error_text = "❌ Product not found"
            self.bot.send_message(message.chat.id, error_text)
            self.db.clear_user_state(user_id)
            return True
        
        # Validate and update based on edit type
        success = False
        if edit_type == 'name':
            if user_input and len(user_input) <= 100:
                products_data['products'][product_index]['name'] = user_input
                success = True
            else:
                error_text = self.language.get_text('invalid_product_name_error', lang_code)
                self.bot.send_message(message.chat.id, error_text)
                return True
                
        elif edit_type == 'description':
            if user_input and len(user_input) <= 1000:
                products_data['products'][product_index]['description'] = user_input
                success = True
            else:
                error_text = self.language.get_text('invalid_product_description_error', lang_code)
                self.bot.send_message(message.chat.id, error_text)
                return True
                
        elif edit_type == 'code':
            if self.validate_product_code(user_input) and not self.product_code_exists(user_input, exclude_id=product_id):
                # Need to rename folders if code changes
                old_code = products_data['products'][product_index]['code']
                new_code = user_input
                
                if self.rename_product_folders(old_code, new_code):
                    products_data['products'][product_index]['code'] = new_code
                    # Update folder paths
                    products_data['products'][product_index]['folder_paths'] = {
                        'image_folder': f"images/{new_code}",
                        'product_folder': f"products/{new_code}",
                        'temp_image_folder': f"images/temp/{new_code}_*",
                        'temp_product_folder': f"products/temp/{new_code}_*"
                    }
                    success = True
                else:
                    error_text = self.language.get_text('error_renaming_folders', lang_code)
                    self.bot.send_message(message.chat.id, error_text)
                    return True
            else:
                error_text = self.language.get_text('invalid_product_code_error', lang_code)
                self.bot.send_message(message.chat.id, error_text)
                return True
                
        elif edit_type == 'price':
            try:
                price = int(user_input)
                if 1 <= price <= 999999:
                    products_data['products'][product_index]['price'] = price
                    success = True
                else:
                    raise ValueError()
            except ValueError:
                error_text = self.language.get_text('invalid_product_price_error', lang_code)
                self.bot.send_message(message.chat.id, error_text)
                return True
                
        elif edit_type == 'quantity':
            try:
                quantity = int(user_input)
                if quantity >= 0:
                    products_data['products'][product_index]['stock'] = quantity
                    success = True
                else:
                    raise ValueError()
            except ValueError:
                error_text = self.language.get_text('invalid_product_quantity_error', lang_code)
                self.bot.send_message(message.chat.id, error_text)
                return True
        
        if success:
            # Save changes
            if self.save_products(products_data):
                self.db.clear_user_state(user_id)
                success_text = self.language.get_text('product_updated_success', lang_code)
                self.bot.send_message(message.chat.id, success_text)
                
                # Return to product view
                from types import SimpleNamespace
                fake_call = SimpleNamespace()
                fake_call.data = f'prod_view_{product_id}'
                fake_call.from_user = message.from_user
                fake_call.message = message
                fake_call.id = None
                self.handle_product_view(fake_call)
            else:
                error_text = self.language.get_text('error_saving_changes', lang_code)
                self.bot.send_message(message.chat.id, error_text)
        
        # Delete user's input message
        try:
            self.bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
            
        return True
    
    def validate_product_code(self, code):
        """Validate product code format"""
        if not code or len(code) > 50:
            return False
        import re
        return re.match(r'^[a-zA-Z0-9_-]+$', code) is not None
    
    def product_code_exists(self, code, exclude_id=None):
        """Check if product code already exists"""
        products_data = self.load_products()
        for product in products_data.get('products', []):
            if (product.get('code') == code and 
                product.get('status') == 'saved' and 
                product.get('id') != exclude_id):
                return True
        return False
    
    def save_products(self, data):
        """Save products to JSON file"""
        try:
            with open(self.products_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info("Products saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving products: {e}")
            return False
    
    def rename_product_folders(self, old_code, new_code):
        """Rename product folders when code changes"""
        import shutil
        try:
            # Rename image folder
            old_image_path = os.path.join(self.images_dir, old_code)
            new_image_path = os.path.join(self.images_dir, new_code)
            if os.path.exists(old_image_path):
                shutil.move(old_image_path, new_image_path)
            
            # Rename product folder
            old_product_path = os.path.join(self.products_dir, old_code)
            new_product_path = os.path.join(self.products_dir, new_code)
            if os.path.exists(old_product_path):
                shutil.move(old_product_path, new_product_path)
            
            return True
        except Exception as e:
            logger.error(f"Error renaming folders: {e}")
            return False
    
    def handle_product_edit_buttons(self, call):
        """Handle product edit button clicks"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract edit type and product ID
        # Format: prod_edit_name_12345678
        parts = call.data.split('_')
        if len(parts) < 4:
            return
        
        edit_type = parts[2]  # name, code, desc, price, quantity, reviews
        product_id = parts[3]
        
        # Special handling for reviews (uses buttons, not text input)
        if edit_type == 'reviews':
            self.handle_reviews_edit(call, product_id, lang_code)
            return
        
        # Set editing state
        self.db.set_user_state(
            user_id=user_id,
            state=f'editing_product_{edit_type}',
            data=json.dumps({
                'lang_code': lang_code,
                'product_id': product_id,
                'edit_type': edit_type
            })
        )
        
        # Send prompt message based on edit type (language-specific)
        prompts = {
            'name': self.language.get_text('enter_product_name_prompt', lang_code),
            'code': self.language.get_text('enter_product_code_prompt', lang_code),
            'desc': self.language.get_text('enter_product_description_prompt', lang_code),
            'price': self.language.get_text('enter_product_price_prompt', lang_code),
            'quantity': self.language.get_text('enter_product_quantity_prompt', lang_code)
        }
        
        prompt_text = prompts.get(edit_type, self.language.get_text('enter_new_value', lang_code))
        
        # Create back button
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_button', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=f"🔙 {back_text}",
            callback_data=f'prod_view_{product_id}'
        ))
        
        self.bot.send_message(
            chat_id=call.message.chat.id,
            text=prompt_text,
            reply_markup=markup
        )
        
        self.bot.answer_callback_query(call.id)
    
    def handle_product_visibility_toggle(self, call):
        """Handle product visibility toggle"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Extract product ID
        product_id = call.data.replace('prod_toggle_visibility_', '')
        
        # Load products
        products_data = self.load_products()
        product_index = None
        for i, product in enumerate(products_data.get('products', [])):
            if product['id'] == product_id and product.get('status') == 'saved':
                product_index = i
                break
        
        if product_index is None:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        # Toggle visibility
        current_hidden = products_data['products'][product_index].get('hidden', False)
        products_data['products'][product_index]['hidden'] = not current_hidden
        
        # Save changes
        if self.save_products(products_data):
            status = "hidden" if not current_hidden else "visible"
            self.bot.answer_callback_query(call.id, f"✅ Product is now {status}")
            
            # Refresh product view
            self.handle_product_view(call)
        else:
            self.bot.answer_callback_query(call.id, "❌ Error updating product")
    
    def handle_product_delete(self, call):
        """Handle product deletion"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Extract product ID
        product_id = call.data.replace('prod_delete_', '')
        
        # Load products
        products_data = self.load_products()
        product_index = None
        product = None
        for i, prod in enumerate(products_data.get('products', [])):
            if prod['id'] == product_id and prod.get('status') == 'saved':
                product_index = i
                product = prod
                break
        
        if product_index is None:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        # Show confirmation dialog
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("✅ Yes, Delete", callback_data=f'prod_confirm_delete_{product_id}'),
            telebot.types.InlineKeyboardButton("❌ Cancel", callback_data=f'prod_view_{product_id}')
        )
        
        confirmation_text = f"⚠️ <b>Delete Product?</b>\n\n"
        confirmation_text += f"<b>Name:</b> {product['name']}\n"
        confirmation_text += f"<b>Code:</b> {product['code']}\n\n"
        confirmation_text += "This action cannot be undone!"
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=confirmation_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        self.bot.answer_callback_query(call.id)
    
    def handle_product_confirm_delete(self, call):
        """Handle confirmed product deletion"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Extract product ID
        product_id = call.data.replace('prod_confirm_delete_', '')
        
        # Load products
        products_data = self.load_products()
        product_index = None
        product = None
        for i, prod in enumerate(products_data.get('products', [])):
            if prod['id'] == product_id and prod.get('status') == 'saved':
                product_index = i
                product = prod
                break
        
        if product_index is None:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        # Delete product folders
        product_code = product['code']
        import shutil
        try:
            # Delete image folder
            image_folder = os.path.join(self.images_dir, product_code)
            if os.path.exists(image_folder):
                shutil.rmtree(image_folder)
            
            # Delete product folder
            product_folder = os.path.join(self.products_dir, product_code)
            if os.path.exists(product_folder):
                shutil.rmtree(product_folder)
                
        except Exception as e:
            logger.error(f"Error deleting product folders: {e}")
        
        # Remove from JSON
        del products_data['products'][product_index]
        
        # Save changes
        if self.save_products(products_data):
            self.bot.answer_callback_query(call.id, "✅ Product deleted successfully!")
            
            # Return to subcategory view
            category_id = product['category_id']
            subcategory_id = product['subcategory_id']
            call.data = f'prod_subcat_{category_id}_{subcategory_id}'
            self.handle_product_subcategory_view(call)
        else:
            self.bot.answer_callback_query(call.id, "❌ Error deleting product")
    
    def handle_set_reviews(self, call):
        """Handle setting review status for existing products"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Extract setting and product ID from callback data
        # Format: prod_set_reviews_true_12345678 or prod_set_reviews_false_12345678
        parts = call.data.split('_')
        if len(parts) < 5:
            return
        
        reviews_enabled = parts[3] == 'true'
        product_id = parts[4]
        
        # Load products
        products_data = self.load_products()
        product_index = None
        for i, product in enumerate(products_data.get('products', [])):
            if product['id'] == product_id and product.get('status') == 'saved':
                product_index = i
                break
        
        if product_index is None:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        # Update review setting
        products_data['products'][product_index]['reviews_enabled'] = reviews_enabled
        
        # Save changes
        if self.save_products(products_data):
            status = "enabled" if reviews_enabled else "disabled"
            self.bot.answer_callback_query(call.id, f"✅ Reviews {status}")
            
            # Refresh product view
            self.handle_product_view(call)
        else:
            self.bot.answer_callback_query(call.id, "❌ Error updating reviews setting")
    
    def handle_reviews_edit(self, call, product_id, lang_code):
        """Handle review settings edit"""
        # Load product
        products_data = self.load_products()
        product = None
        for prod in products_data.get('products', []):
            if prod['id'] == product_id and prod.get('status') == 'saved':
                product = prod
                break
        
        if not product:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        current_reviews = product.get('reviews_enabled', True)
        
        # Create review settings buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        enable_text = self.language.get_text('enable_reviews', lang_code)
        disable_text = self.language.get_text('disable_reviews', lang_code)
        
        # Show both options with current selection highlighted
        if current_reviews:
            enable_button = f"✅ {enable_text}"
            disable_button = disable_text
        else:
            enable_button = enable_text
            disable_button = f"✅ {disable_text}"
        
        markup.add(telebot.types.InlineKeyboardButton(
            text=enable_button,
            callback_data=f'prod_set_reviews_true_{product_id}'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text=disable_button,
            callback_data=f'prod_set_reviews_false_{product_id}'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text="🔙 Back",
            callback_data=f'prod_view_{product_id}'
        ))
        
        review_settings_text = self.language.get_text('review_settings_title', lang_code)
        product_label = self.language.get_text('product_label', lang_code)
        current_setting_label = self.language.get_text('current_setting_label', lang_code)
        choose_setting_text = self.language.get_text('choose_review_setting', lang_code)
        
        enabled_text = self.language.get_text('enabled', lang_code)
        disabled_text = self.language.get_text('disabled', lang_code)
        
        review_text = f"⭐ <b>{review_settings_text}</b>\n\n"
        review_text += f"<b>{product_label}:</b> {product['name']}\n\n"
        review_text += f"<b>{current_setting_label}:</b> {enabled_text if current_reviews else disabled_text}\n\n"
        review_text += choose_setting_text
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=review_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        self.bot.answer_callback_query(call.id)
    
    def handle_upload_more(self, call):
        """Handle upload more files for downloadable/line products"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract product ID
        product_id = call.data.replace('prod_upload_more_', '')
        
        # Load product to check type
        products_data = self.load_products()
        product = None
        for p in products_data.get('products', []):
            if p['id'] == product_id:
                product = p
                break
        
        if not product:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        product_type = product.get('type', 'delivered')
        
        if product_type == 'line_file':
            # Set state for uploading more lines
            self.db.set_user_state(
                user_id=user_id,
                state='uploading_more_lines',
                data=json.dumps({
                    'lang_code': lang_code,
                    'product_id': product_id
                })
            )
            
            # Send message asking for new file
            message_text = f"📤 <b>Upload More Lines</b>\n\n<b>Product:</b> {product['name']}\n<b>Current Stock:</b> {product.get('stock', 0)} lines\n\n📄 <b>Upload a .txt file</b> with additional lines.\nEach line will be added to the existing stock.\n\n<b>Format:</b>\n<code>new-account1:password1\nnew-account2:password2\nnew-license-key-789</code>"
            
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=message_text,
                parse_mode='HTML'
            )
            
            self.bot.answer_callback_query(call.id, "📤 Upload your .txt file now")
        else:
            # For downloadable products, show coming soon message
            self.bot.answer_callback_query(
                call.id, 
                "📤 Upload More for downloadable products will be implemented soon!",
                show_alert=True
            )
