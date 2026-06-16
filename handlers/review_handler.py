import telebot
import logging
import json
import sqlite3
from datetime import datetime
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class ReviewHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
    
    def handle_review_order(self, call):
        """Handle review order button - find most recent order to review"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Find most recent order that needs review
        recent_order = self.get_most_recent_reviewable_order(user_id)
        
        if not recent_order:
            # No orders to review
            no_orders_text = self.language.get_text('all_reviews_completed', lang_code)
            
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
                    text=no_orders_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            except:
                pass
            return
        
        # Show order summary and rating options
        self.show_rating_selection(call, recent_order, lang_code)
    
    def get_most_recent_reviewable_order(self, user_id):
        """Get the most recent order that needs review from selling_history table"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # Only check selling_history since all completed orders (digital and deliverable) end up here
                cursor.execute('''
                    SELECT 'selling_history' as source, id, original_order_id, user_id, username, 
                           products, total_cost, delivery_address, payment_track_id, 
                           order_date, completed_date, 
                           CASE WHEN review IS NULL THEN 'pending' ELSE review END as review
                    FROM selling_history 
                    WHERE user_id = ? AND (review IS NULL OR review = 'pending' OR review = '')
                    ORDER BY completed_date DESC
                    LIMIT 1
                ''', (user_id,))
                
                result = cursor.fetchone()
                
                if result:
                    return self.format_order_result(result)
                else:
                    return None
                    
        except sqlite3.Error as e:
            logger.error(f"Error getting reviewable order: {e}")
            return None
    
    def format_order_result(self, result):
        """Format database result into order dict"""
        if not result:
            return None
            
        return {
            'source': result[0],
            'id': result[1],
            'original_order_id': result[2],
            'user_id': result[3],
            'username': result[4],
            'products': json.loads(result[5]),
            'total_cost': result[6],
            'delivery_address': result[7],
            'payment_track_id': result[8],
            'order_date': result[9],
            'date': result[10],
            'review': result[11] if len(result) > 11 else 'pending'
        }
    
    def show_rating_selection(self, call, order, lang_code):
        """Show order summary and star rating selection"""
        # Build order summary
        summary_title = self.language.get_text('review_summary_title', lang_code)
        rating_prompt = self.language.get_text('review_rating_prompt', lang_code)
        
        message = f"<b>{summary_title}</b>\n\n"
        message += f"🆔 <b>Order ID:</b> {order['original_order_id']}\n"
        message += f"📅 <b>Date:</b> {order['date']}\n\n"
        
        message += "<b>📦 Products:</b>\n"
        for item in order['products']:
            message += f"• {item['name']} x{item['quantity']} - ${item['total_price']:.2f}\n"
        
        message += f"\n💰 <b>Total:</b> ${order['total_cost']:.2f}\n\n"
        message += f"<b>{rating_prompt}</b>"
        
        # Create star rating buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Row 1: 1-2 stars
        markup.row(
            telebot.types.InlineKeyboardButton(
                text=self.language.get_text('star_1', lang_code),
                callback_data=f'review_rating:{order["source"]}:{order["id"]}:1'
            ),
            telebot.types.InlineKeyboardButton(
                text=self.language.get_text('star_2', lang_code),
                callback_data=f'review_rating:{order["source"]}:{order["id"]}:2'
            )
        )
        
        # Row 2: 3-4 stars  
        markup.row(
            telebot.types.InlineKeyboardButton(
                text=self.language.get_text('star_3', lang_code),
                callback_data=f'review_rating:{order["source"]}:{order["id"]}:3'
            ),
            telebot.types.InlineKeyboardButton(
                text=self.language.get_text('star_4', lang_code),
                callback_data=f'review_rating:{order["source"]}:{order["id"]}:4'
            )
        )
        
        # Row 3: 5 stars
        markup.add(telebot.types.InlineKeyboardButton(
            text=self.language.get_text('star_5', lang_code),
            callback_data=f'review_rating:{order["source"]}:{order["id"]}:5'
        ))
        
        # Back button
        back_text = self.language.get_text('back_to_menu_button', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='review_back_clear_state'
        ))
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=message,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing rating selection: {e}")
    
    def handle_rating_selection(self, call):
        """Handle star rating selection"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Parse callback data: review_rating:source:id:rating
        parts = call.data.split(':')
        if len(parts) != 4:
            logger.error(f"Invalid rating callback data: {call.data}")
            return
        
        source = parts[1]  # selling_history or delivery_queue
        order_id = int(parts[2])
        rating = int(parts[3])
        
        # Store rating in user state and ask for text review
        self.db.set_user_state(user_id, 'review_text_input', {
            'source': source,
            'order_id': order_id,
            'rating': rating
        })
        
        # Ask for text review
        review_text_prompt = self.language.get_text('review_text_prompt', lang_code)
        placeholder = self.language.get_text('review_text_placeholder', lang_code)
        
        selected_rating = self.language.get_text(f'star_{rating}', lang_code)
        
        message = f"<b>{selected_rating}</b> ✅\n\n{review_text_prompt}\n\n<i>{placeholder}</i>"
        
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_menu_button', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='review_back_clear_state'
        ))
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=message,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error asking for review text: {e}")
    
    def handle_review_text_input(self, message):
        """Handle review text input"""
        user_id = message.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            return
        
        lang_code = user['language_code']
        
        # Get user state
        state = self.db.get_user_state(user_id)
        if not state or state.get('state') != 'review_text_input':
            return
        
        review_data = state.get('data', {})
        source = review_data.get('source')
        order_id = review_data.get('order_id')
        rating = review_data.get('rating')
        review_text = message.text
        
        # Get order details
        order = self.get_order_from_source(source, order_id)
        if not order:
            self.bot.send_message(message.chat.id, "Order not found.")
            return
        
        # Save review to reviews table
        self.save_review(order, rating, review_text, source)
        
        # Mark order as reviewed
        self.mark_order_as_reviewed(source, order_id)
        
        # Clear user state
        self.db.clear_user_state(user_id)
        
        # Delete user's message
        try:
            self.bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        # Send thank you message
        thank_you = self.language.get_text('review_thank_you', lang_code)
        saved_text = self.language.get_text('review_saved', lang_code)
        
        message_text = f"{thank_you}\n\n{saved_text}"
        
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_menu_button', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=message_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def get_order_from_source(self, source, order_id):
        """Get order details from selling_history table (all completed orders are here)"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # All completed orders (digital and deliverable) are in selling_history
                cursor.execute('''
                    SELECT id, original_order_id, user_id, username, products, 
                           total_cost, delivery_address, payment_track_id, order_date
                    FROM selling_history WHERE id = ?
                ''', (order_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        'id': result[0],
                        'original_order_id': result[1],
                        'user_id': result[2],
                        'username': result[3],
                        'products': json.loads(result[4]),
                        'total_cost': result[5],
                        'delivery_address': result[6],
                        'payment_track_id': result[7],
                        'order_date': result[8]
                    }
                return None
                
        except sqlite3.Error as e:
            logger.error(f"Error getting order from selling_history: {e}")
            return None
    
    def save_review(self, order, rating, review_text, order_type):
        """Save review to reviews table"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # Extract product IDs
                product_ids = [str(item.get('product_id', '')) for item in order['products']]
                product_ids_json = json.dumps(product_ids)
                
                cursor.execute('''
                    INSERT INTO reviews (
                        order_id, user_id, username, product_ids, products,
                        star_rating, review_text, order_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    order['original_order_id'], order['user_id'], order.get('username', ''),
                    product_ids_json, json.dumps(order['products']),
                    rating, review_text, order_type
                ))
                conn.commit()
                logger.info(f"Review saved for order {order['original_order_id']}")
                
        except sqlite3.Error as e:
            logger.error(f"Error saving review: {e}")
    
    def mark_order_as_reviewed(self, source, order_id):
        """Mark order as reviewed in selling_history table"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # All completed orders are in selling_history
                cursor.execute('''
                    UPDATE selling_history SET review = 'done' WHERE id = ?
                ''', (order_id,))
                
                conn.commit()
                logger.info(f"Order {order_id} marked as reviewed in selling_history")
                
        except sqlite3.Error as e:
            logger.error(f"Error marking order as reviewed: {e}")
    
    def get_product_review_summary(self, product_id):
        """Get review summary for a product"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # Get all reviews for this product
                cursor.execute('''
                    SELECT star_rating, COUNT(*) as count
                    FROM reviews 
                    WHERE product_ids LIKE ?
                    GROUP BY star_rating
                ''', (f'%"{product_id}"%',))
                
                results = cursor.fetchall()
                
                if not results:
                    return None
                
                total_reviews = sum(count for _, count in results)
                total_rating = sum(rating * count for rating, count in results)
                average_rating = round(total_rating / total_reviews, 1)
                
                return {
                    'total_reviews': total_reviews,
                    'average_rating': average_rating
                }
                
        except sqlite3.Error as e:
            logger.error(f"Error getting product review summary: {e}")
            return None
    
    def handle_product_reviews(self, call):
        """Handle product reviews button click"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract product ID from callback data: product_reviews_{product_id}_0
        parts = call.data.split('_')
        if len(parts) < 3:
            logger.error(f"Invalid product reviews callback data: {call.data}")
            return
        
        product_id = parts[2]
        page = int(parts[3]) if len(parts) > 3 else 0
        
        self.show_product_reviews(call, product_id, page, lang_code)
    
    def show_product_reviews(self, call, product_id, page, lang_code):
        """Show product reviews with pagination"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # Get reviews for this product with pagination
                offset = page * 5
                cursor.execute('''
                    SELECT star_rating, review_text, username, review_date
                    FROM reviews 
                    WHERE product_ids LIKE ?
                    ORDER BY review_date DESC
                    LIMIT 5 OFFSET ?
                ''', (f'%"{product_id}"%', offset))
                
                reviews = cursor.fetchall()
                
                # Get total count for pagination
                cursor.execute('''
                    SELECT COUNT(*) FROM reviews WHERE product_ids LIKE ?
                ''', (f'%"{product_id}"%',))
                
                total_reviews = cursor.fetchone()[0]
                
                if not reviews:
                    no_reviews_text = self.language.get_text('no_reviews_found', lang_code)
                    
                    markup = telebot.types.InlineKeyboardMarkup()
                    back_text = self.language.get_text('back_to_product_button', lang_code)
                    markup.add(telebot.types.InlineKeyboardButton(
                        text=back_text,
                        callback_data=f'back_to_product_{product_id}'
                    ))
                    
                    try:
                        self.bot.edit_message_text(
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            text=no_reviews_text,
                            reply_markup=markup,
                            parse_mode='HTML'
                        )
                    except:
                        pass
                    return
                
                # Build reviews message
                message = f"<b>📝 Product Reviews</b>\n\n"
                
                for rating, review_text, username, review_date in reviews:
                    stars = "⭐" * rating
                    message += f"{stars}\n"
                    message += f" |_ {review_text}\n"
                    if username:
                        message += f"    <i>- {username}</i>\n"
                    message += "\n"
                
                # Add pagination info
                start_review = offset + 1
                end_review = min(offset + 5, total_reviews)
                message += f"<i>Showing {start_review}-{end_review} of {total_reviews} reviews</i>"
                
                # Create navigation buttons
                markup = telebot.types.InlineKeyboardMarkup()
                
                # Previous/Next buttons
                nav_buttons = []
                if page > 0:
                    prev_text = "◀️ Previous"
                    nav_buttons.append(telebot.types.InlineKeyboardButton(
                        text=prev_text,
                        callback_data=f'product_reviews_{product_id}_{page-1}'
                    ))
                
                if end_review < total_reviews:
                    next_text = "Next ▶️"
                    nav_buttons.append(telebot.types.InlineKeyboardButton(
                        text=next_text,
                        callback_data=f'product_reviews_{product_id}_{page+1}'
                    ))
                
                if nav_buttons:
                    if len(nav_buttons) == 2:
                        markup.row(*nav_buttons)
                    else:
                        markup.add(nav_buttons[0])
                
                # Back to product button
                back_text = self.language.get_text('back_to_product_button', lang_code)
                markup.add(telebot.types.InlineKeyboardButton(
                    text=back_text,
                    callback_data=f'back_to_product_{product_id}'
                ))
                
                try:
                    self.bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=message,
                        reply_markup=markup,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Error showing product reviews: {e}")
                    
        except sqlite3.Error as e:
            logger.error(f"Error getting product reviews: {e}")
    
    def handle_back_to_product(self, call):
        """Handle back to product button"""
        # Extract product ID from callback data: back_to_product_{product_id}
        parts = call.data.split('_')
        if len(parts) < 4:
            logger.error(f"Invalid back to product callback data: {call.data}")
            return
        
        product_id = parts[3]
        logger.info(f"REVIEW: Attempting to return to product {product_id}")
        
        # Import and initialize shopping handler with proper dependencies
        from handlers.shopping_handler import ShoppingHandler
        from handlers.cart_handler import CartHandler
        
        # Initialize handlers with correct dependencies
        cart_handler = CartHandler(self.bot, self.db, self.language, self.config)
        shopping_handler = ShoppingHandler(self.bot, self.db, self.language, self.config)
        shopping_handler.cart_handler = cart_handler  # Set cart handler reference
        
        # Create a proper callback object that matches what shopping handler expects
        class FakeCall:
            def __init__(self, data, message, from_user, call_id):
                self.data = data
                self.message = message
                self.from_user = from_user
                self.id = call_id
        
        fake_call = FakeCall(
            data=f'shop_product_{product_id}',
            message=call.message,
            from_user=call.from_user,
            call_id=call.id
        )
        
        shopping_handler.handle_product_view(fake_call)
    
    def handle_back_clear_state(self, call):
        """Handle back button - clear state and return to menu"""
        user_id = call.from_user.id
        self.db.clear_user_state(user_id)
        
        # Redirect to main menu
        from handlers.menu_handler import MenuHandler
        menu_handler = MenuHandler(self.bot, self.db, self.language, self.config)
        menu_handler.handle_main_menu(call.message.chat.id)