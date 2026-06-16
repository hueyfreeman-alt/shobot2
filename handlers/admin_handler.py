import telebot
import logging
import json
import os
from performance_optimizations import handler_operation
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class AdminHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.category_handler = None  # Will be set later
        self.product_handler = None  # Will be set later
        self.currency_handler = None  # Will be set later
        self.payment_handler = None  # Will be set later
    
    def handle_admin_panel(self, call):
        """Handle admin panel callback"""
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
        
        # Get admin panel welcome message
        welcome_text = self.language.get_text('admin_panel_welcome', lang_code)
        
        # Create admin menu buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add admin action buttons with dynamic currency button
        admin_buttons = self.language.get_admin_buttons(lang_code)
        for button_row in admin_buttons:
            row_buttons = []
            for btn in button_row:
                button_text = btn['text']
                callback_data = btn['callback_data']
                
                # If it's the currency button, add current currency symbol
                if callback_data == 'admin_currency_settings':
                    current_currency = self.config.get('currency', {'symbol': '$'})
                    button_text = f"{button_text}: {current_currency['symbol']}"
                
                row_buttons.append(telebot.types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=callback_data
                ))
            markup.row(*row_buttons)
        
        # Add back to main menu button
        back_text = self.language.get_text('back_to_menu', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
        # Edit the message
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=welcome_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            # If editing fails, send a new message
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=welcome_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")
    
    def handle_admin_buttons(self, call):
        """Handle admin button clicks with new ID-based system"""
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
        
        # Extract button ID from callback data
        button_id = call.data.replace('admin_', '')
        
        # Handle different admin options based on ID
        if button_id == 'store_settings':
            self.show_store_settings_menu(call, lang_code)
            return
        elif button_id == 'categories':
            # Call the category handler directly
            if self.category_handler:
                self.category_handler.handle_categories_management(call)
            else:
                self.bot.answer_callback_query(call.id, "❌ Category handler not available")
            return
        elif button_id == 'products':
            # Products are handled by the product handler
            if self.product_handler:
                self.product_handler.handle_products_management(call)
            else:
                self.bot.answer_callback_query(call.id, "❌ Product handler not available")
            return
        elif button_id == 'order_management':
            # Order management is handled by the order management handler
            if hasattr(self, 'order_management_handler') and self.order_management_handler:
                self.order_management_handler.handle_order_management(call)
            else:
                self.bot.answer_callback_query(call.id, "❌ Order management handler not available")
            return
        elif button_id == 'admin_disputes':
            # Dispute management is handled by the dispute handler
            if hasattr(self, 'dispute_handler') and self.dispute_handler:
                self.dispute_handler.show_admin_disputes(call)
            else:
                self.bot.answer_callback_query(call.id, "❌ Dispute handler not available")
            return
        elif button_id == 'edit_buttons':
            # Button editor is handled by the button editor handler
            if hasattr(self, 'button_editor_handler') and self.button_editor_handler:
                self.button_editor_handler.handle_export_buttons(call)
            else:
                self.bot.answer_callback_query(call.id, "❌ Button editor not available")
            return
        elif button_id == 'currency_settings':
            # Currency settings are handled by the currency handler
            if self.currency_handler:
                self.currency_handler.handle_currency_settings(call)
            else:
                self.bot.answer_callback_query(call.id, "❌ Currency handler not available")
            return
        elif button_id == 'language_settings':
            response_text = f"🌐 <b>Language Settings</b>\n\n🔤 <i>Manage bot languages</i>\n\n<b>Available Languages:</b>\n• 🇺🇸 English (Active)\n• 🇪🇸 Español (Active)\n• 🇫🇷 Français (Active)\n• 🇩🇪 Deutsch (Active)\n\n<b>Language Management:</b>\n• ➕ Add new languages\n• ✏️ Edit translations\n• 🔧 Set default language\n• 📊 Usage statistics\n\n<i>Advanced language management coming soon!</i>"
            
            # Add Coming Soon button
            markup = telebot.types.InlineKeyboardMarkup()
            coming_soon_text = self.language.get_text('coming_soon', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=coming_soon_text,
                callback_data='coming_soon_feature'
            ))
            
            # Add back buttons
            back_admin_text = self.language.get_text('back_to_admin_panel', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_admin_text,
                callback_data='admin_panel'
            ))
            
            back_text = self.language.get_text('back_to_menu', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_text,
                callback_data='main_menu'
            ))
            
            # Edit the message
            try:
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=response_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                self.bot.send_message(
                    chat_id=call.message.chat.id,
                    text=response_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            
            # Answer callback query
            self.bot.answer_callback_query(call.id)
            return
        elif button_id == 'statistics':
            # Show upgrade alert instead of statistics
            upgrade_alert_text = self.language.get_text('upgrade_bot_alert', lang_code)
            self.bot.answer_callback_query(call.id, upgrade_alert_text, show_alert=True)
            return
        elif button_id == 'setup_payment':
            self.show_payment_setup(call, lang_code)
            return
        elif button_id == 'setup_admin':
            self.show_admin_setup(call, lang_code)
            return
        else:
            response_text = f"🔧 <b>Admin Function</b>\n\nYou selected: {button_id.replace('_', ' ').title()}\n\nThis admin feature will be implemented soon!"
        
        # Add back buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Back to admin panel button
        back_admin_text = self.language.get_text('back_to_admin_panel', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_admin_text,
            callback_data='admin_panel'
        ))
        
        # Back to main menu button
        back_text = self.language.get_text('back_to_menu', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
        # Edit the message
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=response_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=response_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")
    
    def handle_admin_panel_keyboard(self, message):
        """Handle admin panel keyboard button press"""
        user_id = message.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.send_message(message.chat.id, "❌ Access denied! Admin only.")
            return
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.send_message(message.chat.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Get admin panel welcome message
        welcome_text = self.language.get_text('admin_panel_welcome', lang_code)
        
        # Create admin menu buttons
        import time
        button_creation_start = time.time()
        logger.info(f"🔍 DEBUG: Starting button creation for admin panel at {button_creation_start:.3f}")
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add admin action buttons
        admin_buttons = self.language.get_admin_buttons(lang_code)
        button_loop_start = time.time()
        for button_row in admin_buttons:
            markup.row(*[
                telebot.types.InlineKeyboardButton(
                    text=btn['text'],
                    callback_data=btn['callback_data']
                ) for btn in button_row
            ])
        button_loop_time = time.time() - button_loop_start
        
        # Add back to main menu button
        back_text = self.language.get_text('back_to_menu', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
        button_creation_time = time.time() - button_creation_start
        logger.info(f"🔍 DEBUG: Button creation took {button_creation_time:.3f}s (loop: {button_loop_time:.3f}s)")
        
        # Send admin panel
        import time
        telegram_api_start = time.time()
        logger.info(f"🔍 DEBUG: Starting Telegram API send_message call for admin panel at {telegram_api_start:.3f}")
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=welcome_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
        
        telegram_api_time = time.time() - telegram_api_start
        logger.info(f"🔍 DEBUG: Telegram API send_message call took {telegram_api_time:.3f}s")
    
    def show_store_settings_menu(self, call, lang_code):
        """Show store settings menu with editable options"""
        # Get store settings menu text
        menu_text = self.language.get_text('store_settings_menu', lang_code)
        
        # Create store settings buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add edit buttons
        edit_welcome_text = self.language.get_text('edit_welcome_message', lang_code)
        edit_about_text = self.language.get_text('edit_about_shop', lang_code)
        edit_contact_text = self.language.get_text('edit_contact_info', lang_code)
        edit_delivery_text = self.language.get_text('edit_delivery_prompt', lang_code)
        
        markup.add(telebot.types.InlineKeyboardButton(
            text=edit_welcome_text,
            callback_data='store_edit_welcome'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text=edit_about_text,
            callback_data='store_edit_about'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text=edit_contact_text,
            callback_data='store_edit_contact'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text=edit_delivery_text,
            callback_data='store_edit_delivery_prompt'
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
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")
    
    def handle_store_edit_buttons(self, call):
        """Handle store edit button clicks"""
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
        logger.info(f"User language code: {lang_code}")
        
        # Extract edit type from callback data
        edit_type = call.data.replace('store_edit_', '')
        logger.info(f"Edit type: {edit_type}")
        
        # Show edit prompt based on type
        if edit_type == 'welcome':
            self.show_edit_prompt(call, lang_code, 'welcome_message', 'welcome_edit_prompt')
        elif edit_type == 'about':
            self.show_edit_prompt(call, lang_code, 'about', 'about_edit_prompt')
        elif edit_type == 'contact':
            self.show_edit_prompt(call, lang_code, 'contact', 'contact_edit_prompt')
        elif edit_type == 'delivery_prompt':
            self.show_edit_prompt(call, lang_code, 'delivery_address_prompt', 'delivery_prompt_edit_prompt')
    
    def show_edit_prompt(self, call, lang_code, content_key, prompt_key):
        """Show edit prompt for a specific content type"""
        logger.info(f"show_edit_prompt called with lang_code: {lang_code}, content_key: {content_key}")
        # Get current content based on content_key
        if content_key == 'welcome_message':
            current_text = self.language.get_text('welcome_message', lang_code)
        elif content_key == 'about':
            current_text = self.language.get_button_response('about', 'message', lang_code)
        elif content_key == 'contact':
            current_text = self.language.get_button_response('contact', 'message', lang_code)
        else:
            current_text = "Content not found"
        
        # Get prompt text and format with current content
        prompt_template = self.language.get_text(prompt_key, lang_code)
        prompt_text = prompt_template.format(current_text=current_text)
        
        # Create back button
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_store_settings', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='store_back_to_settings'
        ))
        
        # Set user state for input handling
        self.db.set_user_state(
            user_id=call.from_user.id,
            state=f'editing_{content_key}',
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
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")
    
    @handler_operation
    def handle_text_input(self, message):
        """Handle text input when user is in editing state"""
        import time
        start_time = time.time()
        user_id = message.from_user.id
        
        logger.info(f"🔍 DEBUG: Admin handler text input START for user {user_id} at {start_time:.3f}")
        
        # Get user state
        db_start = time.time()
        user_state = self.db.get_user_state(user_id)
        db_time = time.time() - db_start
        logger.info(f"🔍 DEBUG: Admin handler get_user_state took {db_time:.3f}s")
        logger.info(f"🔍 DEBUG: Admin handler text input for user {user_id}, state: {user_state}")
        
        # Check if user is waiting for API key input
        if user_state and user_state['state'] == 'waiting_api_key':
            handler_time = time.time() - start_time
            logger.info(f"🔍 DEBUG: Admin handler API key input processing in {handler_time:.3f}s")
            return self.handle_api_key_input(message)
        
        # Check if user is waiting for admin link input
        if user_state and user_state['state'] == 'waiting_admin_link':
            handler_time = time.time() - start_time
            logger.info(f"🔍 DEBUG: Admin handler admin link input processing in {handler_time:.3f}s")
            logger.info(f"User {user_id} in waiting_admin_link state, handling input")
            return self.handle_admin_link_input(message)
        
        # Only handle store content editing states, not category states
        if not user_state or not (
            user_state['state'] == 'editing_welcome_message' or
            user_state['state'] == 'editing_about' or
            user_state['state'] == 'editing_contact' or
            user_state['state'] == 'editing_delivery_address_prompt'
        ):
            handler_time = time.time() - start_time
            logger.info(f"🔍 DEBUG: Admin handler not in editing state, returning False in {handler_time:.3f}s")
            return False  # Not in admin editing state
        
        # Check if user is admin
        admin_check_start = time.time()
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            admin_check_time = time.time() - admin_check_start
            logger.info(f"🔍 DEBUG: Admin handler user not admin, returning False in {admin_check_time:.3f}s")
            return False
        admin_check_time = time.time() - admin_check_start
        logger.info(f"🔍 DEBUG: Admin handler admin check passed in {admin_check_time:.3f}s")
        
        # Extract content type from state
        content_type = user_state['state'].replace('editing_', '')
        lang_code = user_state['data']
        new_text = message.text
        
        logger.info(f"🔍 DEBUG: Admin handler processing content update: {content_type}, lang: {lang_code}")
        
        # Update the JSON file
        json_update_start = time.time()
        success = self.update_language_json(content_type, lang_code, new_text)
        json_update_time = time.time() - json_update_start
        logger.info(f"🔍 DEBUG: Admin handler JSON update took {json_update_time:.3f}s, success: {success}")
        
        if success:
            # Show success message
            response_start = time.time()
            success_text = self.language.get_text('text_updated_success', lang_code)
            self.bot.send_message(
                chat_id=message.chat.id,
                text=f"{success_text} ✅",
                parse_mode='HTML'
            )
            
            # Clear user state
            self.db.clear_user_state(user_id)
            
            # Reload language system
            self.language.reload_languages()
            
            # Show store settings menu again
            markup = telebot.types.InlineKeyboardMarkup()
            back_settings_text = self.language.get_text('back_to_store_settings', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_settings_text,
                callback_data='admin_store_settings'
            ))
            
            returning_text = self.language.get_text('returning_to_store_settings', lang_code)
            self.bot.send_message(
                chat_id=message.chat.id,
                text=returning_text,
                reply_markup=markup
            )
            response_time = time.time() - response_start
            logger.info(f"🔍 DEBUG: Admin handler success response took {response_time:.3f}s")
        else:
            response_start = time.time()
            try:
                error_text = self.language.get_text('error_updating_content', lang_code)
            except:
                error_text = "❌ Error updating content. Please try again."
            self.bot.send_message(
                chat_id=message.chat.id,
                text=error_text
            )
            response_time = time.time() - response_start
            logger.info(f"🔍 DEBUG: Admin handler error response took {response_time:.3f}s")
        
        total_time = time.time() - start_time
        logger.info(f"🔍 DEBUG: Admin handler text input COMPLETE in {total_time:.3f}s for user {user_id}")
        return True  # Input was handled
    
    def handle_back_to_settings(self, call):
        """Handle back to store settings button"""
        user_id = call.from_user.id
        
        # Clear user state
        self.db.clear_user_state(user_id)
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Show store settings menu
        self.show_store_settings_menu(call, lang_code)
    
    def update_language_json(self, content_type, lang_code, new_text):
        """Update the language.json file with new content"""
        try:
            logger.info(f"Attempting to update {content_type} for {lang_code}")
            
            # Read current language file
            with open('language.json', 'r', encoding='utf-8') as f:
                language_data = json.load(f)
            
            # Check if language exists
            if lang_code not in language_data:
                logger.error(f"Language {lang_code} not found in language data")
                return False
            
            # Update the appropriate content
            if content_type == 'welcome_message':
                language_data[lang_code]['welcome_message'] = new_text
                logger.info(f"Updated welcome_message for {lang_code}")
            elif content_type == 'about':
                if 'button_responses' not in language_data[lang_code]:
                    logger.error(f"button_responses not found for {lang_code}")
                    return False
                if 'about' not in language_data[lang_code]['button_responses']:
                    logger.error(f"about button not found for {lang_code}")
                    return False
                language_data[lang_code]['button_responses']['about']['message'] = new_text
                logger.info(f"Updated about message for {lang_code}")
            elif content_type == 'contact':
                if 'button_responses' not in language_data[lang_code]:
                    logger.error(f"button_responses not found for {lang_code}")
                    return False
                if 'contact' not in language_data[lang_code]['button_responses']:
                    logger.error(f"contact button not found for {lang_code}")
                    return False
                language_data[lang_code]['button_responses']['contact']['message'] = new_text
                logger.info(f"Updated contact message for {lang_code}")
            elif content_type == 'delivery_address_prompt':
                language_data[lang_code]['delivery_address_prompt'] = new_text
                logger.info(f"Updated delivery_address_prompt for {lang_code}")
            else:
                logger.error(f"Unknown content_type: {content_type}")
                return False
            
            # Write back to file
            save_json_safely("language.json", language_data)
            
            logger.info(f"Successfully updated {content_type} for {lang_code}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating language file: {e}")
            logger.error(f"Content type: {content_type}, Lang code: {lang_code}")
            return False
    
    def show_payment_setup(self, call, lang_code):
        """Show payment setup instructions for OxaPay"""
        setup_text = self.language.get_text('payment_setup_message', lang_code)
        
        # Create back button
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_admin_panel', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='payment_setup_back'
        ))
        
        # Set user state for API key input
        self.db.set_user_state(
            user_id=call.from_user.id,
            state='waiting_api_key',
            data=lang_code,
            message_id=call.message.message_id
        )
        
        # Edit the message
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=setup_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")
    
    def handle_payment_setup_back(self, call):
        """Handle back button from payment setup"""
        user_id = call.from_user.id
        
        # Clear user state
        self.db.clear_user_state(user_id)
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Go back to admin panel
        self.handle_admin_panel(call)
    
    def handle_api_key_input(self, message):
        """Handle API key input from user"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        # Check if user is in API key waiting state
        if not user_state or user_state['state'] != 'waiting_api_key':
            return False
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            return False
        
        lang_code = user_state['data']
        api_key = message.text.strip()
        
        # Validate API key (basic validation)
        if not api_key or len(api_key) < 10:
            self.bot.send_message(
                chat_id=message.chat.id,
                text="❌ Invalid API key. Please provide a valid OxaPay API key."
            )
            return True
        
        # Update config.json with the API key
        success = self.update_config_api_key(api_key)
        
        if success:
            # Determine if this is new or updated
            current_key = self.config.get('oxapay_api_key', '')
            if current_key:
                success_text = self.language.get_text('api_key_updated', lang_code)
            else:
                success_text = self.language.get_text('api_key_saved', lang_code)
            
            # Update local config
            self.config['oxapay_api_key'] = api_key
            
            # Update payment handler's API key immediately if payment handler exists
            if self.payment_handler:
                self.payment_handler.oxapay_api_key = api_key
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text=success_text,
                parse_mode='HTML'
            )
            
            # Clear user state
            self.db.clear_user_state(user_id)
            
            # Show back to admin panel button
            markup = telebot.types.InlineKeyboardMarkup()
            back_admin_text = self.language.get_text('back_to_admin_panel', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_admin_text,
                callback_data='admin_panel'
            ))
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text="🔄 Returning to admin panel...",
                reply_markup=markup
            )
        else:
            self.bot.send_message(
                chat_id=message.chat.id,
                text="❌ Error saving API key. Please try again."
            )
        
        return True
    
    def update_config_api_key(self, api_key):
        """Update config.json with new API key"""
        try:
            # Read current config
            with open('config.json', 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Update API key
            config_data['oxapay_api_key'] = api_key
            
            # Write back to file
            save_json_safely("config.json", config_data)
            
            logger.info(f"Successfully updated oxapay_api_key in config.json")
            return True
            
        except Exception as e:
            logger.error(f"Error updating config file: {e}")
            return False
    
    def show_admin_setup(self, call, lang_code):
        """Show admin setup instructions"""
        setup_text = self.language.get_text('setup_admin_message', lang_code)
        
        # Create back button
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_admin_panel', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='admin_chat_setup_back'
        ))
        
        # Set user state for admin link input
        self.db.set_user_state(
            user_id=call.from_user.id,
            state='waiting_admin_link',
            data=lang_code,
            message_id=call.message.message_id
        )
        
        # Edit the message
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=setup_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")
    
    def handle_admin_setup_back(self, call):
        """Handle back button from admin setup - clear ALL states for clean return"""
        user_id = call.from_user.id
        
        # Clear ALL user states to ensure clean slate
        success = self.db.clear_user_state(user_id)
        logger.info(f"Admin setup back: cleared ALL states for user {user_id}, success: {success}")
        
        # Also clear any potential lingering states (double-check)
        try:
            # Force clear any remaining states
            import sqlite3
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM user_states WHERE user_id = ?', (user_id,))
                conn.commit()
                logger.info(f"Force cleared all states for user {user_id}")
        except Exception as e:
            logger.error(f"Error force clearing states: {e}")
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Go back to admin panel
        self.handle_admin_panel(call)
    
    def handle_admin_link_input(self, message):
        """Handle admin link input from user"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        # Check if user is in admin link waiting state
        if not user_state or user_state['state'] != 'waiting_admin_link':
            return False
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            return False
        
        lang_code = user_state['data']
        admin_link = message.text.strip()
        
        # Validate admin link (basic validation)
        if not admin_link or len(admin_link) < 3:
            self.bot.send_message(
                chat_id=message.chat.id,
                text="❌ Invalid admin link. Please provide a valid link or username."
            )
            return True
        
        # Update config.json with the admin link
        success = self.update_config_admin_link(admin_link)
        
        if success:
            # Determine if this is new or updated
            current_link = self.config.get('admin_chat_link', '')
            if current_link:
                success_text = self.language.get_text('admin_link_updated', lang_code)
            else:
                success_text = self.language.get_text('admin_link_saved', lang_code)
            
            # Update local config
            self.config['admin_chat_link'] = admin_link
            
            # Clear user state
            self.db.clear_user_state(user_id)
            
            # Send success message and show admin panel directly
            self.bot.send_message(
                chat_id=message.chat.id,
                text=f"{success_text} 🔄 Returning to admin panel...",
                parse_mode='HTML'
            )
            
            # Create admin panel message
            welcome_text = self.language.get_text('admin_panel_welcome', lang_code)
            markup = telebot.types.InlineKeyboardMarkup()
            
            # Add admin action buttons
            admin_buttons = self.language.get_admin_buttons(lang_code)
            for button_row in admin_buttons:
                row_buttons = []
                for btn in button_row:
                    button_text = btn['text']
                    callback_data = btn['callback_data']
                    
                    # If it's the currency button, add current currency symbol
                    if callback_data == 'admin_currency_settings':
                        current_currency = self.config.get('currency', {'symbol': '$'})
                        button_text = f"{button_text}: {current_currency['symbol']}"
                    
                    row_buttons.append(telebot.types.InlineKeyboardButton(
                        text=button_text,
                        callback_data=callback_data
                    ))
                markup.row(*row_buttons)
            
            # Add back to main menu button
            back_text = self.language.get_text('back_to_menu', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_text,
                callback_data='main_menu'
            ))
            
            # Send admin panel
            self.bot.send_message(
                chat_id=message.chat.id,
                text=welcome_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        else:
            self.bot.send_message(
                chat_id=message.chat.id,
                text="❌ Error saving admin link. Please try again."
            )
        
        return True
    
    def update_config_admin_link(self, admin_link):
        """Update config.json with new admin link"""
        try:
            # Read current config
            with open('config.json', 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Update admin link
            config_data['admin_chat_link'] = admin_link
            
            # Write back to file
            save_json_safely("config.json", config_data)
            
            logger.info(f"Successfully updated admin_chat_link in config.json")
            return True
            
        except Exception as e:
            logger.error(f"Error updating config file: {e}")
            return False