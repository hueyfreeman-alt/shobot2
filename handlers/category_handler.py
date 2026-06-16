import telebot
import logging
import json
import os
import uuid
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class CategoryHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.categories_file = 'categories.json'
    
    def load_categories(self):
        """Load categories from JSON file"""
        try:
            if os.path.exists(self.categories_file):
                with open(self.categories_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # Create default structure if file doesn't exist
                default_data = {"categories": []}
                self.save_categories(default_data)
                return default_data
        except Exception as e:
            logger.error(f"Error loading categories: {e}")
            return {"categories": []}
    
    def save_categories(self, data):
        """Save categories to JSON file"""
        try:
            with open(self.categories_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info("Categories saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving categories: {e}")
            return False
    
    def handle_categories_management(self, call):
        """Handle main categories management screen"""
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
        
        # Load categories
        categories_data = self.load_categories()
        categories = categories_data.get('categories', [])
        
        # Get categories management text
        menu_text = self.language.get_text('categories_management', lang_code)
        
        # Create categories buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        if categories:
            # Add existing categories
            for category in categories:
                markup.add(telebot.types.InlineKeyboardButton(
                    text=category['name'],
                    callback_data=f'cat_view_{category["id"]}'
                ))
        else:
            # No categories message
            no_categories_text = self.language.get_text('no_categories_found', lang_code)
            menu_text += f"\n\n{no_categories_text}"
        
        # Add new category button
        add_new_text = self.language.get_text('add_new_category', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=add_new_text,
            callback_data='cat_add_new'
        ))
        
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
        # Answer callback query (only if it's a real callback)
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_categories_management_for_message(self, message, lang_code):
        """Handle categories management from a message (not callback)"""
        # Load categories
        categories_data = self.load_categories()
        categories = categories_data.get('categories', [])
        
        # Get categories management text
        menu_text = self.language.get_text('categories_management', lang_code)
        
        # Create categories buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        if categories:
            # Add existing categories
            for category in categories:
                markup.add(telebot.types.InlineKeyboardButton(
                    text=category['name'],
                    callback_data=f'cat_view_{category["id"]}'
                ))
        else:
            # No categories message
            no_categories_text = self.language.get_text('no_categories_found', lang_code)
            menu_text += f"\n\n{no_categories_text}"
        
        # Add new category button
        add_new_text = self.language.get_text('add_new_category', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=add_new_text,
            callback_data='cat_add_new'
        ))
        
        # Add back button
        back_admin_text = self.language.get_text('back_to_admin_panel', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_admin_text,
            callback_data='admin_panel'
        ))
        
        # Send new message
        self.bot.send_message(
            chat_id=message.chat.id,
            text=menu_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def handle_category_view_for_message(self, call, lang_code):
        """Handle category view for a message (not callback) - sends new message instead of editing"""
        user_id = call.from_user.id
        
        # Extract category ID
        category_id = call.data.replace('cat_view_', '')
        
        # Load categories and find the specific one
        categories_data = self.load_categories()
        category = None
        for cat in categories_data.get('categories', []):
            if cat['id'] == category_id:
                category = cat
                break
        
        if not category:
            return
        
        # Build category view text
        menu_text = f"<b>📂 {category['name']}</b>\n\n"
        
        subcategories = category.get('subcategories', [])
        if subcategories:
            menu_text += "<b>Subcategories:</b>\n"
            for subcat in subcategories:
                menu_text += f"• {subcat['name']}\n"
        else:
            no_subcats_text = self.language.get_text('no_subcategories_found', lang_code)
            menu_text += no_subcats_text
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add subcategory buttons with edit/delete options if they exist
        if subcategories:
            for subcat in subcategories:
                # Create a row with subcategory name and edit/delete buttons
                markup.row(
                    telebot.types.InlineKeyboardButton(
                        text=subcat['name'],
                        callback_data=f'subcat_view_{category_id}_{subcat["id"]}'
                    ),
                    telebot.types.InlineKeyboardButton(
                        text="✏️",
                        callback_data=f'subcat_edit_{category_id}_{subcat["id"]}'
                    ),
                    telebot.types.InlineKeyboardButton(
                        text="🗑️",
                        callback_data=f'subcat_delete_{category_id}_{subcat["id"]}'
                    )
                )
        
        # Management buttons
        edit_text = self.language.get_text('edit_category', lang_code)
        delete_text = self.language.get_text('delete_category', lang_code)
        add_subcat_text = self.language.get_text('add_new_subcategory', lang_code)
        
        markup.row(
            telebot.types.InlineKeyboardButton(
                text=edit_text,
                callback_data=f'cat_edit_{category_id}'
            ),
            telebot.types.InlineKeyboardButton(
                text=delete_text,
                callback_data=f'cat_delete_{category_id}'
            )
        )
        
        markup.add(telebot.types.InlineKeyboardButton(
            text=add_subcat_text,
            callback_data=f'subcat_add_{category_id}'
        ))
        
        # Back button
        back_text = self.language.get_text('back_to_categories', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='admin_categories'
        ))
        
        # Send new message instead of editing
        self.bot.send_message(
            chat_id=call.message.chat.id,
            text=menu_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def handle_category_view(self, call):
        """Handle viewing a specific category with subcategories"""
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
        category_id = call.data.replace('cat_view_', '')
        
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
        menu_text = f"<b>📂 {category['name']}</b>\n\n"
        
        subcategories = category.get('subcategories', [])
        if subcategories:
            menu_text += "<b>Subcategories:</b>\n"
            for subcat in subcategories:
                menu_text += f"• {subcat['name']}\n"
        else:
            no_subcats_text = self.language.get_text('no_subcategories_found', lang_code)
            menu_text += no_subcats_text
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add subcategory buttons with edit/delete options if they exist
        if subcategories:
            for subcat in subcategories:
                # Create a row with subcategory name and edit/delete buttons
                markup.row(
                    telebot.types.InlineKeyboardButton(
                        text=subcat['name'],
                        callback_data=f'subcat_view_{category_id}_{subcat["id"]}'
                    ),
                    telebot.types.InlineKeyboardButton(
                        text="✏️",
                        callback_data=f'subcat_edit_{category_id}_{subcat["id"]}'
                    ),
                    telebot.types.InlineKeyboardButton(
                        text="🗑️",
                        callback_data=f'subcat_delete_{category_id}_{subcat["id"]}'
                    )
                )
        
        # Management buttons
        edit_text = self.language.get_text('edit_category', lang_code)
        delete_text = self.language.get_text('delete_category', lang_code)
        add_subcat_text = self.language.get_text('add_new_subcategory', lang_code)
        
        markup.row(
            telebot.types.InlineKeyboardButton(
                text=edit_text,
                callback_data=f'cat_edit_{category_id}'
            ),
            telebot.types.InlineKeyboardButton(
                text=delete_text,
                callback_data=f'cat_delete_{category_id}'
            )
        )
        
        markup.add(telebot.types.InlineKeyboardButton(
            text=add_subcat_text,
            callback_data=f'subcat_add_{category_id}'
        ))
        
        # Back button
        back_text = self.language.get_text('back_to_categories', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='admin_categories'
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
        # Answer callback query (only if it's a real callback)
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_add_new_category(self, call):
        """Handle adding a new category"""
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
        
        # Get prompt text
        prompt_text = self.language.get_text('category_name_prompt', lang_code)
        
        # Create back button
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_categories', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='cat_back_to_categories'
        ))
        
        # Set user state for input handling
        self.db.set_user_state(
            user_id=user_id,
            state='adding_category',
            data=lang_code,
            message_id=call.message.message_id
        )
        
        # Edit the message to show prompt
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=prompt_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        # Answer callback query (only if it's a real callback)
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_add_new_subcategory(self, call):
        """Handle adding a new subcategory"""
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
        category_id = call.data.replace('subcat_add_', '')
        
        # Load categories and find the parent category
        categories_data = self.load_categories()
        parent_category = None
        for cat in categories_data.get('categories', []):
            if cat['id'] == category_id:
                parent_category = cat
                break
        
        if not parent_category:
            self.bot.answer_callback_query(call.id, "❌ Parent category not found")
            return
        
        # Get prompt text with parent category name
        prompt_template = self.language.get_text('subcategory_name_prompt', lang_code)
        prompt_text = prompt_template.format(parent_name=parent_category['name'])
        
        # Create back button
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_category', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data=f'cat_back_to_category_{category_id}'
        ))
        
        # Set user state for input handling
        self.db.set_user_state(
            user_id=user_id,
            state=f'adding_subcategory_{category_id}',
            data=lang_code,
            message_id=call.message.message_id
        )
        
        # Edit the message to show prompt
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=prompt_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        # Answer callback query (only if it's a real callback)
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_edit_category(self, call):
        """Handle editing a category"""
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
        category_id = call.data.replace('cat_edit_', '')
        
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
        
        # Get prompt text with current name
        prompt_template = self.language.get_text('edit_category_name', lang_code)
        prompt_text = prompt_template.format(current_name=category['name'])
        
        # Create back button
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_category', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data=f'cat_back_to_category_{category_id}'
        ))
        
        # Set user state for input handling
        self.db.set_user_state(
            user_id=user_id,
            state=f'editing_category_{category_id}',
            data=lang_code,
            message_id=call.message.message_id
        )
        
        # Edit the message to show prompt
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=prompt_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        # Answer callback query (only if it's a real callback)
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_delete_category(self, call):
        """Handle category deletion confirmation"""
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
        category_id = call.data.replace('cat_delete_', '')
        
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
        
        # Get confirmation text
        confirm_template = self.language.get_text('confirm_delete_category', lang_code)
        confirm_text = confirm_template.format(category_name=category['name'])
        
        # Create confirmation buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        confirm_delete_text = self.language.get_text('confirm_delete', lang_code)
        cancel_text = self.language.get_text('cancel_delete', lang_code)
        
        markup.row(
            telebot.types.InlineKeyboardButton(
                text=confirm_delete_text,
                callback_data=f'cat_confirm_delete_{category_id}'
            ),
            telebot.types.InlineKeyboardButton(
                text=cancel_text,
                callback_data=f'cat_view_{category_id}'
            )
        )
        
        # Edit the message to show confirmation
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=confirm_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        # Answer callback query (only if it's a real callback)
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_confirm_delete_category(self, call):
        """Handle confirmed category deletion"""
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
        category_id = call.data.replace('cat_confirm_delete_', '')
        
        # Load categories
        categories_data = self.load_categories()
        categories = categories_data.get('categories', [])
        
        # Remove the category
        updated_categories = [cat for cat in categories if cat['id'] != category_id]
        categories_data['categories'] = updated_categories
        
        # Save updated categories
        if self.save_categories(categories_data):
            # Show success message
            success_text = self.language.get_text('category_deleted_success', lang_code)
            self.bot.answer_callback_query(call.id, success_text, show_alert=True)
            
            # Return to categories management
            self.handle_categories_management(call)
        else:
            # Show error message
            error_text = self.language.get_text('error_managing_categories', lang_code)
            self.bot.answer_callback_query(call.id, error_text, show_alert=True)
    
    def handle_text_input(self, message):
        """Handle text input when user is in category editing state"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        # Only handle category-related states
        if not user_state:
            return False
        
        state = user_state['state']
        if not (
            state == 'adding_category' or 
            state.startswith('adding_subcategory_') or 
            state.startswith('editing_category_') or
            state.startswith('editing_subcategory_')
        ):
            return False  # Not in category editing state
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            return False
        
        state = user_state['state']
        lang_code = user_state['data']
        new_name = message.text.strip()
        
        # Validate input
        if not new_name or len(new_name) > 50:
            error_text = self.language.get_text('error_managing_categories', lang_code)
            self.bot.send_message(
                chat_id=message.chat.id,
                text=error_text
            )
            return True
        
        # Load categories
        categories_data = self.load_categories()
        success = False
        
        if state == 'adding_category':
            # Add new category
            new_category = {
                "id": str(uuid.uuid4())[:8],
                "name": new_name,
                "subcategories": []
            }
            categories_data['categories'].append(new_category)
            success = self.save_categories(categories_data)
            success_key = 'category_added_success'
            
        elif state.startswith('adding_subcategory_'):
            # Add new subcategory
            category_id = state.replace('adding_subcategory_', '')
            
            # Find parent category
            for category in categories_data['categories']:
                if category['id'] == category_id:
                    new_subcategory = {
                        "id": str(uuid.uuid4())[:8],
                        "name": new_name
                    }
                    category['subcategories'].append(new_subcategory)
                    success = self.save_categories(categories_data)
                    break
            success_key = 'subcategory_added_success'
            
        elif state.startswith('editing_category_'):
            # Edit existing category
            category_id = state.replace('editing_category_', '')
            
            # Find and update category
            for category in categories_data['categories']:
                if category['id'] == category_id:
                    category['name'] = new_name
                    success = self.save_categories(categories_data)
                    break
            success_key = 'category_updated_success'
            
        elif state.startswith('editing_subcategory_'):
            # Edit existing subcategory
            parts = state.replace('editing_subcategory_', '').split('_')
            category_id = parts[0]
            subcategory_id = parts[1]
            
            # Find and update subcategory
            for category in categories_data['categories']:
                if category['id'] == category_id:
                    for subcategory in category.get('subcategories', []):
                        if subcategory['id'] == subcategory_id:
                            subcategory['name'] = new_name
                            success = self.save_categories(categories_data)
                            break
                    break
            success_key = 'category_updated_success'
        
        if success:
            # Clear user state first
            self.db.clear_user_state(user_id)
            
            # Show success message as alert and return to appropriate menu
            success_text = self.language.get_text(success_key, lang_code)
            
            if state == 'adding_category':
                # Return to main categories menu
                self.handle_categories_management_for_message(message, lang_code)
            elif state.startswith('adding_subcategory_') or state.startswith('editing_category_') or state.startswith('editing_subcategory_'):
                # Return to specific category view
                if state.startswith('adding_subcategory_'):
                    category_id = state.replace('adding_subcategory_', '')
                elif state.startswith('editing_category_'):
                    category_id = state.replace('editing_category_', '')
                else:
                    # editing_subcategory_
                    parts = state.replace('editing_subcategory_', '').split('_')
                    category_id = parts[0]
                
                # Create a fake call object to reuse the view handler
                class FakeCall:
                    def __init__(self, message, category_id):
                        self.message = message
                        self.from_user = message.from_user
                        self.data = f'cat_view_{category_id}'
                        self.id = None  # Add missing id attribute
                
                fake_call = FakeCall(message, category_id)
                self.handle_category_view_for_message(fake_call, lang_code)
            
            # Show success alert (but delete the message after a moment)
            success_msg = self.bot.send_message(
                chat_id=message.chat.id,
                text=f"✅ {success_text}",
                parse_mode='HTML'
            )
            
            # Delete the success message after 1 second  
            import threading
            def delete_after_delay():
                import time
                time.sleep(1)
                try:
                    self.bot.delete_message(message.chat.id, success_msg.message_id)
                    # Also delete the user's input message
                    self.bot.delete_message(message.chat.id, message.message_id)
                except:
                    pass
            threading.Thread(target=delete_after_delay).start()
            
        else:
            # Show error message
            error_text = self.language.get_text('error_managing_categories', lang_code)
            self.bot.send_message(
                chat_id=message.chat.id,
                text=error_text
            )
        
        return True  # Input was handled
    
    def handle_edit_subcategory(self, call):
        """Handle editing a subcategory"""
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
        
        # Extract category and subcategory IDs
        parts = call.data.replace('subcat_edit_', '').split('_')
        category_id = parts[0]
        subcategory_id = parts[1]
        
        # Load categories and find the subcategory
        categories_data = self.load_categories()
        subcategory = None
        for cat in categories_data.get('categories', []):
            if cat['id'] == category_id:
                for subcat in cat.get('subcategories', []):
                    if subcat['id'] == subcategory_id:
                        subcategory = subcat
                        break
                break
        
        if not subcategory:
            self.bot.answer_callback_query(call.id, "❌ Subcategory not found")
            return
        
        # Get prompt text with current name
        prompt_template = self.language.get_text('edit_category_name', lang_code)
        prompt_text = prompt_template.format(current_name=subcategory['name'])
        
        # Create back button
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_category', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data=f'cat_back_to_category_{category_id}'
        ))
        
        # Set user state for input handling
        self.db.set_user_state(
            user_id=user_id,
            state=f'editing_subcategory_{category_id}_{subcategory_id}',
            data=lang_code,
            message_id=call.message.message_id
        )
        
        # Edit the message to show prompt
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=prompt_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        # Answer callback query (only if it's a real callback)
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_delete_subcategory(self, call):
        """Handle subcategory deletion confirmation"""
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
        
        # Extract category and subcategory IDs
        parts = call.data.replace('subcat_delete_', '').split('_')
        category_id = parts[0]
        subcategory_id = parts[1]
        
        # Load categories and find the subcategory
        categories_data = self.load_categories()
        subcategory = None
        for cat in categories_data.get('categories', []):
            if cat['id'] == category_id:
                for subcat in cat.get('subcategories', []):
                    if subcat['id'] == subcategory_id:
                        subcategory = subcat
                        break
                break
        
        if not subcategory:
            self.bot.answer_callback_query(call.id, "❌ Subcategory not found")
            return
        
        # Get confirmation text
        confirm_template = self.language.get_text('confirm_delete_category', lang_code)
        confirm_text = confirm_template.format(category_name=subcategory['name'])
        
        # Create confirmation buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        confirm_delete_text = self.language.get_text('confirm_delete', lang_code)
        cancel_text = self.language.get_text('cancel_delete', lang_code)
        
        markup.row(
            telebot.types.InlineKeyboardButton(
                text=confirm_delete_text,
                callback_data=f'subcat_confirm_delete_{category_id}_{subcategory_id}'
            ),
            telebot.types.InlineKeyboardButton(
                text=cancel_text,
                callback_data=f'cat_view_{category_id}'
            )
        )
        
        # Edit the message to show confirmation
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=confirm_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        # Answer callback query (only if it's a real callback)
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_confirm_delete_subcategory(self, call):
        """Handle confirmed subcategory deletion"""
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
        
        # Extract category and subcategory IDs
        parts = call.data.replace('subcat_confirm_delete_', '').split('_')
        category_id = parts[0]
        subcategory_id = parts[1]
        
        # Load categories
        categories_data = self.load_categories()
        
        # Remove the subcategory
        for category in categories_data.get('categories', []):
            if category['id'] == category_id:
                category['subcategories'] = [
                    subcat for subcat in category.get('subcategories', [])
                    if subcat['id'] != subcategory_id
                ]
                break
        
        # Save updated categories
        if self.save_categories(categories_data):
            # Show success message
            success_text = self.language.get_text('category_deleted_success', lang_code)
            self.bot.answer_callback_query(call.id, success_text, show_alert=True)
            
            # Return to category view
            call.data = f'cat_view_{category_id}'
            self.handle_category_view(call)
        else:
            # Show error message
            error_text = self.language.get_text('error_managing_categories', lang_code)
            self.bot.answer_callback_query(call.id, error_text, show_alert=True)
    
    def handle_back_buttons(self, call):
        """Handle various back buttons"""
        if call.data == 'cat_back_to_categories':
            # Clear user state and return to categories
            self.db.clear_user_state(call.from_user.id)
            self.handle_categories_management(call)
            
        elif call.data.startswith('cat_back_to_category_'):
            # Clear user state and return to specific category
            category_id = call.data.replace('cat_back_to_category_', '')
            self.db.clear_user_state(call.from_user.id)
            
            # Create a new call data for category view
            new_call_data = f'cat_view_{category_id}'
            call.data = new_call_data
            self.handle_category_view(call)
