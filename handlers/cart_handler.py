import telebot
import logging
import json
import sqlite3
import os
from datetime import datetime
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class CartHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        
        # Import other handlers
        from handlers.payment_handler import PaymentHandler
        self.payment_handler = PaymentHandler(bot, db, language, config)
    
    def get_cart_button_text(self, lang_code, user_id):
        """Get dynamic cart button text with total if there's an active order"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                current_timestamp = int(datetime.now().timestamp())
                
                cursor.execute('''
                    SELECT total_cost FROM orders 
                    WHERE user_id = ? AND status = 'pending' AND deadline > ?
                    ORDER BY created_at DESC LIMIT 1
                ''', (user_id, current_timestamp))
                
                order = cursor.fetchone()
                
                if order and order[0] > 0:
                    # Format total with currency
                    total = self.format_price(order[0])
                    return self.language.get_text('cart_button_with_total', lang_code).format(total=total)
                else:
                    # Default cart button text
                    return self.language.get_text('cart_title', lang_code)
                    
        except Exception as e:
            logger.error(f"Error getting cart button text: {e}")
            return self.language.get_text('cart_title', lang_code)
    
    def handle_cart_view(self, call):
        """Handle cart view - show cart summary with payment options"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Get user's active order
        order = self.get_active_order(user_id)
        
        if not order or not order.get('products'):
            # Empty cart
            empty_text = self.language.get_text('cart_empty', lang_code)
            markup = telebot.types.InlineKeyboardMarkup()
            back_text = self.language.get_text('back_to_menu_button', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_text,
                callback_data='main_menu'
            ))
            
            try:
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=empty_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
        else:
            # Show cart summary
            self.show_cart_summary(call, order, lang_code)
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def show_cart_summary(self, call, order, lang_code):
        """Show detailed cart summary with payment options"""
        # Build cart items display
        cart_items = self.build_cart_items_display(order['products'], lang_code)
        total_cost = self.format_price(order['total_cost'])
        
        # Build summary message
        summary_title = self.language.get_text('cart_summary_title', lang_code)
        grand_total = self.language.get_text('cart_grand_total', lang_code).format(total=total_cost)
        
        # Add expiry warning
        from handlers.cleanup_handler import CleanupHandler
        cleanup_handler = CleanupHandler(self.bot, self.db, self.language, self.config)
        expiry_warning = cleanup_handler.get_order_expiry_warning_text(lang_code)
        
        message_text = f"<b>{summary_title}</b>\n\n{cart_items}\n\n{grand_total}\n\n{expiry_warning}"
        
        # Check if order has deliverable products
        has_deliverable = any(item.get('type') == 'delivered' for item in order['products'])
        
        # Create buttons based on product types
        markup = telebot.types.InlineKeyboardMarkup()
        
        if has_deliverable:
            # DELIVERABLE PRODUCTS - COMPLETELY SEPARATE FLOW
            if not order.get('delivery_address'):
                # Need to collect delivery address first
                address_text = self.language.get_text('delivery_address_button', lang_code)
                markup.add(telebot.types.InlineKeyboardButton(
                    text=address_text,
                    callback_data=f'cart_address_{order["id"]}'
                ))
            else:
                # Address collected - DELIVERABLE SPECIFIC BUTTONS
                pay_now_text = self.language.get_text('pay_now_button', lang_code)
                check_place_text = self.language.get_text('check_place_order_button', lang_code)
                
                markup.row(
                    telebot.types.InlineKeyboardButton(text=pay_now_text, callback_data=f'cart_deliverable_pay_{order["id"]}'),
                    telebot.types.InlineKeyboardButton(text=check_place_text, callback_data=f'cart_deliverable_place_{order["id"]}')
                )
        else:
            # DIGITAL PRODUCTS - SEPARATE FLOW
            pay_now_text = self.language.get_text('pay_now_button', lang_code)
            check_payment_text = self.language.get_text('check_payment_button', lang_code)
            
            markup.row(
                telebot.types.InlineKeyboardButton(text=pay_now_text, callback_data=f'cart_digital_pay_{order["id"]}'),
                telebot.types.InlineKeyboardButton(text=check_payment_text, callback_data=f'cart_digital_check_{order["id"]}')
            )
        
        # Empty cart button
        empty_cart_text = self.language.get_text('empty_cart_button', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=empty_cart_text,
            callback_data=f'cart_empty_{order["id"]}'
        ))
        
        # Back button
        back_text = self.language.get_text('back_to_menu_button', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
        # Edit message
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=message_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
    
    def build_cart_items_display(self, products, lang_code):
        """Build cart items display string"""
        if not products:
            return ""
        
        # Load categories and products data
        categories_data = self.load_categories()
        products_data = self.load_products()
        
        items = []
        for item in products:
            # Get product details
            product_name = item.get('name', 'Unknown Product')
            quantity = item.get('quantity', 0)
            total_price = self.format_price(item.get('total_price', 0))
            
            # Get category and subcategory names
            category_name = "Unknown"
            subcategory_name = "Unknown"
            
            product_id = item.get('product_id')
            if product_id:
                # Find product in products data
                for p in products_data.get('products', []):
                    if p['id'] == product_id:
                        # Find category and subcategory
                        for cat in categories_data.get('categories', []):
                            if cat['id'] == p['category_id']:
                                category_name = cat['name']
                                for subcat in cat.get('subcategories', []):
                                    if subcat['id'] == p['subcategory_id']:
                                        subcategory_name = subcat['name']
                                        break
                                break
                        break
            
            # Format item display
            item_text = self.language.get_text('cart_item_format', lang_code)
            formatted_item = item_text.format(
                category=category_name,
                subcategory=subcategory_name,
                product=product_name,
                quantity=quantity,
                total=total_price
            )
            items.append(formatted_item)
        
        return "\n\n".join(items)
    
    def handle_delivery_address_input(self, call):
        """Handle delivery address collection"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract order ID
        order_id = call.data.replace('cart_address_', '')
        
        # Set user state for address input
        self.db.set_user_state(
            user_id=user_id,
            state='cart_delivery_address',
            data=json.dumps({
                'lang_code': lang_code,
                'order_id': order_id
            }),
            message_id=call.message.message_id
        )
        
        # Send address prompt
        prompt_text = self.language.get_text('delivery_address_prompt', lang_code)
        
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_menu_button', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='cart_back_clear_state'
        ))
        
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
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_delivery_address_text(self, message):
        """Handle delivery address text input"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        if not user_state or user_state['state'] != 'cart_delivery_address':
            return False
        
        try:
            # user_state['data'] is already parsed by database.py
            state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
            lang_code = state_data['lang_code']
            order_id = state_data['order_id']
        except (json.JSONDecodeError, KeyError):
            return False
        
        # Save delivery address
        delivery_address = message.text.strip()
        
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE orders 
                    SET delivery_address = ?, updated_at = ?
                    WHERE id = ?
                ''', (delivery_address, int(datetime.now().timestamp()), order_id))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error saving delivery address: {e}")
            return True
        
        # Clear user state
        self.db.clear_user_state(user_id)
        
        # Delete user's message
        try:
            self.bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        # Notify with a simple message instead of answer_callback_query (no callback id here)
        success_text = self.language.get_text('delivery_address_saved', lang_code)
        try:
            self.bot.send_message(message.chat.id, success_text)
        except Exception:
            pass
        
        # Redirect back to cart view
        from types import SimpleNamespace
        fake_call = SimpleNamespace()
        fake_call.from_user = message.from_user
        fake_call.message = SimpleNamespace()
        fake_call.message.chat = message.chat
        fake_call.message.message_id = user_state['message_id']
        fake_call.id = None
        
        self.handle_cart_view(fake_call)
        
        return True
    
    def handle_back_clear_state(self, call):
        """Handle back button that clears user state"""
        user_id = call.from_user.id
        self.db.clear_user_state(user_id)
        
        # Redirect to main menu
        from handlers.menu_handler import MenuHandler
        menu_handler = MenuHandler(self.bot, self.db, self.language, self.config)
        
        fake_call = call
        fake_call.data = 'main_menu'
        menu_handler.handle_main_menu(fake_call)
    
    def handle_text_input(self, message):
        """Handle text input for cart states"""
        return self.handle_delivery_address_text(message)
    
    def get_active_order(self, user_id):
        """Get user's active order"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                current_timestamp = int(datetime.now().timestamp())
                
                cursor.execute('''
                    SELECT id, user_id, username, products, total_cost, status, deadline, 
                           delivery_address, payment_track_id, payment_url, created_at
                    FROM orders 
                    WHERE user_id = ? AND status IN ('pending', 'payment_phase') AND deadline > ?
                    ORDER BY created_at DESC LIMIT 1
                ''', (user_id, current_timestamp))
                
                order = cursor.fetchone()
                
                if order:
                    return {
                        'id': order[0],
                        'user_id': order[1],
                        'username': order[2],
                        'products': json.loads(order[3]) if order[3] else [],
                        'total_cost': order[4],
                        'status': order[5],
                        'deadline': order[6],
                        'delivery_address': order[7],
                        'payment_track_id': order[8],
                        'payment_url': order[9],
                        'created_at': order[10]
                    }
                
                return None
                
        except sqlite3.Error as e:
            logger.error(f"Error getting active order: {e}")
            return None
    
    def load_categories(self):
        """Load categories from JSON file with caching"""
        try:
            from json_cache import json_cache
            if os.path.exists('categories.json'):
                data = json_cache.get('categories.json')
                return data if data else {"categories": []}
            return {"categories": []}
        except Exception as e:
            logger.error(f"Error loading categories: {e}")
            return {"categories": []}
    
    def load_products(self):
        """Load products from JSON file with caching"""
        try:
            from json_cache import json_cache
            if os.path.exists('products.json'):
                data = json_cache.get('products.json')
                return data if data else {"products": []}
            return {"products": []}
        except Exception as e:
            logger.error(f"Error loading products: {e}")
            return {"products": []}
    
    def format_price(self, amount):
        """Format price with currency symbol"""
        try:
            currency_symbol = self.config.get('currency', {}).get('symbol', '$')
            return f"{currency_symbol}{amount:.2f}"
        except:
            return f"${amount:.2f}"
    
    def handle_empty_cart_confirmation(self, call):
        """Handle empty cart button - show confirmation dialog"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract order ID from callback data
        try:
            order_id = int(call.data.replace('cart_empty_', ''))
        except ValueError:
            self.bot.answer_callback_query(call.id, "❌ Invalid order ID")
            return
        
        # Get order details with ownership verification
        order = self.get_active_order(user_id)
        if not order or order['id'] != order_id:
            self.bot.answer_callback_query(call.id, "❌ Order not found")
            return
        
        # Show confirmation dialog
        confirm_text = self.language.get_text('empty_cart_confirm', lang_code)
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Yes and No buttons
        markup.row(
            telebot.types.InlineKeyboardButton(text="✅ Yes", callback_data=f'cart_empty_confirm_{order_id}'),
            telebot.types.InlineKeyboardButton(text="❌ No", callback_data=f'cart_view_{order_id}')
        )
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=confirm_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing empty cart confirmation: {e}")
        
        # Answer callback query
        self.bot.answer_callback_query(call.id)
    
    def handle_empty_cart_execute(self, call):
        """Handle empty cart confirmation - actually delete the order"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract order ID from callback data
        try:
            order_id = int(call.data.replace('cart_empty_confirm_', ''))
        except ValueError:
            self.bot.answer_callback_query(call.id, "❌ Invalid order ID")
            return
        
        # Get order details with ownership verification
        order = self.get_active_order(user_id)
        if not order or order['id'] != order_id:
            self.bot.answer_callback_query(call.id, "❌ Order not found")
            return
        
        # Delete the order and restore stock
        success = self.delete_order_and_restore_stock(order_id, order)
        
        if success:
            # Show success message and redirect to main menu
            success_text = self.language.get_text('empty_cart_success', lang_code)
            markup = telebot.types.InlineKeyboardMarkup()
            back_text = self.language.get_text('back_to_menu_button', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_text,
                callback_data='main_menu'
            ))
            
            try:
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=success_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error showing empty cart success: {e}")
            
            # Answer callback query
            self.bot.answer_callback_query(call.id, success_text)
        else:
            # Show error message
            self.bot.answer_callback_query(call.id, "❌ Failed to empty cart. Please try again.", show_alert=True)
    
    def delete_order_and_restore_stock(self, order_id, order):
        """Delete order from database and restore stock for all products"""
        try:
            import sqlite3
            import json
            
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # Get products from order (handle both string and list cases)
                products = order['products']
                logger.info(f"Order products type: {type(products)}, value: {products}")
                
                if isinstance(products, str):
                    products = json.loads(products)
                    logger.info(f"Parsed products from JSON string: {products}")
                elif not isinstance(products, list):
                    logger.error(f"Unexpected products type: {type(products)}")
                    return False
                
                # Restore stock for each product
                for item in products:
                    product_id = item.get('product_id')
                    quantity = item.get('quantity', 0)
                    
                    if product_id and quantity > 0:
                        # Load current products data
                        products_data = self.load_products()
                        
                        # Find and update the product
                        for product in products_data.get('products', []):
                            if product['id'] == product_id:
                                # Restore stock
                                current_stock = product.get('stock', 0)
                                product['stock'] = current_stock + quantity
                                logger.info(f"Restored {quantity} stock to product {product_id}. New stock: {product['stock']}")
                                break
                        
                        # Save updated products data
                        from cache_manager import save_json_safely
                        save_json_safely('products.json', products_data)
                
                # Delete the order from database
                cursor.execute('DELETE FROM orders WHERE id = ?', (order_id,))
                conn.commit()
                
                logger.info(f"Successfully deleted order {order_id} and restored stock")
                return True
                
        except Exception as e:
            logger.error(f"Error deleting order and restoring stock: {e}")
            return False
