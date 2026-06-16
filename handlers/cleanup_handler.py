import threading
import time
import sqlite3
import json
import logging
from datetime import datetime
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class CleanupHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.cleanup_thread = None
        self.running = False
        
        # Get cleanup interval from config (default 5 minutes)
        self.cleanup_interval = config.get('cleanup_interval_minutes', 5) * 60  # Convert to seconds
        self.order_expiry_minutes = config.get('order_expiry_minutes', 15)
    
    def start_cleanup_service(self):
        """Start the automatic cleanup service"""
        if not self.running:
            self.running = True
            self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
            self.cleanup_thread.start()
            logger.info(f"Order cleanup service started - runs every {self.cleanup_interval/60} minutes")
    
    def stop_cleanup_service(self):
        """Stop the automatic cleanup service"""
        self.running = False
        if self.cleanup_thread:
            self.cleanup_thread.join()
        logger.info("Order cleanup service stopped")
    
    def _cleanup_loop(self):
        """Main cleanup loop that runs periodically"""
        while self.running:
            try:
                self.cleanup_expired_orders()
                time.sleep(self.cleanup_interval)
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                time.sleep(60)  # Wait 1 minute before retrying
    
    def cleanup_expired_orders(self):
        """Clean up expired orders and restore stock"""
        try:
            current_timestamp = int(time.time())
            expiry_threshold = current_timestamp - (self.order_expiry_minutes * 60)
            
            # Find expired orders
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # Get expired orders (created_at + expiry_minutes < current_time)
                cursor.execute('''
                    SELECT id, user_id, username, products, total_cost, created_at, deadline
                    FROM orders 
                    WHERE status = 'pending' AND deadline < ?
                ''', (current_timestamp,))
                
                expired_orders = cursor.fetchall()
                
                if not expired_orders:
                    logger.debug("No expired orders found")
                    return
                
                logger.info(f"Found {len(expired_orders)} expired orders to clean up")
                
                for order_data in expired_orders:
                    order_id, user_id, username, products_json, total_cost, created_at, deadline = order_data
                    
                    try:
                        products = json.loads(products_json)
                        
                        # Restore stock for each product in the order
                        self.restore_stock_for_order(order_id, products)
                        
                        # Delete the expired order
                        cursor.execute('DELETE FROM orders WHERE id = ?', (order_id,))
                        
                        # Notify user about order expiration
                        self.notify_user_order_expired(user_id, order_id, username)
                        
                        logger.info(f"Cleaned up expired order {order_id} for user {user_id}")
                        
                    except Exception as e:
                        logger.error(f"Error cleaning up order {order_id}: {e}")
                        continue
                
                conn.commit()
                logger.info(f"Successfully cleaned up {len(expired_orders)} expired orders")
                
        except sqlite3.Error as e:
            logger.error(f"Database error during cleanup: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during cleanup: {e}")
    
    def restore_stock_for_order(self, order_id, products):
        """Restore stock amounts for products in an expired order"""
        try:
            # Load current products data
            with open('products.json', 'r', encoding='utf-8') as f:
                products_data = json.load(f)
            
            # Track changes
            changes_made = False
            
            for product_item in products:
                product_id = product_item.get('product_id')
                quantity = product_item.get('quantity', 0)
                
                if not product_id or quantity <= 0:
                    continue
                
                # Find the product in products.json
                for product in products_data.get('products', []):
                    if product['id'] == product_id:
                        # Remove the reserved stock entry for this order
                        reserved_stock = product.get('reserved_stock', [])
                        original_reserved = len(reserved_stock)
                        
                        # Filter out reservations for this order
                        updated_reserved = [
                            res for res in reserved_stock 
                            if res.get('order_id') != order_id
                        ]
                        
                        # Calculate how much stock to restore
                        removed_reservations = original_reserved - len(updated_reserved)
                        if removed_reservations > 0:
                            # Restore stock amount
                            current_stock = product.get('stock', 0)
                            product['stock'] = current_stock + quantity
                            product['reserved_stock'] = updated_reserved
                            
                            logger.info(f"Restored {quantity} stock for product {product_id} (order {order_id})")
                            changes_made = True
                        
                        break
            
            # Save updated products data if changes were made
            if changes_made:
                save_json_safely("products.json", products_data)
                logger.info(f"Stock restored for expired order {order_id}")
            
        except Exception as e:
            logger.error(f"Error restoring stock for order {order_id}: {e}")
    
    def notify_user_order_expired(self, user_id, order_id, username):
        """Notify user that their order has expired"""
        try:
            # Get user's language preference
            user = self.db.get_or_create_user(user_id)
            if not user:
                return
            
            lang_code = user['language_code']
            
            # Get expiry message
            expiry_message = self.language.get_text('order_expired_message', lang_code)
            expiry_minutes = self.order_expiry_minutes
            
            message = expiry_message.format(
                order_id=order_id,
                minutes=expiry_minutes
            )
            
            # Send notification to user
            self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML'
            )
            
            logger.info(f"Sent expiry notification to user {user_id} for order {order_id}")
            
        except Exception as e:
            logger.error(f"Error notifying user {user_id} about expired order {order_id}: {e}")
    
    def get_order_expiry_warning_text(self, lang_code):
        """Get order expiry warning text for cart/product pages"""
        warning_text = self.language.get_text('order_expiry_warning', lang_code)
        return warning_text.format(minutes=self.order_expiry_minutes)
    
    def manual_cleanup(self):
        """Manually trigger cleanup (for testing or admin use)"""
        logger.info("Manual cleanup triggered")
        self.cleanup_expired_orders()
        return "Cleanup completed"
