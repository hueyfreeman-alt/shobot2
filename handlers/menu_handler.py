import telebot
import logging
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class MenuHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.cart_handler = None  # Will be set by main.py
        self.topup_handler = None  # Will be set by main.py
    
    def get_welcome_with_balance(self, user_id, lang_code):
        """Get welcome message with user's balance"""
        # Get welcome message
        welcome_text = self.language.get_text('welcome_message', lang_code)
        
        # Get user's balance
        balance = self.db.get_user_balance(user_id)
        currency_symbol = self.config.get('currency', {}).get('symbol', '$')
        
        # Get balance display text
        balance_text = self.language.get_text('balance_display', lang_code)
        balance_text = balance_text.format(balance=f"{balance:.2f}", currency_symbol=currency_symbol)
        
        # Combine welcome message with balance
        return welcome_text + balance_text
    
    def handle_main_menu(self, call):
        """Handle main menu callback"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            # User not found, redirect to start
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Check if user is admin
        is_admin = self.db.is_admin(user_id, self.config['admin_ids'])
        
        # Get welcome message with balance
        welcome_text = self.get_welcome_with_balance(user_id, lang_code)
        
        # Create menu buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add menu navigation buttons
        menu_buttons = self.language.get_menu_buttons(lang_code, is_admin)
        for button_row in menu_buttons:
            markup.row(*[
                telebot.types.InlineKeyboardButton(
                    text=btn['text'],
                    callback_data=btn['callback_data']
                ) for btn in button_row
            ])
        
        # Add main menu action buttons with dynamic cart
        main_menu_buttons = self.language.get_main_menu_buttons(lang_code, user_id, self.cart_handler)
        for button_row in main_menu_buttons:
            markup.row(*[
                telebot.types.InlineKeyboardButton(
                    text=btn['text'],
                    callback_data=btn['callback_data']
                ) for btn in button_row
            ])
        
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
    
    def handle_menu_buttons(self, call):
        """Handle main menu button clicks with new ID-based system"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract button ID from callback data
        button_id = call.data.replace('menu_', '')
        
        # Handle special cases that should redirect to other handlers
        if button_id == 'products':
            # This should be handled by shopping handler
            # We'll return False to indicate it wasn't handled here
            return False
        elif button_id == 'cart':
            # This should be handled by shopping handler  
            # We'll return False to indicate it wasn't handled here
            return False
        elif button_id == 'topup':
            # This should be handled by topup handler
            return False
        elif button_id == 'reviews':
            # This should be handled by reviews handler
            return False
        elif button_id == 'disputes':
            # This should be handled by dispute handler
            return False
        elif button_id == 'admin_link':
            # Handle admin link - open the link from config
            self.handle_admin_link(call)
            return True
        elif button_id == 'history':
            # This should be handled by history handler
            # We'll return False to indicate it wasn't handled here
            return False
        
        # For other buttons, show generic response
        # Get button response from language system
        response_data = self.language.get_button_response(button_id, None, lang_code)
        response_text = response_data['message']
        
        # Add back to menu button
        markup = telebot.types.InlineKeyboardMarkup()
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
        return True
    
    def handle_main_menu_keyboard(self, message):
        """Handle main menu keyboard button press"""
        user_id = message.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.send_message(message.chat.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Get welcome message with balance
        welcome_text = self.get_welcome_with_balance(user_id, lang_code)
        
        # Create inline buttons for main menu actions
        import time
        button_creation_start = time.time()
        logger.info(f"🔍 DEBUG: Starting button creation for menu at {button_creation_start:.3f}")
        
        inline_markup = telebot.types.InlineKeyboardMarkup()
        main_menu_buttons = self.language.get_main_menu_buttons(lang_code)
        
        button_loop_start = time.time()
        for button_row in main_menu_buttons:
            inline_markup.row(*[
                telebot.types.InlineKeyboardButton(
                    text=btn['text'],
                    callback_data=btn['callback_data']
                ) for btn in button_row
            ])
        button_loop_time = time.time() - button_loop_start
        
        button_creation_time = time.time() - button_creation_start
        logger.info(f"🔍 DEBUG: Button creation took {button_creation_time:.3f}s (loop: {button_loop_time:.3f}s)")
        
        # Send main menu
        import time
        telegram_api_start = time.time()
        logger.info(f"🔍 DEBUG: Starting Telegram API send_message call for menu at {telegram_api_start:.3f}")
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=welcome_text,
            reply_markup=inline_markup,
            parse_mode='HTML'
        )
        
        telegram_api_time = time.time() - telegram_api_start
        logger.info(f"🔍 DEBUG: Telegram API send_message call took {telegram_api_time:.3f}s")
    
    def handle_admin_link(self, call):
        """Handle admin link button - open admin chat link"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Get admin chat link from config
        admin_link = self.config.get('admin_chat_link', '')
        
        if not admin_link:
            # No admin link configured
            self.bot.answer_callback_query(
                call.id, 
                "❌ Admin contact not configured. Please contact the shop owner.",
                show_alert=True
            )
            return
        
        # Format the admin link message
        admin_text = f"👤 <b>Contact Admin</b>\n\n🔗 Click the link below to contact our admin:\n\n{admin_link}\n\n💬 You can also copy the link and paste it in your browser or Telegram."
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add URL button if it's a proper URL
        if admin_link.startswith(('http://', 'https://', 't.me/')):
            if not admin_link.startswith('https://') and admin_link.startswith('t.me/'):
                full_link = f"https://{admin_link}"
            else:
                full_link = admin_link
            
            markup.add(telebot.types.InlineKeyboardButton(
                text="🔗 Open Admin Chat",
                url=full_link
            ))
        
        # Back to menu button
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
                text=admin_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=admin_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")