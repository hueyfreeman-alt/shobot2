import telebot
import logging
import json
import os
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class CurrencyHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.currencies_file = 'currencies.json'
        self.config_file = 'config.json'
    
    def load_currencies(self):
        """Load currencies from JSON file"""
        try:
            if os.path.exists(self.currencies_file):
                with open(self.currencies_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.error(f"Currencies file not found: {self.currencies_file}")
                return {"currencies": []}
        except Exception as e:
            logger.error(f"Error loading currencies: {e}")
            return {"currencies": []}
    
    def save_config(self, config_data):
        """Save configuration to JSON file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
            logger.info("Configuration saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def get_current_currency(self):
        """Get current currency from config"""
        return self.config.get('currency', {
            "code": "USD",
            "name": "US Dollar", 
            "symbol": "$",
            "flag": "🇺🇸"
        })
    
    def handle_currency_settings(self, call):
        """Handle main currency settings screen"""
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
        
        # Get current currency
        current_currency = self.get_current_currency()
        
        # Get currency settings text
        currency_text = self.language.get_text('currency_settings_message', lang_code)
        formatted_text = currency_text.format(
            current_currency_flag=current_currency['flag'],
            current_currency_name=current_currency['name'],
            current_currency_symbol=current_currency['symbol']
        )
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Popular currencies button
        popular_text = self.language.get_text('popular_currencies', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=popular_text,
            callback_data='currency_popular'
        ))
        
        # All currencies button
        all_currencies_text = self.language.get_text('all_currencies', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=all_currencies_text,
            callback_data='currency_all'
        ))
        
        # Back button
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
                text=formatted_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_popular_currencies(self, call):
        """Show popular currencies selection"""
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
        
        # Load currencies
        currencies_data = self.load_currencies()
        popular_currencies = [c for c in currencies_data.get('currencies', []) if c.get('popular', False)]
        
        # Get current currency for highlighting
        current_currency = self.get_current_currency()
        
        # Create title text
        title_text = self.language.get_text('popular_currencies', lang_code)
        select_prompt = self.language.get_text('select_currency_prompt', lang_code)
        menu_text = f"<b>{title_text}</b>\n\n{select_prompt}"
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add popular currency buttons (2 per row)
        for i in range(0, len(popular_currencies), 2):
            row_buttons = []
            for j in range(2):
                if i + j < len(popular_currencies):
                    currency = popular_currencies[i + j]
                    
                    # Highlight current currency
                    if currency['code'] == current_currency['code']:
                        display_text = f"✅ {currency['flag']} {currency['code']}"
                    else:
                        display_text = f"{currency['flag']} {currency['code']}"
                    
                    row_buttons.append(telebot.types.InlineKeyboardButton(
                        text=display_text,
                        callback_data=f'currency_select_{currency["code"]}'
                    ))
            
            if len(row_buttons) == 2:
                markup.row(*row_buttons)
            elif len(row_buttons) == 1:
                markup.add(row_buttons[0])
        
        # Back button
        back_text = self.language.get_text('back_to_currency_selection', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='admin_currency_settings'
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
    
    def handle_all_currencies(self, call):
        """Show all currencies selection with pagination"""
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
        
        # For now, show first page (can add pagination later)
        self.show_currencies_page(call, lang_code, page=0)
    
    def show_currencies_page(self, call, lang_code, page=0):
        """Show currencies with pagination"""
        # Load currencies
        currencies_data = self.load_currencies()
        all_currencies = currencies_data.get('currencies', [])
        
        # Get current currency for highlighting
        current_currency = self.get_current_currency()
        
        # Pagination settings
        currencies_per_page = 10
        start_idx = page * currencies_per_page
        end_idx = start_idx + currencies_per_page
        page_currencies = all_currencies[start_idx:end_idx]
        
        total_pages = (len(all_currencies) + currencies_per_page - 1) // currencies_per_page
        
        # Create title text
        title_text = self.language.get_text('all_currencies', lang_code)
        select_prompt = self.language.get_text('select_currency_prompt', lang_code)
        page_info = f"Page {page + 1}/{total_pages}" if total_pages > 1 else ""
        menu_text = f"<b>{title_text}</b>\n\n{select_prompt}\n\n{page_info}"
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add currency buttons (2 per row)
        for i in range(0, len(page_currencies), 2):
            row_buttons = []
            for j in range(2):
                if i + j < len(page_currencies):
                    currency = page_currencies[i + j]
                    
                    # Highlight current currency
                    if currency['code'] == current_currency['code']:
                        display_text = f"✅ {currency['flag']} {currency['code']}"
                    else:
                        display_text = f"{currency['flag']} {currency['code']}"
                    
                    row_buttons.append(telebot.types.InlineKeyboardButton(
                        text=display_text,
                        callback_data=f'currency_select_{currency["code"]}'
                    ))
            
            if len(row_buttons) == 2:
                markup.row(*row_buttons)
            elif len(row_buttons) == 1:
                markup.add(row_buttons[0])
        
        # Pagination buttons
        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(telebot.types.InlineKeyboardButton(
                    text="⬅️ Previous",
                    callback_data=f'currency_page_{page - 1}'
                ))
            if page < total_pages - 1:
                nav_buttons.append(telebot.types.InlineKeyboardButton(
                    text="Next ➡️",
                    callback_data=f'currency_page_{page + 1}'
                ))
            
            if nav_buttons:
                if len(nav_buttons) == 2:
                    markup.row(*nav_buttons)
                else:
                    markup.add(nav_buttons[0])
        
        # Back button
        back_text = self.language.get_text('back_to_currency_selection', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='admin_currency_settings'
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
    
    def handle_currency_page(self, call):
        """Handle currency pagination"""
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
        
        # Extract page number
        page = int(call.data.replace('currency_page_', ''))
        
        # Show the requested page
        self.show_currencies_page(call, lang_code, page)
    
    def handle_currency_selection(self, call):
        """Handle currency selection"""
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
        
        # Extract currency code
        currency_code = call.data.replace('currency_select_', '')
        
        # Load currencies and find the selected one
        currencies_data = self.load_currencies()
        selected_currency = None
        for currency in currencies_data.get('currencies', []):
            if currency['code'] == currency_code:
                selected_currency = currency
                break
        
        if not selected_currency:
            self.bot.answer_callback_query(call.id, "❌ Currency not found")
            return
        
        # Update config
        new_config = self.config.copy()
        new_config['currency'] = {
            'code': selected_currency['code'],
            'name': selected_currency['name'],
            'symbol': selected_currency['symbol'],
            'flag': selected_currency['flag']
        }
        
        # Save configuration
        if self.save_config(new_config):
            # Update internal config
            self.config['currency'] = new_config['currency']
            
            # Show success message
            success_text = self.language.get_text('currency_updated_success', lang_code)
            formatted_success = success_text.format(
                currency_name=selected_currency['name'],
                currency_symbol=selected_currency['symbol']
            )
            
            self.bot.answer_callback_query(call.id, formatted_success, show_alert=True)
            
            # Reload config to get the updated currency
            import json
            with open(self.config_file, 'r', encoding='utf-8') as f:
                updated_config = json.load(f)
            
            # Return to admin panel to show updated currency button
            call.data = 'admin_panel'
            from handlers.admin_handler import AdminHandler
            admin_handler = AdminHandler(self.bot, self.db, self.language, updated_config)
            admin_handler.currency_handler = self
            admin_handler.handle_admin_panel(call)
        else:
            self.bot.answer_callback_query(call.id, "❌ Error saving currency settings")
    
    def get_currency_display(self, amount):
        """Format amount with current currency"""
        current_currency = self.get_current_currency()
        symbol = current_currency['symbol']
        
        # Different positioning for different currencies
        if current_currency['code'] in ['USD', 'CAD', 'AUD', 'SGD', 'HKD', 'MXN', 'BRL']:
            return f"{symbol}{amount}"  # $100
        elif current_currency['code'] in ['EUR', 'GBP']:
            return f"{symbol}{amount}"  # €100, £100
        elif current_currency['code'] in ['JPY', 'CNY', 'KRW', 'INR']:
            return f"{symbol}{amount}"  # ¥100, ₹100, ₩100
        else:
            return f"{amount} {symbol}"  # 100 CHF, 100 kr
    
    def format_price(self, price):
        """Format price with current currency (for display in products)"""
        return self.get_currency_display(price)
