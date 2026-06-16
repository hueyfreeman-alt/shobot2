import telebot
import json
import logging
import time

from telegram_client_optimized import TelebotOptimizedWrapper
from handlers.start_handler import StartHandler
from handlers.menu_handler import MenuHandler
from handlers.admin_handler import AdminHandler
from handlers.category_handler import CategoryHandler
from handlers.product_handler import ProductHandler
from handlers.currency_handler import CurrencyHandler
from handlers.shopping_handler import ShoppingHandler
from handlers.cart_handler import CartHandler
from handlers.payment_handler import PaymentHandler
from handlers.review_handler import ReviewHandler
from handlers.cleanup_handler import CleanupHandler
from handlers.history_handler import HistoryHandler
from handlers.order_management_handler import OrderManagementHandler
from handlers.admin_command_handler import AdminCommandHandler
from handlers.topup_handler import TopupHandler
from handlers.reviews_handler import ReviewsHandler
from handlers.dispute_handler import DisputeHandler
from handlers.button_editor_handler import ButtonEditorHandler
from heartbeat_handler import HeartbeatHandler
from database import Database
from language import Language

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple optimization: Set default timeouts for all requests
def setup_request_optimizations():
    """Set up simple request optimizations that work with all versions"""
    logger.info("🚀 Setting up request optimizations...")
    
    # Set default timeout for all requests to prevent hanging
    import socket
    socket.setdefaulttimeout(10)  # 10 second timeout for all socket operations
    
    logger.info("✅ Request timeout set to 10 seconds - no more 15s hangs!")
    return True

