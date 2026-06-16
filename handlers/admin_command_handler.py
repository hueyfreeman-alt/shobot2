import telebot
import logging
import sqlite3
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class AdminCommandHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
    
    def handle_delivered_command(self, message):
        """Handle /delivered command"""
        user_id = message.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.send_message(message.chat.id, "❌ Access denied! Admin only.")
            return
        
        try:
            # Extract order ID from command
            command_parts = message.text.split()
            if len(command_parts) != 2:
                self.bot.send_message(
                    message.chat.id, 
                    "❌ Invalid format. Use: /delivered <order_id>\nExample: /delivered 51"
                )
                return
            
            order_id = int(command_parts[1])
            
            # Update order status and notify user
            success = self.update_order_status_delivered(order_id)
            
            if success:
                # Get admin's language for response
                admin_user = self.db.get_user(user_id)
                admin_lang = admin_user['language_code'] if admin_user else 'en'
                success_msg = self.get_admin_text('delivered_success', admin_lang).replace('{order_id}', str(order_id))
                self.bot.send_message(message.chat.id, success_msg)
            else:
                admin_user = self.db.get_user(user_id)
                admin_lang = admin_user['language_code'] if admin_user else 'en'
                error_msg = self.get_admin_text('order_not_found', admin_lang).replace('{order_id}', str(order_id))
                self.bot.send_message(message.chat.id, error_msg)
                
        except ValueError:
            admin_user = self.db.get_user(user_id)
            admin_lang = admin_user['language_code'] if admin_user else 'en'
            error_msg = self.get_admin_text('invalid_order_id', admin_lang)
            self.bot.send_message(message.chat.id, error_msg)
        except Exception as e:
            logger.error(f"Error handling delivered command: {e}")
            admin_user = self.db.get_user(user_id)
            admin_lang = admin_user['language_code'] if admin_user else 'en'
            error_msg = self.get_admin_text('error_processing', admin_lang)
            self.bot.send_message(message.chat.id, error_msg)
    
    def handle_completed_command(self, message):
        """Handle /completed command"""
        user_id = message.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.send_message(message.chat.id, "❌ Access denied! Admin only.")
            return
        
        try:
            # Extract order ID from command
            command_parts = message.text.split()
            if len(command_parts) != 2:
                self.bot.send_message(
                    message.chat.id,
                    "❌ Invalid format. Use: /completed <order_id>\nExample: /completed 51"
                )
                return
            
            order_id = int(command_parts[1])
            
            # Move order to selling history and notify user
            success = self.complete_order(order_id)
            
            if success:
                self.bot.send_message(
                    message.chat.id,
                    f"✅ Order #{order_id} completed and moved to selling history. User has been notified with review option."
                )
            else:
                self.bot.send_message(
                    message.chat.id,
                    f"❌ Order #{order_id} not found or already processed."
                )
                
        except ValueError:
            self.bot.send_message(
                message.chat.id,
                "❌ Invalid order ID. Please provide a valid number."
            )
        except Exception as e:
            logger.error(f"Error handling completed command: {e}")
            self.bot.send_message(
                message.chat.id,
                "❌ Error processing command. Please try again."
            )
    
    def handle_cancelled_command(self, message):
        """Handle /cancelled command"""
        user_id = message.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.send_message(message.chat.id, "❌ Access denied! Admin only.")
            return
        
        try:
            # Extract order ID from command
            command_parts = message.text.split()
            if len(command_parts) != 2:
                self.bot.send_message(
                    message.chat.id,
                    "❌ Invalid format. Use: /cancelled <order_id>\nExample: /cancelled 51"
                )
                return
            
            order_id = int(command_parts[1])
            
            # Cancel order and notify user
            success = self.cancel_order(order_id)
            
            if success:
                self.bot.send_message(
                    message.chat.id,
                    f"✅ Order #{order_id} cancelled and moved to cancelled orders. User has been notified."
                )
            else:
                self.bot.send_message(
                    message.chat.id,
                    f"❌ Order #{order_id} not found or already processed."
                )
                
        except ValueError:
            self.bot.send_message(
                message.chat.id,
                "❌ Invalid order ID. Please provide a valid number."
            )
        except Exception as e:
            logger.error(f"Error handling cancelled command: {e}")
            self.bot.send_message(
                message.chat.id,
                "❌ Error processing command. Please try again."
            )
    
    def update_order_status_delivered(self, order_id):
        """Update order status to delivered and notify user"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Find the order in delivery_queue
                cursor.execute("""
                    SELECT * FROM delivery_queue 
                    WHERE original_order_id = ? AND status = 'awaiting_delivery'
                """, (order_id,))
                
                order = cursor.fetchone()
                if not order:
                    return False
                
                # Update status to delivered
                cursor.execute("""
                    UPDATE delivery_queue 
                    SET status = 'delivered', delivered_date = CURRENT_TIMESTAMP
                    WHERE original_order_id = ?
                """, (order_id,))
                
                conn.commit()
                
                # Notify user
                self.notify_user_delivered(dict(order))
                
                return True
                
        except Exception as e:
            logger.error(f"Error updating order status to delivered: {e}")
            return False
    
    def complete_order(self, order_id):
        """Complete order - move from delivery_queue to selling_history and notify user"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Find the order in delivery_queue
                cursor.execute("""
                    SELECT * FROM delivery_queue 
                    WHERE original_order_id = ?
                """, (order_id,))
                
                order = cursor.fetchone()
                if not order:
                    return False
                
                # Insert into selling_history
                cursor.execute("""
                    INSERT INTO selling_history 
                    (original_order_id, user_id, username, products, total_cost, 
                     delivery_address, payment_track_id, review, order_date, completed_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, CURRENT_TIMESTAMP)
                """, (
                    order['original_order_id'],
                    order['user_id'],
                    order['username'],
                    order['products'],
                    order['total_cost'],
                    order['delivery_address'],
                    order['payment_track_id'],
                    order['order_date']
                ))
                
                # Remove from delivery_queue
                cursor.execute("""
                    DELETE FROM delivery_queue WHERE original_order_id = ?
                """, (order_id,))
                
                conn.commit()
                
                # Notify user and send review option
                self.notify_user_completed(dict(order))
                
                return True
                
        except Exception as e:
            logger.error(f"Error completing order: {e}")
            return False
    
    def cancel_order(self, order_id):
        """Cancel order - move from delivery_queue to cancelled_orders and notify user"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Find the order in delivery_queue
                cursor.execute("""
                    SELECT * FROM delivery_queue 
                    WHERE original_order_id = ?
                """, (order_id,))
                
                order = cursor.fetchone()
                if not order:
                    return False
                
                # Insert into cancelled_orders
                cursor.execute("""
                    INSERT INTO cancelled_orders 
                    (original_order_id, user_id, username, products, total_cost, 
                     delivery_address, payment_track_id, order_date, cancelled_date, cancellation_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'Admin cancelled')
                """, (
                    order['original_order_id'],
                    order['user_id'],
                    order['username'],
                    order['products'],
                    order['total_cost'],
                    order['delivery_address'],
                    order['payment_track_id'],
                    order['order_date']
                ))
                
                # Remove from delivery_queue
                cursor.execute("""
                    DELETE FROM delivery_queue WHERE original_order_id = ?
                """, (order_id,))
                
                conn.commit()
                
                # Notify user
                self.notify_user_cancelled(dict(order))
                
                return True
                
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False
    
    def notify_user_delivered(self, order):
        """Notify user that their order has been delivered"""
        try:
            user_id = order['user_id']
            user = self.db.get_user(user_id)
            if not user:
                return
            
            lang_code = user['language_code']
            
            # Format products for display
            products_text = self.format_products_for_notification(order['products'])
            
            # Get localized message template
            message_template = self.get_notification_text('delivered', 'message', lang_code)
            
            # Replace placeholders
            message_text = message_template.format(
                order_id=order['original_order_id'],
                products=products_text,
                currency=self.config['currency']['symbol'],
                total=f"{order['total_cost']:.2f}",
                address=order['delivery_address']
            )
            
            self.bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Error notifying user about delivery: {e}")
    
    def notify_user_completed(self, order):
        """Notify user that their order is completed and send review option"""
        try:
            user_id = order['user_id']
            user = self.db.get_user(user_id)
            if not user:
                return
            
            lang_code = user['language_code']
            
            # Format products for display
            products_text = self.format_products_for_notification(order['products'])
            
            # Get localized message template
            message_template = self.get_notification_text('completed', 'message', lang_code)
            
            # Replace placeholders
            message_text = message_template.format(
                order_id=order['original_order_id'],
                products=products_text,
                currency=self.config['currency']['symbol'],
                total=f"{order['total_cost']:.2f}"
            )
            
            # Create review button with localized text
            review_button_text = self.get_notification_text('completed', 'review_button', lang_code)
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton(
                text=review_button_text,
                callback_data=f'review_order_{order["original_order_id"]}'
            ))
            
            self.bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Error notifying user about completion: {e}")
    
    def notify_user_cancelled(self, order):
        """Notify user that their order has been cancelled"""
        try:
            user_id = order['user_id']
            user = self.db.get_user(user_id)
            if not user:
                return
            
            lang_code = user['language_code']
            
            # Format products for display
            products_text = self.format_products_for_notification(order['products'])
            
            # Get admin chat link from config
            admin_link = self.config.get('admin_chat_link', 'Admin')
            
            # Get localized message template
            message_template = self.get_notification_text('cancelled', 'message', lang_code)
            
            # Replace placeholders
            message_text = message_template.format(
                order_id=order['original_order_id'],
                products=products_text,
                currency=self.config['currency']['symbol'],
                total=f"{order['total_cost']:.2f}",
                admin_link=admin_link
            )
            
            self.bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Error notifying user about cancellation: {e}")
    
    def format_products_for_notification(self, products_json):
        """Format products JSON for notification display"""
        try:
            if isinstance(products_json, str):
                products = json.loads(products_json)
            else:
                products = products_json
            
            if isinstance(products, list):
                product_names = []
                for product in products:
                    if isinstance(product, dict):
                        name = product.get('name', 'Unknown Product')
                        quantity = product.get('quantity', 1)
                        product_names.append(f"{name} (x{quantity})")
                    else:
                        product_names.append(str(product))
                return ', '.join(product_names)
            else:
                return str(products)
                
        except Exception as e:
            logger.error(f"Error formatting products: {e}")
            return "Error loading products"
    
    def get_admin_text(self, key, lang_code):
        """Get admin command text in specified language"""
        try:
            admin_texts = self.language.languages.get(lang_code, {}).get('admin_commands', {})
            return admin_texts.get(key, f"Text not found: {key}")
        except:
            # Fallback to English
            admin_texts = self.language.languages.get('en', {}).get('admin_commands', {})
            return admin_texts.get(key, f"Text not found: {key}")
    
    def get_notification_text(self, notification_type, key, lang_code):
        """Get notification text in specified language"""
        try:
            notifications = self.language.languages.get(lang_code, {}).get('order_notifications', {})
            return notifications.get(notification_type, {}).get(key, f"Text not found: {notification_type}.{key}")
        except:
            # Fallback to English
            notifications = self.language.languages.get('en', {}).get('order_notifications', {})
            return notifications.get(notification_type, {}).get(key, f"Text not found: {notification_type}.{key}")
