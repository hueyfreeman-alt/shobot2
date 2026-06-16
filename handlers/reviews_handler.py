import telebot
import logging
import math

logger = logging.getLogger(__name__)

class ReviewsHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.per_page = 3  # Reviews per page
    
    def handle_reviews_menu(self, call):
        """Handle reviews button click - show all reviews with pagination"""
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error")
            return
        
        lang_code = user['language_code']
        
        # Show first page
        self.show_reviews_page(call, 1, lang_code)
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    def show_reviews_page(self, call, page, lang_code):
        """Show reviews page with pagination"""
        # Get average rating
        rating_data = self.db.get_average_rating()
        avg_rating = rating_data['average']
        total_count = rating_data['count']
        
        # Get reviews for this page
        reviews = self.db.get_all_reviews(page=page, per_page=self.per_page)
        
        # Calculate total pages
        total_pages = max(1, math.ceil(total_count / self.per_page))
        
        # Build message
        texts = self.language.get_text('reviews', lang_code)
        
        text = f"{texts.get('title', '⭐ Customer Reviews')}\n\n"
        
        # Show average rating
        avg_text = texts.get('average_rating', '📊 Average Rating: {rating}/5 ⭐ ({count} reviews)')
        text += avg_text.format(rating=avg_rating, count=total_count) + "\n\n"
        
        if not reviews:
            text += texts.get('no_reviews', '📝 No reviews yet.')
        else:
            # Add separator
            text += "━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for review in reviews:
                # Convert star rating to stars
                stars = "⭐" * review['star_rating'] + "☆" * (5 - review['star_rating'])
                
                # Get username or show "Anonymous"
                username = review['username'] if review['username'] else "Anonymous"
                
                # Truncate review text if too long
                review_text = review['review_text'] or "No comment"
                if len(review_text) > 150:
                    review_text = review_text[:147] + "..."
                
                # Format date
                date = review['review_date'][:10] if review['review_date'] else "Unknown"
                
                # Products
                products = review['products'][:50] + "..." if len(review['products']) > 50 else review['products']
                
                review_template = texts.get('review_item', '⭐ {stars}\n👤 @{username}\n📦 {products}\n💬 {text}\n📅 {date}')
                text += review_template.format(
                    stars=stars,
                    username=username,
                    products=products,
                    text=review_text,
                    date=date
                ) + "\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            # Page info
            page_info = texts.get('page_info', '📄 Page {current} of {total}')
            text += page_info.format(current=page, total=total_pages)
        
        # Build markup with pagination
        markup = telebot.types.InlineKeyboardMarkup(row_width=3)
        
        # Pagination buttons
        pagination_buttons = []
        
        if page > 1:
            pagination_buttons.append(
                telebot.types.InlineKeyboardButton(
                    text="⬅️ Prev",
                    callback_data=f"reviews_page_{page - 1}"
                )
            )
        
        if total_count > 0:
            pagination_buttons.append(
                telebot.types.InlineKeyboardButton(
                    text=f"{page}/{total_pages}",
                    callback_data="ignore"
                )
            )
        
        if page < total_pages:
            pagination_buttons.append(
                telebot.types.InlineKeyboardButton(
                    text="Next ➡️",
                    callback_data=f"reviews_page_{page + 1}"
                )
            )
        
        if pagination_buttons:
            markup.row(*pagination_buttons)
        
        # Back button
        back_text = texts.get('back_to_menu', '🔙 Back to Menu')
        markup.row(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data="main_menu"
        ))
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing reviews: {e}")
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
    
    def handle_reviews_callbacks(self, call):
        """Handle reviews-related callbacks"""
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        
        if call.data.startswith('reviews_page_'):
            page = int(call.data.replace('reviews_page_', ''))
            self.show_reviews_page(call, page, lang_code)
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