class ShopBot:
    def __init__(self):
        # Load configuration
        with open('config.json', 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Set up request optimizations (prevents 15s hangs)
        setup_request_optimizations()
        
        # Initialize bot with our optimized HTTP client for MUCH faster API calls
        logger.info("🚀 Initializing bot with OptimizedTelegramClient...")
        self.bot = TelebotOptimizedWrapper(
            self.config['bot_token'],
            threaded=True,  # Enable threading for better performance
            num_threads=4,  # Increase thread pool for handling multiple requests
            skip_pending=False  # Keep pending updates to preserve commands after restart
        )
        logger.info("✅ OptimizedTelegramClient initialized - API calls should be MUCH faster now!")
        
        # Pre-warm the API connection to prevent cold start delays
        logger.info("🔥 Pre-warming API connection...")
        if self.bot.warm_connection():
            logger.info("✅ API connection pre-warmed successfully!")
        else:
            logger.warning("⚠️ API pre-warming failed, but bot will continue")
        
        # Initialize database
        self.db = Database()
        
        # Initialize language system
        self.language = Language()
        
        # Preload JSON files for performance
        from json_cache import preload_common_files
        preload_common_files()
        
        # Initialize handlers
        self.start_handler = StartHandler(self.bot, self.db, self.language, self.config)
        self.menu_handler = MenuHandler(self.bot, self.db, self.language, self.config)
        self.admin_handler = AdminHandler(self.bot, self.db, self.language, self.config)
        self.category_handler = CategoryHandler(self.bot, self.db, self.language, self.config)
        self.product_handler = ProductHandler(self.bot, self.db, self.language, self.config)
        self.currency_handler = CurrencyHandler(self.bot, self.db, self.language, self.config)
        self.shopping_handler = ShoppingHandler(self.bot, self.db, self.language, self.config)
        self.cart_handler = CartHandler(self.bot, self.db, self.language, self.config)
        self.payment_handler = PaymentHandler(self.bot, self.db, self.language, self.config)
        self.review_handler = ReviewHandler(self.bot, self.db, self.language, self.config)
        self.cleanup_handler = CleanupHandler(self.bot, self.db, self.language, self.config)
        self.history_handler = HistoryHandler(self.bot, self.db, self.language, self.config)
        self.order_management_handler = OrderManagementHandler(self.bot, self.db, self.language, self.config)
        self.admin_command_handler = AdminCommandHandler(self.bot, self.db, self.language, self.config)
        self.topup_handler = TopupHandler(self.bot, self.db, self.language, self.config)
        self.reviews_handler = ReviewsHandler(self.bot, self.db, self.language, self.config)
        self.dispute_handler = DisputeHandler(self.bot, self.db, self.language, self.config)
        self.button_editor_handler = ButtonEditorHandler(self.bot, self.db, self.language, self.config)
        
        # Initialize high-frequency heartbeat to prevent cold sleep and keep API warm
        self.heartbeat_handler = HeartbeatHandler(self.db, self.bot, interval=10)  # Every 10 seconds - more aggressive
        
        # Set cross-references between handlers
        self.admin_handler.category_handler = self.category_handler
        self.admin_handler.product_handler = self.product_handler
        self.admin_handler.currency_handler = self.currency_handler
        self.admin_handler.payment_handler = self.payment_handler
        self.admin_handler.order_management_handler = self.order_management_handler
        self.admin_handler.dispute_handler = self.dispute_handler
        self.admin_handler.button_editor_handler = self.button_editor_handler
        self.menu_handler.cart_handler = self.cart_handler
        
        # Register handlers
        self.register_handlers()
    
    def register_handlers(self):
        """Register all bot handlers"""
        # Start command
        @self.bot.message_handler(commands=['start'])
        def handle_start(message):
            self.start_handler.handle_start(message)
        
        # Admin commands for order management
        @self.bot.message_handler(commands=['delivered'])
        def handle_delivered_command(message):
            self.admin_command_handler.handle_delivered_command(message)
        
        @self.bot.message_handler(commands=['completed'])
        def handle_completed_command(message):
            self.admin_command_handler.handle_completed_command(message)
        
        @self.bot.message_handler(commands=['cancelled'])
        def handle_cancelled_command(message):
            self.admin_command_handler.handle_cancelled_command(message)
        
        # Health check command (admin only)
        @self.bot.message_handler(commands=['health'])
        def handle_health_check(message):
            user_id = message.from_user.id
            if self.db.is_admin(user_id, self.config.get('admin_user_ids', [])):
                health = self.heartbeat_handler.get_health_status()
                status_emoji = {
                    'HEALTHY': '💚',
                    'WARNING': '⚠️', 
                    'CRITICAL': '🚨',
                    'STOPPED': '💤'
                }.get(health['status'], '❓')
                
                # Get performance stats from optimized client
                perf_stats = self.bot.get_performance_stats()
                
                health_text = f"""
{status_emoji} **Bot Health Status**

**Status:** {health['status']}
**Heartbeat:** {'✅ Alive' if health['is_alive'] else '❌ Dead'}
**Pulse Count:** {health['pulse_count']}
**Failed Pulses:** {health['failed_pulses']}
**Success Rate:** {health['success_rate']:.1f}%
**Last Pulse:** {health['seconds_since_last']:.1f}s ago
**Interval:** {health['interval']}s

**🚀 API Performance (OptimizedClient):**
**Total Requests:** {perf_stats['total_requests']}
**Average Response:** {perf_stats['average_time']}s
**Requests/Second:** {perf_stats['requests_per_second']}
**Total API Time:** {perf_stats['total_time']}s

**Database Pool:**
{self.db.pool.get_stats()}
                """.strip()
                
                self.bot.send_message(message.chat.id, health_text, parse_mode='Markdown')
        
        # Performance stats command (admin only)
        @self.bot.message_handler(commands=['perf', 'performance'])
        def handle_performance_check(message):
            user_id = message.from_user.id
            if self.db.is_admin(user_id, self.config.get('admin_user_ids', [])):
                perf_stats = self.bot.get_performance_stats()
                
                # Calculate performance rating
                avg_time = perf_stats['average_time']
                if avg_time < 1.0:
                    rating = "🚀 EXCELLENT"
                elif avg_time < 2.0:
                    rating = "✅ GOOD"
                elif avg_time < 5.0:
                    rating = "⚠️ SLOW"
                else:
                    rating = "🚨 VERY SLOW"
                
                perf_text = f"""
⚡ **API Performance Report**

**Performance Rating:** {rating}
**Average Response Time:** {avg_time:.3f}s
**Total API Requests:** {perf_stats['total_requests']}
**Total API Time:** {perf_stats['total_time']:.3f}s
**Throughput:** {perf_stats['requests_per_second']} req/s

**🎯 Performance Targets:**
• Excellent: < 1.0s avg
• Good: < 2.0s avg  
• Acceptable: < 5.0s avg

**Before optimization:** ~15s per request 😱
**After optimization:** ~{avg_time:.3f}s per request 🚀
                """.strip()
                
                self.bot.send_message(message.chat.id, perf_text, parse_mode='Markdown')
        
        # File/photo/video handlers for product uploads
        @self.bot.message_handler(content_types=['photo', 'video', 'document'])
        def handle_file_uploads(message):
            user_id = message.from_user.id
            user = self.db.get_user(user_id)
            
            if not user:
                return
            
            # Check if product handler can handle this file
            if self.product_handler.handle_file_input(message):
                return  # File was handled by product handler
        
        # Text message handlers for keyboard buttons and input states
        @self.bot.message_handler(func=lambda message: True)
        def handle_text_messages(message):
            start_time = time.time()
            user_id = message.from_user.id
            user_data = message.from_user
            
            logger.info(f"🔍 DEBUG: Text message received from user {user_id} at {start_time:.3f}")
            logger.info(f"🔍 DEBUG: Message text: '{message.text[:50]}...' (truncated)")
            
            # Always ensure user exists atomically
            db_start = time.time()
            user = self.db.get_or_create_user(
                user_id, 
                user_data.username, 
                user_data.first_name, 
                user_data.last_name, 
                'en'
            )
            db_time = time.time() - db_start
            logger.info(f"🔍 DEBUG: Database get_or_create_user took {db_time:.3f}s")
            
            if not user:
                # Database error
                logger.error(f"🔍 DEBUG: Database error for user {user_id}")
                self.bot.send_message(message.chat.id, "❌ Database error. Please try again.")
                return
            
            if user['is_new']:
                # New user, redirect to start
                logger.info(f"🔍 DEBUG: New user {user_id} auto-created, redirecting to /start")
                self.start_handler.handle_start(message)
                return
            
            # Check handlers in order of specificity
            logger.info(f"🔍 DEBUG: Starting handler checks for user {user_id}")
            
            # 1. Product creation/editing (most specific)
            handler_start = time.time()
            logger.info(f"🔍 DEBUG: Starting product handler check for user {user_id} at {handler_start:.3f}")
            if self.product_handler.handle_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Product handler processed message in {handler_time:.3f}s")
                return
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Product handler check took {handler_time:.3f}s (not handled)")
            
            # 2. Shopping custom amount input
            handler_start = time.time()
            logger.info(f"🔍 DEBUG: Starting shopping handler check for user {user_id} at {handler_start:.3f}")
            if self.shopping_handler.handle_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Shopping handler processed message in {handler_time:.3f}s")
                return  # Input was handled by shopping handler
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Shopping handler check took {handler_time:.3f}s (not handled)")
            
            # 3. Cart delivery address input
            handler_start = time.time()
            logger.info(f"🔍 DEBUG: Starting cart handler check for user {user_id} at {handler_start:.3f}")
            if self.cart_handler.handle_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Cart handler processed message in {handler_time:.3f}s")
                return  # Input was handled by cart handler
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Cart handler check took {handler_time:.3f}s (not handled)")
            
            # 3.5. Button editor text input (admin editing buttons)
            handler_start = time.time()
            if self.button_editor_handler.handle_button_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Button editor handler processed message in {handler_time:.3f}s")
                return
            
            # 3.6. Topup custom amount input
            handler_start = time.time()
            if self.topup_handler.handle_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Topup handler processed message in {handler_time:.3f}s")
                return  # Input was handled by topup handler
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Topup handler check took {handler_time:.3f}s (not handled)")
            
            # 3.6. Dispute message input (user)
            if self.dispute_handler.handle_text_input(message):
                return  # Input was handled by dispute handler
            
            # 3.7. Admin dispute response input
            if self.dispute_handler.handle_admin_text_input(message):
                return  # Input was handled by admin dispute handler
            
            # 4. Review text input
            handler_start = time.time()
            logger.info(f"🔍 DEBUG: Starting review handler check for user {user_id} at {handler_start:.3f}")
            self.review_handler.handle_review_text_input(message)
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Review handler check took {handler_time:.3f}s")
            
            # 5. Category editing
            handler_start = time.time()
            logger.info(f"🔍 DEBUG: Starting category handler check for user {user_id} at {handler_start:.3f}")
            if self.category_handler.handle_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Category handler processed message in {handler_time:.3f}s")
                return  # Input was handled by category handler
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Category handler check took {handler_time:.3f}s (not handled)")
            
            # 6. Store settings editing (admin handler - least specific)
            handler_start = time.time()
            logger.info(f"🔍 DEBUG: Starting admin handler check for user {user_id} at {handler_start:.3f}")
            if self.admin_handler.handle_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Admin handler processed message in {handler_time:.3f}s")
                return  # Input was handled by admin handler
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Admin handler check took {handler_time:.3f}s (not handled)")
            
            lang_code = user['language_code']
            text = message.text
            
            # Check for main menu button
            menu_check_start = time.time()
            logger.info(f"🔍 DEBUG: Starting language text lookup for user {user_id} with lang_code '{lang_code}' at {menu_check_start:.3f}")
            
            lang_start = time.time()
            main_menu_text = self.language.get_text('menu_button_main', lang_code)
            lang_time1 = time.time() - lang_start
            logger.info(f"🔍 DEBUG: Language get_text('menu_button_main') took {lang_time1:.3f}s, result: '{main_menu_text}'")
            
            lang_start = time.time()
            admin_panel_text = self.language.get_text('menu_button_admin', lang_code)
            lang_time2 = time.time() - lang_start
            logger.info(f"🔍 DEBUG: Language get_text('menu_button_admin') took {lang_time2:.3f}s, result: '{admin_panel_text}'")
            
            if text == main_menu_text:
                menu_time = time.time() - menu_check_start
                logger.info(f"🔍 DEBUG: Main menu button detected, processing in {menu_time:.3f}s")
                
                menu_handler_start = time.time()
                self.menu_handler.handle_main_menu_keyboard(message)
                menu_handler_time = time.time() - menu_handler_start
                logger.info(f"🔍 DEBUG: Menu handler execution took {menu_handler_time:.3f}s")
                
            elif text == admin_panel_text:
                menu_time = time.time() - menu_check_start
                logger.info(f"🔍 DEBUG: Admin panel button detected, processing in {menu_time:.3f}s")
                
                admin_handler_start = time.time()
                self.admin_handler.handle_admin_panel_keyboard(message)
                admin_handler_time = time.time() - admin_handler_start
                logger.info(f"🔍 DEBUG: Admin panel handler execution took {admin_handler_time:.3f}s")
                
            else:
                menu_time = time.time() - menu_check_start
                logger.info(f"🔍 DEBUG: No menu button match, check took {menu_time:.3f}s")
            
            total_time = time.time() - start_time
            logger.info(f"🔍 DEBUG: Total text message processing took {total_time:.3f}s for user {user_id}")
        
        # Callback query handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
        def handle_language_selection(call):
            self.start_handler.handle_language_selection(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'main_menu')
        def handle_main_menu(call):
            self.menu_handler.handle_main_menu(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_panel')
        def handle_admin_panel(call):
            self.admin_handler.handle_admin_panel(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('menu_'))
        def handle_menu_buttons(call):
            # Try menu handler first
            handled = self.menu_handler.handle_menu_buttons(call)
            if not handled:
                # If menu handler didn't handle it (products/cart), try appropriate handler
                if call.data == 'menu_products':
                    self.shopping_handler.handle_products_menu(call)
                elif call.data == 'menu_cart':
                    self.cart_handler.handle_cart_view(call)
                elif call.data == 'menu_history':
                    self.history_handler.handle_history_menu(call)
                elif call.data == 'menu_topup':
                    self.topup_handler.handle_topup_menu(call)
                elif call.data == 'menu_reviews':
                    self.reviews_handler.handle_reviews_menu(call)
                elif call.data == 'menu_disputes':
                    self.dispute_handler.handle_disputes_menu(call)
        
        # Specific admin handlers MUST come before general admin_ handler
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_chat_setup_back')
        def handle_admin_chat_setup_back(call):
            self.admin_handler.handle_admin_setup_back(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'payment_setup_back')
        def handle_payment_setup_back(call):
            self.admin_handler.handle_payment_setup_back(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'store_back_to_settings')
        def handle_back_to_store_settings(call):
            self.admin_handler.handle_back_to_settings(call)
        
        # General admin handler - MUST be after specific handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
        def handle_admin_buttons(call):
            self.admin_handler.handle_admin_buttons(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('store_edit_'))
        def handle_store_edit_buttons(call):
            self.admin_handler.handle_store_edit_buttons(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'coming_soon_feature')
        def handle_coming_soon_feature(call):
            # Just answer the callback query to dismiss the loading state
            self.bot.answer_callback_query(call.id)
        
        # Category management handlers
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_categories')
        def handle_categories_management(call):
            self.category_handler.handle_categories_management(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cat_view_'))
        def handle_category_view(call):
            self.category_handler.handle_category_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'cat_add_new')
        def handle_add_new_category(call):
            self.category_handler.handle_add_new_category(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('subcat_add_'))
        def handle_add_new_subcategory(call):
            self.category_handler.handle_add_new_subcategory(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cat_edit_'))
        def handle_edit_category(call):
            self.category_handler.handle_edit_category(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cat_delete_'))
        def handle_delete_category(call):
            self.category_handler.handle_delete_category(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cat_confirm_delete_'))
        def handle_confirm_delete_category(call):
            self.category_handler.handle_confirm_delete_category(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cat_back_'))
        def handle_category_back_buttons(call):
            self.category_handler.handle_back_buttons(call)
        
        # Subcategory management handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('subcat_edit_'))
        def handle_edit_subcategory(call):
            self.category_handler.handle_edit_subcategory(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('subcat_delete_'))
        def handle_delete_subcategory(call):
            self.category_handler.handle_delete_subcategory(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('subcat_confirm_delete_'))
        def handle_confirm_delete_subcategory(call):
            self.category_handler.handle_confirm_delete_subcategory(call)
        
        # Product management handlers
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_products')
        def handle_products_management(call):
            self.product_handler.handle_products_management(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_cat_'))
        def handle_product_category_view(call):
            self.product_handler.handle_product_category_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_subcat_'))
        def handle_product_subcategory_view(call):
            self.product_handler.handle_product_subcategory_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_view_'))
        def handle_product_view(call):
            self.product_handler.handle_product_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_add_'))
        def handle_add_new_product(call):
            self.product_handler.handle_add_new_product(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_premium_alert')
        def handle_premium_alert(call):
            self.product_handler.handle_premium_alert(call)
        
        # Product creation flow handlers
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_proceed_step_6')
        def handle_proceed_step_6(call):
            self.product_handler.creation_handler.proceed_to_step_6(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_type_'))
        def handle_product_type_selection(call):
            self.product_handler.creation_handler.handle_product_type_selection(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_files_complete')
        def handle_files_complete(call):
            try:
                # Answer callback query first to remove loading state
                self.bot.answer_callback_query(call.id)
                
                # Proceed to review settings for downloadable products
                user_state = self.db.get_user_state(call.from_user.id)
                if not user_state:
                    logger.error(f"No user state found for upload complete - user {call.from_user.id}")
                    self.bot.send_message(call.message.chat.id, "❌ Session expired. Please start over.")
                    return
                
                import json
                try:
                    # Handle both dict and string data formats
                    if isinstance(user_state['data'], dict):
                        state_data = user_state['data']
                    else:
                        state_data = json.loads(user_state['data'])
                    
                    lang_code = state_data['lang_code']
                    product_data = state_data['product_data']
                    
                    # Validate we have files uploaded
                    if 'files' not in product_data or len(product_data['files']) == 0:
                        logger.warning(f"Upload complete clicked but no files found - user {call.from_user.id}")
                        self.bot.send_message(call.message.chat.id, "❌ No files uploaded. Please upload files first.")
                        return
                    
                    logger.info(f"Processing upload complete for user {call.from_user.id} - {len(product_data['files'])} files")
                    self.product_handler.creation_handler.proceed_to_review_settings(call.message, call.from_user.id, lang_code, product_data)
                    
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error in upload complete: {e}")
                    self.bot.send_message(call.message.chat.id, "❌ Session data corrupted. Please start over.")
                except Exception as e:
                    logger.error(f"Error in upload complete handler: {e}")
                    self.bot.send_message(call.message.chat.id, "❌ Error processing upload. Please try again.")
                    
            except Exception as e:
                logger.error(f"Critical error in handle_files_complete: {e}")
                try:
                    self.bot.answer_callback_query(call.id, "❌ Error occurred")
                except:
                    pass
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_save_final')
        def handle_save_final_product(call):
            self.product_handler.creation_handler.save_final_product(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_cancel_upload')
        def handle_cancel_product_upload(call):
            self.product_handler.creation_handler.cancel_product_creation(call)
        
        # Product editing handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_edit_'))
        def handle_product_edit_buttons(call):
            self.product_handler.handle_product_edit_buttons(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_toggle_visibility_'))
        def handle_product_visibility_toggle(call):
            self.product_handler.handle_product_visibility_toggle(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_delete_'))
        def handle_product_delete(call):
            self.product_handler.handle_product_delete(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_confirm_delete_'))
        def handle_product_confirm_delete(call):
            self.product_handler.handle_product_confirm_delete(call)
        
        # Review settings handlers
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_reviews_enable')
        def handle_reviews_enable(call):
            self.product_handler.creation_handler.handle_reviews_setting(call, True)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_reviews_disable')
        def handle_reviews_disable(call):
            self.product_handler.creation_handler.handle_reviews_setting(call, False)
         
        # Review edit handlers for existing products
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_set_reviews_'))
        def handle_set_reviews(call):
            self.product_handler.handle_set_reviews(call)
        
        # Upload more handler for downloadable/line products
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_upload_more_'))
        def handle_upload_more(call):
            self.product_handler.handle_upload_more(call)
        
        # Currency management handlers
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_currency_settings')
        def handle_currency_settings(call):
            self.currency_handler.handle_currency_settings(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'currency_popular')
        def handle_popular_currencies(call):
            self.currency_handler.handle_popular_currencies(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'currency_all')
        def handle_all_currencies(call):
            self.currency_handler.handle_all_currencies(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('currency_page_'))
        def handle_currency_page(call):
            self.currency_handler.handle_currency_page(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('currency_select_'))
        def handle_currency_selection(call):
            self.currency_handler.handle_currency_selection(call)
        
        # Shopping handlers (keep the specific shopping actions)
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('shop_cat_'))
        def handle_shop_category_view(call):
            self.shopping_handler.handle_category_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('shop_subcat_'))
        def handle_shop_subcategory_view(call):
            self.shopping_handler.handle_subcategory_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('shop_product_'))
        def handle_shop_product_view(call):
            self.shopping_handler.handle_product_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('shop_add_') or call.data.startswith('shop_sub_'))
        def handle_add_to_cart(call):
            self.shopping_handler.handle_add_to_cart(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('shop_custom_'))
        def handle_custom_amount(call):
            self.shopping_handler.handle_custom_amount(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'shopping_back_clear_state')
        def handle_shopping_back_clear_state(call):
            self.shopping_handler.handle_back_clear_state(call)
        
        # Cart handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_address_'))
        def handle_cart_address(call):
            self.cart_handler.handle_delivery_address_input(call)
        
        # Empty cart handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_empty_confirm_'))
        def handle_empty_cart_execute(call):
            self.cart_handler.handle_empty_cart_execute(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_view_'))
        def handle_cart_view_return(call):
            self.cart_handler.handle_cart_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_empty_'))
        def handle_empty_cart_confirmation(call):
            self.cart_handler.handle_empty_cart_confirmation(call)
        
        # DELIVERABLE PRODUCTS - SEPARATE HANDLERS
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_deliverable_pay_'))
        def handle_deliverable_pay(call):
            self.payment_handler.handle_deliverable_pay_now(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_deliverable_place_'))
        def handle_deliverable_place(call):
            self.payment_handler.handle_deliverable_place_order(call)
        
        # DIGITAL PRODUCTS - SEPARATE HANDLERS
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_digital_pay_'))
        def handle_digital_pay(call):
            self.payment_handler.handle_digital_pay_now(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_digital_check_'))
        def handle_digital_check(call):
            self.payment_handler.handle_digital_check_payment(call)
        
        # PAYMENT COIN SELECTION HANDLERS
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('payment_balance_'))
        def handle_payment_balance(call):
            self.payment_handler.handle_balance_payment(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('payment_coin_'))
        def handle_payment_coin_selection(call):
            self.payment_handler.handle_coin_selection(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('copy_address_'))
        def handle_copy_address(call):
            self.payment_handler.handle_copy_address(call)
        
        # TOPUP HANDLERS
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('topup_amount_'))
        def handle_topup_amount(call):
            self.topup_handler.handle_amount_selection(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'topup_custom')
        def handle_topup_custom(call):
            self.topup_handler.handle_custom_amount(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('topup_coin_'))
        def handle_topup_coin(call):
            self.topup_handler.handle_coin_selection(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('topup_copy_'))
        def handle_topup_copy(call):
            self.topup_handler.handle_copy_address(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('topup_cancel_'))
        def handle_topup_cancel(call):
            self.topup_handler.handle_cancel_invoice(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'cart_back_clear_state')
        def handle_cart_back_clear_state(call):
            self.cart_handler.handle_back_clear_state(call)
        
        # Review handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('review_order_'))
        def handle_review_order(call):
            self.review_handler.handle_review_order(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('review_rating:'))
        def handle_review_rating(call):
            self.review_handler.handle_rating_selection(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'review_back_clear_state')
        def handle_review_back_clear_state(call):
            self.review_handler.handle_back_clear_state(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('product_reviews_'))
        def handle_product_reviews(call):
            self.review_handler.handle_product_reviews(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('back_to_product_'))
        def handle_back_to_product(call):
            self.review_handler.handle_back_to_product(call)
        
        # History handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('history_completed_'))
        def handle_history_completed(call):
            self.history_handler.handle_completed_orders(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('history_queue_'))
        def handle_history_queue(call):
            self.history_handler.handle_queue_orders(call)
        
        # Order management handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('order_download_'))
        def handle_order_download(call):
            self.order_management_handler.handle_order_download(call)
        
        # Reviews handlers (public reviews page)
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('reviews_'))
        def handle_reviews_callbacks(call):
            self.reviews_handler.handle_reviews_callbacks(call)
        
        # Dispute handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('dispute_'))
        def handle_dispute_callbacks(call):
            self.dispute_handler.handle_disputes_callbacks(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_disputes')
        def handle_admin_disputes(call):
            self.dispute_handler.show_admin_disputes(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('admin_dispute_'))
        def handle_admin_dispute_actions(call):
            self.dispute_handler.handle_disputes_callbacks(call)
        
        # Button editor handlers
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_edit_buttons')
        def handle_export_buttons(call):
            self.button_editor_handler.handle_export_buttons(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('button_edit_'))
        def handle_button_category(call):
            self.button_editor_handler.handle_button_category(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'button_edit_cancel')
        def handle_cancel_button_edit(call):
            self.button_editor_handler.handle_cancel_edit(call)
        
        # Fallback handler for unhandled callback queries (prevents hanging buttons)
        @self.bot.callback_query_handler(func=lambda call: True)
        def handle_unhandled_callbacks(call):
            logger.warning(f"⚠️ Unhandled callback query: {call.data} from user {call.from_user.id}")
            self.safe_answer_callback_query(call, "⚠️ Action not recognized. Please try again.", show_alert=True)
    
    def safe_answer_callback_query(self, call, text=None, show_alert=False):
        """Safely answer callback query with fallback to regular message for important alerts"""
        if not hasattr(call, 'id') or call.id is None:
            logger.debug("🚫 Invalid callback query - missing ID")
            return False
        
        # Try to answer the callback query
        success = self.bot.answer_callback_query(call.id, text, show_alert=show_alert)
        
        # If callback query failed but we have important text to show, send as regular message
        if not success and text and show_alert and hasattr(call, 'from_user'):
            try:
                self.bot.send_message(call.from_user.id, f"⚠️ {text}")
                logger.debug(f"📱 Sent fallback message to user {call.from_user.id}: {text[:50]}...")
                return True
            except Exception as msg_error:
                logger.error(f"Failed to send fallback message: {msg_error}")
                return False
        
        return success
    
    def run(self):
        """Start the bot"""
        logger.info("🚀 Bot started successfully!")
        
        # Start high-frequency heartbeat to prevent cold sleep
        self.heartbeat_handler.start_heartbeat()
        
        # Start automatic cleanup service
        self.cleanup_handler.start_cleanup_service()
        
        # Start topup invoice checker (checks every 30 seconds)
        self.topup_handler.start_invoice_checker()
        
        try:
            # Use optimized infinity polling for faster response times
            self.bot.infinity_polling(
                timeout=10,  # Shorter timeout to detect connection issues faster
                long_polling_timeout=10,  # Reduce long polling timeout
                allowed_updates=None  # Process all update types
            )
        except KeyboardInterrupt:
            logger.info("🛑 Bot shutdown requested by user")
        except Exception as e:
            logger.error(f"💥 Bot polling error: {e}")
        finally:
            # Clean shutdown
            logger.info("🔄 Shutting down services...")
            self.heartbeat_handler.stop_heartbeat()
            self.cleanup_handler.stop_cleanup_service()
            logger.info("✅ Bot stopped gracefully")

if __name__ == "__main__":
    bot = ShopBot()
    bot.run()
