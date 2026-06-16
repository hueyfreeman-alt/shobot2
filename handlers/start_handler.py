import telebot
import logging
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class StartHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
    
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
    
    def handle_start(self, message):
        """Handle /start command"""
        user = message.from_user
        user_id = user.id
        username = user.username
        first_name = user.first_name
        last_name = user.last_name
        
        # Get or create user atomically - no race conditions
        user_data = self.db.get_or_create_user(user_id, username, first_name, last_name, 'en')
        
        if not user_data:
            # Database error
            self.bot.send_message(message.chat.id, "❌ Database error. Please try again.")
            return
        
        if user_data['is_new']:
            # New user, show language selection
            self.show_language_selection(message, user_id, username, first_name, last_name)
        else:
            # Existing user, show main menu in their preferred language
            lang_code = user_data['language_code']
            self.show_main_menu(message, lang_code)
    
    def show_language_selection(self, message, user_id, username, first_name, last_name):
        """Show language selection menu"""
        # User already created in handle_start, just show language selection
        
        # Get combined language setup message from all languages
        text = self.language.get_combined_language_setup_message()
        
        # Create inline keyboard with language options
        markup = telebot.types.InlineKeyboardMarkup()
        language_buttons = self.language.get_language_buttons()
        
        for button in language_buttons:
            markup.add(telebot.types.InlineKeyboardButton(
                text=button['text'],
                callback_data=button['callback_data']
            ))
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def handle_language_selection(self, call):
        """Handle language selection callback"""
        user_id = call.from_user.id
        lang_code = call.data.replace('lang_', '')
        
        # Update user's language preference
        self.db.update_user_language(user_id, lang_code)
        
        # Get confirmation message
        confirmation_text = self.language.get_text('language_selected', lang_code)
        
        # Edit the message to show confirmation
        self.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=confirmation_text,
            parse_mode='HTML'
        )
        
        # Show main menu after a brief moment
        self.show_main_menu_after_selection(call, lang_code)
    
    def show_main_menu_after_selection(self, call, lang_code):
        """Show main menu after language selection"""
        user_id = call.from_user.id
        
        # Check if user is admin
        is_admin = self.db.is_admin(user_id, self.config['admin_ids'])
        
        # Get welcome message with balance
        welcome_text = self.get_welcome_with_balance(user_id, lang_code)
        
        # Create keyboard buttons for Menu/Admin navigation
        keyboard_markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        main_menu_text = self.language.get_text('menu_button_main', lang_code)
        keyboard_buttons = [telebot.types.KeyboardButton(main_menu_text)]
        
        if is_admin:
            admin_panel_text = self.language.get_text('menu_button_admin', lang_code)
            keyboard_buttons.append(telebot.types.KeyboardButton(admin_panel_text))
        
        keyboard_markup.add(*keyboard_buttons)
        
        # Create inline buttons for main menu actions (filtered for regular users)
        inline_markup = telebot.types.InlineKeyboardMarkup()
        main_menu_buttons = self.get_filtered_main_menu_buttons(lang_code, is_admin)
        for button_row in main_menu_buttons:
            inline_markup.row(*[
                telebot.types.InlineKeyboardButton(
                    text=btn['text'],
                    callback_data=btn['callback_data']
                ) for btn in button_row
            ])
        
        # First set the keyboard with a minimal message
        setup_text = self.language.get_text('setting_up_menu', lang_code)
        self.bot.send_message(
            chat_id=call.message.chat.id,
            text=setup_text,
            reply_markup=keyboard_markup
        )
        
        # Then send the main welcome message with inline buttons
        self.bot.send_message(
            chat_id=call.message.chat.id,
            text=welcome_text,
            reply_markup=inline_markup,
            parse_mode='HTML'
        )
    
    def show_main_menu(self, message, lang_code):
        """Show main menu for existing users"""
        user_id = message.from_user.id
        
        # Check if user is admin
        is_admin = self.db.is_admin(user_id, self.config['admin_ids'])
        
        # Get welcome message with balance
        welcome_text = self.get_welcome_with_balance(user_id, lang_code)
        
        # Create keyboard buttons for Menu/Admin navigation
        keyboard_markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        main_menu_text = self.language.get_text('menu_button_main', lang_code)
        keyboard_buttons = [telebot.types.KeyboardButton(main_menu_text)]
        
        if is_admin:
            admin_panel_text = self.language.get_text('menu_button_admin', lang_code)
            keyboard_buttons.append(telebot.types.KeyboardButton(admin_panel_text))
        
        keyboard_markup.add(*keyboard_buttons)
        
        # Create inline buttons for main menu actions (filtered for regular users)
        inline_markup = telebot.types.InlineKeyboardMarkup()
        main_menu_buttons = self.get_filtered_main_menu_buttons(lang_code, is_admin)
        for button_row in main_menu_buttons:
            inline_markup.row(*[
                telebot.types.InlineKeyboardButton(
                    text=btn['text'],
                    callback_data=btn['callback_data']
                ) for btn in button_row
            ])
        
        # First set the keyboard with a minimal message
        setup_text = self.language.get_text('setting_up_menu', lang_code)
        self.bot.send_message(
            chat_id=message.chat.id,
            text=setup_text,
            reply_markup=keyboard_markup
        )
        
        # Then send the main welcome message with inline buttons
        self.bot.send_message(
            chat_id=message.chat.id,
            text=welcome_text,
            reply_markup=inline_markup,
            parse_mode='HTML'
        )
    
    def get_filtered_main_menu_buttons(self, lang_code, is_admin=False):
        """Get main menu buttons filtered based on user permissions"""
        buttons = []
        button_data = self.language.get_text('button_texts_mainmenu', lang_code)
        
        if isinstance(button_data, list):
            admin_history_row = []
            
            for button_info in button_data:
                if isinstance(button_info, dict):
                    # Skip admin_link button for regular users
                    if button_info['id'] == 'admin_link' and not is_admin:
                        continue
                    
                    button_obj = {
                        'text': button_info['text'],
                        'callback_data': f"menu_{button_info['id']}"
                    }
                    
                    # Special handling for Admin and History buttons - put them in the same row
                    if button_info['id'] == 'admin_link':
                        admin_history_row.append(button_obj)
                    elif button_info['id'] == 'history':
                        admin_history_row.append(button_obj)
                        # After adding history, add the row with both buttons
                        if admin_history_row:
                            buttons.append(admin_history_row)
                            admin_history_row = []
                    else:
                        # Add single button in its own row
                        buttons.append([button_obj])
            
            # If admin_history_row has remaining buttons (edge case)
            if admin_history_row:
                buttons.append(admin_history_row)
        
        return buttons
