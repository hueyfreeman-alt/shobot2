import telebot
import logging
import json
import sqlite3
from datetime import datetime
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class HistoryHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.orders_per_page = 3
    
    def handle_history_menu(self, call):
        """Handle main history menu"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Show history options
        history_text = self.language.get_text('history_message', lang_code)
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Completed and Queue buttons
        completed_text = self.language.get_text('history_completed', lang_code)
        queue_text = self.language.get_text('history_queue', lang_code)
        
        markup.add(
            telebot.types.InlineKeyboardButton(
                text=completed_text,
                callback_data='history_completed_0'
            ),
            telebot.types.InlineKeyboardButton(
                text=queue_text,
                callback_data='history_queue_0'
            )
        )
        
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
                text=history_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=history_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        
        # Answer callback query
        self.bot.answer_callback_query(call.id)
    
    def handle_completed_orders(self, call):
        """Handle completed orders view with pagination"""
        user_id = call.from_user.id
        
        # Extract page number from callback data
        page = int(call.data.replace('history_completed_', ''))
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Get completed orders from database
        orders = self.get_completed_orders(user_id, page)
        total_orders = self.get_total_completed_orders(user_id)
        
        if not orders:
            no_orders_text = self.language.get_text('no_completed_orders', lang_code)
            
            # Create back button
            markup = telebot.types.InlineKeyboardMarkup()
            back_text = self.language.get_text('back_to_history', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_text,
                callback_data='menu_history'
            ))
            
            # Edit the message
            try:
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=no_orders_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            
            self.bot.answer_callback_query(call.id)
            return
        
        # Format orders display
        title = self.language.get_text('completed_orders_title', lang_code)
        orders_text = f"<b>{title}</b>\n\n"
        
        for i, order in enumerate(orders, 1):
            order_summary = self.format_order_summary(order, lang_code)
            orders_text += f"{order_summary}\n\n"
        
        # Add pagination info
        total_pages = (total_orders + self.orders_per_page - 1) // self.orders_per_page
        current_page = page + 1
        orders_text += f"📄 Page {current_page} of {total_pages}"
        
        # Create pagination buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Previous and Next buttons
        nav_buttons = []
        if page > 0:
            prev_text = self.language.get_text('previous_page', lang_code)
            nav_buttons.append(telebot.types.InlineKeyboardButton(
                text=prev_text,
                callback_data=f'history_completed_{page - 1}'
            ))
        
        if (page + 1) * self.orders_per_page < total_orders:
            next_text = self.language.get_text('next_page', lang_code)
            nav_buttons.append(telebot.types.InlineKeyboardButton(
                text=next_text,
                callback_data=f'history_completed_{page + 1}'
            ))
        
        if nav_buttons:
            markup.row(*nav_buttons)
        
        # Back to history button
        back_text = self.language.get_text('back_to_history', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='menu_history'
        ))
        
        # Edit the message
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=orders_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        self.bot.answer_callback_query(call.id)
    
    def handle_queue_orders(self, call):
        """Handle queue orders view with pagination"""
        user_id = call.from_user.id
        
        # Extract page number from callback data
        page = int(call.data.replace('history_queue_', ''))
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Get queue orders from database
        orders = self.get_queue_orders(user_id, page)
        total_orders = self.get_total_queue_orders(user_id)
        
        if not orders:
            no_orders_text = self.language.get_text('no_queue_orders', lang_code)
            
            # Create back button
            markup = telebot.types.InlineKeyboardMarkup()
            back_text = self.language.get_text('back_to_history', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_text,
                callback_data='menu_history'
            ))
            
            # Edit the message
            try:
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=no_orders_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            
            self.bot.answer_callback_query(call.id)
            return
        
        # Format orders display
        title = self.language.get_text('queue_orders_title', lang_code)
        orders_text = f"<b>{title}</b>\n\n"
        
        for i, order in enumerate(orders, 1):
            order_summary = self.format_order_summary(order, lang_code, is_queue=True)
            orders_text += f"{order_summary}\n\n"
        
        # Add pagination info
        total_pages = (total_orders + self.orders_per_page - 1) // self.orders_per_page
        current_page = page + 1
        orders_text += f"📄 Page {current_page} of {total_pages}"
        
        # Create pagination buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Previous and Next buttons
        nav_buttons = []
        if page > 0:
            prev_text = self.language.get_text('previous_page', lang_code)
            nav_buttons.append(telebot.types.InlineKeyboardButton(
                text=prev_text,
                callback_data=f'history_queue_{page - 1}'
            ))
        
        if (page + 1) * self.orders_per_page < total_orders:
            next_text = self.language.get_text('next_page', lang_code)
            nav_buttons.append(telebot.types.InlineKeyboardButton(
                text=next_text,
                callback_data=f'history_queue_{page + 1}'
            ))
        
        if nav_buttons:
            markup.row(*nav_buttons)
        
        # Back to history button
        back_text = self.language.get_text('back_to_history', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='menu_history'
        ))
        
        # Edit the message
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=orders_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        self.bot.answer_callback_query(call.id)
    
    def get_completed_orders(self, user_id, page):
        """Get completed orders for user with pagination"""
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            offset = page * self.orders_per_page
            
            cursor.execute("""
                SELECT id, user_id, total_cost, completed_date, 'completed' as status, products
                FROM selling_history 
                WHERE user_id = ? 
                ORDER BY completed_date DESC 
                LIMIT ? OFFSET ?
            """, (user_id, self.orders_per_page, offset))
            
            orders = cursor.fetchall()
            conn.close()
            
            # Convert to list of dictionaries
            order_list = []
            for order in orders:
                order_dict = {
                    'id': order[0],
                    'user_id': order[1],
                    'total_cost': order[2],
                    'created_at': order[3],
                    'status': order[4],
                    'products': json.loads(order[5]) if order[5] else []
                }
                order_list.append(order_dict)
            
            return order_list
            
        except Exception as e:
            logger.error(f"Error getting completed orders: {e}")
            return []
    
    def get_total_completed_orders(self, user_id):
        """Get total count of completed orders for user"""
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM selling_history WHERE user_id = ?", (user_id,))
            count = cursor.fetchone()[0]
            conn.close()
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting total completed orders: {e}")
            return 0
    
    def get_queue_orders(self, user_id, page):
        """Get queue orders for user with pagination"""
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            offset = page * self.orders_per_page
            
            cursor.execute("""
                SELECT id, user_id, total_cost, payment_date, status, products
                FROM delivery_queue 
                WHERE user_id = ? 
                ORDER BY payment_date DESC 
                LIMIT ? OFFSET ?
            """, (user_id, self.orders_per_page, offset))
            
            orders = cursor.fetchall()
            conn.close()
            
            # Convert to list of dictionaries
            order_list = []
            for order in orders:
                order_dict = {
                    'id': order[0],
                    'user_id': order[1],
                    'total_cost': order[2],
                    'created_at': order[3],
                    'status': order[4],
                    'products': json.loads(order[5]) if order[5] else []
                }
                order_list.append(order_dict)
            
            return order_list
            
        except Exception as e:
            logger.error(f"Error getting queue orders: {e}")
            return []
    
    def get_total_queue_orders(self, user_id):
        """Get total count of queue orders for user"""
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM delivery_queue WHERE user_id = ?", (user_id,))
            count = cursor.fetchone()[0]
            conn.close()
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting total queue orders: {e}")
            return 0
    
    def format_order_summary(self, order, lang_code, is_queue=False):
        """Format order summary for display"""
        try:
            # Format date
            date_str = order['created_at']
            if isinstance(date_str, str):
                # Try to parse the date string
                try:
                    date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    formatted_date = date_obj.strftime('%Y-%m-%d %H:%M')
                except:
                    formatted_date = date_str
            else:
                formatted_date = str(date_str)
            
            # Get currency symbol
            currency_symbol = self.config.get('currency', {}).get('symbol', '$')
            
            # Format products summary
            products = order.get('products', [])
            products_summary = self.format_products_summary(products)
            
            # Format using language template
            summary = self.language.get_text('order_summary_format', lang_code,
                order_id=order['id'],
                date=formatted_date,
                total=f"{currency_symbol}{order['total_cost']}",
                products_summary=products_summary
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"Error formatting order summary: {e}")
            return f"Order #{order.get('id', 'Unknown')} - Error loading details"
    
    def format_products_summary(self, products):
        """Format a compact summary of products"""
        try:
            if not products or len(products) == 0:
                return "No products"
            
            # If it's a string (JSON), parse it
            if isinstance(products, str):
                products = json.loads(products)
            
            summary_parts = []
            for product in products[:3]:  # Show max 3 products
                if isinstance(product, dict):
                    name = product.get('name', 'Unknown')
                    quantity = product.get('quantity', 1)
                    if quantity > 1:
                        summary_parts.append(f"{name} x{quantity}")
                    else:
                        summary_parts.append(name)
                else:
                    summary_parts.append(str(product))
            
            # If there are more products, add "..."
            if len(products) > 3:
                summary_parts.append("...")
            
            return ", ".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Error formatting products summary: {e}")
            return f"{len(products) if products else 0} items"
