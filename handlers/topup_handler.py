import telebot
import logging
import json
import requests
import time
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

class TopupHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        
        self.oxapay_api_key = config.get('oxapay_api_key', '')
        self.oxapay_sandbox = config.get('oxapay_sandbox', True)  # Use sandbox for topup
        
        # Auto-checker worker
        self.checker_thread = None
        self.checker_running = False
        self.check_interval = 30  # Check every 30 seconds
        
        logger.info(f"💳 TopupHandler Initialized:")
        logger.info(f"   - Sandbox Mode: {self.oxapay_sandbox}")
        logger.info(f"   - API Key Present: {'Yes' if self.oxapay_api_key else 'No'}")
    
    # ==================== TOPUP MENU ====================
    
    def handle_topup_menu(self, call):
        """Handle topup button click - show topup menu or existing invoice"""
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Check if user has a pending invoice
        pending_invoice = self.db.get_pending_topup_invoice(user_id)
        
        if pending_invoice:
            # Show existing invoice
            self.show_existing_invoice(call, pending_invoice, lang_code)
        else:
            # Show amount selection
            self.show_amount_selection(call, lang_code)
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    def show_amount_selection(self, call, lang_code):
        """Show amount selection buttons"""
        balance = self.db.get_user_balance(call.from_user.id)
        currency_symbol = self.config.get('currency', {}).get('symbol', '$')
        
        text = f"""💰 <b>Top Up Balance</b>

💳 <b>Current Balance:</b> {currency_symbol}{balance:.2f}

<b>Select amount to add:</b>
Choose a preset amount or enter a custom amount.

💡 <i>Your balance can be used for future purchases!</i>"""
        
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        
        # Preset amounts
        amounts = [5, 10, 15, 20]
        amount_buttons = []
        for amount in amounts:
            amount_buttons.append(
                telebot.types.InlineKeyboardButton(
                    text=f"💵 {currency_symbol}{amount}",
                    callback_data=f"topup_amount_{amount}"
                )
            )
        
        # Add preset buttons in rows of 2
        for i in range(0, len(amount_buttons), 2):
            if i + 1 < len(amount_buttons):
                markup.row(amount_buttons[i], amount_buttons[i + 1])
            else:
                markup.row(amount_buttons[i])
        
        # Custom amount button
        markup.row(telebot.types.InlineKeyboardButton(
            text="✏️ Custom Amount",
            callback_data="topup_custom"
        ))
        
        # Back button
        markup.row(telebot.types.InlineKeyboardButton(
            text="🔙 Back to Menu",
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
            logger.error(f"Error showing amount selection: {e}")
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
    
    def show_existing_invoice(self, call, invoice, lang_code):
        """Show existing pending invoice"""
        currency_symbol = self.config.get('currency', {}).get('symbol', '$')
        
        text = f"""⏳ <b>Pending Top-Up Invoice</b>

You already have a pending top-up invoice:

💰 <b>Amount:</b> {currency_symbol}{invoice['amount']:.2f}
🪙 <b>Pay:</b> {invoice['pay_amount']} {invoice['pay_currency']}
📍 <b>Address:</b> <code>{invoice['address']}</code>
📅 <b>Created:</b> {invoice['created_at']}

⏰ <b>Please wait a bit, it will be confirmed within 120 seconds automatically!</b>

💡 <i>Choose an option below:</i>"""
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Copy address button
        markup.row(telebot.types.InlineKeyboardButton(
            text="📋 Copy Address",
            callback_data=f"topup_copy_{invoice['track_id']}"
        ))
        
        # Cancel button
        markup.row(telebot.types.InlineKeyboardButton(
            text="❌ Cancel Invoice",
            callback_data=f"topup_cancel_{invoice['id']}"
        ))
        
        # Back button
        markup.row(telebot.types.InlineKeyboardButton(
            text="🔙 Back to Menu",
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
            logger.error(f"Error showing existing invoice: {e}")
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
    
    def handle_amount_selection(self, call):
        """Handle preset amount selection"""
        amount = int(call.data.replace('topup_amount_', ''))
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        
        # Store amount and show currency selection
        self.db.set_user_state(user_id, 'topup_selecting_currency', {'amount': amount})
        self.show_currency_selection(call, amount, lang_code)
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    def handle_custom_amount(self, call):
        """Handle custom amount button - ask user to enter amount"""
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        currency_symbol = self.config.get('currency', {}).get('symbol', '$')
        
        text = f"""✏️ <b>Enter Custom Amount</b>

Please enter the amount you want to top up in {self.config.get('currency', {}).get('name', 'USD')}.

<b>Examples:</b>
• <code>25</code> for {currency_symbol}25
• <code>50</code> for {currency_symbol}50
• <code>100</code> for {currency_symbol}100

💬 <b>Enter amount (numbers only):</b>"""
        
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(telebot.types.InlineKeyboardButton(
            text="❌ Cancel",
            callback_data="menu_topup"
        ))
        
        # Set user state to expect custom amount
        self.db.set_user_state(user_id, 'topup_custom_amount', {'message_id': call.message.message_id})
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing custom amount input: {e}")
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    def handle_text_input(self, message):
        """Handle text input for custom amount"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        if not user_state or user_state['state'] != 'topup_custom_amount':
            return False
        
        text = message.text.strip()
        
        # Validate amount
        try:
            amount = float(text)
            if amount <= 0:
                self.bot.send_message(
                    message.chat.id,
                    "❌ Amount must be greater than 0. Please try again."
                )
                return True
            if amount > 10000:
                self.bot.send_message(
                    message.chat.id,
                    "❌ Maximum amount is $10,000. Please enter a smaller amount."
                )
                return True
        except ValueError:
            self.bot.send_message(
                message.chat.id,
                "❌ Invalid amount. Please enter a number (e.g., 25 or 50.50)."
            )
            return True
        
        # Clear state and show currency selection
        self.db.clear_user_state(user_id)
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        
        # Store amount in state for currency selection
        self.db.set_user_state(user_id, 'topup_selecting_currency', {'amount': amount})
        
        # Create a fake call object to reuse the currency selection function
        self.show_currency_selection_message(message, amount, lang_code)
        return True
    
    def show_currency_selection_message(self, message, amount, lang_code):
        """Show currency selection for message context"""
        currency_symbol = self.config.get('currency', {}).get('symbol', '$')
        
        text = f"""🪙 <b>Select Payment Currency</b>

💰 <b>Amount:</b> {currency_symbol}{amount:.2f}

<b>Choose cryptocurrency to pay with:</b>"""
        
        markup = self.get_currency_markup(amount)
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def show_currency_selection(self, call, amount, lang_code):
        """Show cryptocurrency selection for topup"""
        currency_symbol = self.config.get('currency', {}).get('symbol', '$')
        
        text = f"""🪙 <b>Select Payment Currency</b>

💰 <b>Amount:</b> {currency_symbol}{amount:.2f}

<b>Choose cryptocurrency to pay with:</b>"""
        
        markup = self.get_currency_markup(amount)
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing currency selection: {e}")
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
    
    def get_currency_markup(self, amount):
        """Generate currency selection markup"""
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        
        supported_coins = self.config.get('supported_cryptocurrencies', {})
        coin_buttons = []
        
        for coin_code, coin_info in supported_coins.items():
            emoji = coin_info.get('emoji', '🪙')
            name = coin_info.get('name', coin_code)
            coin_buttons.append(
                telebot.types.InlineKeyboardButton(
                    text=f"{emoji} {name}",
                    callback_data=f"topup_coin_{coin_code}_{amount}"
                )
            )
        
        # Add coins in rows of 2
        for i in range(0, len(coin_buttons), 2):
            if i + 1 < len(coin_buttons):
                markup.row(coin_buttons[i], coin_buttons[i + 1])
            else:
                markup.row(coin_buttons[i])
        
        # Back button
        markup.row(telebot.types.InlineKeyboardButton(
            text="🔙 Back",
            callback_data="menu_topup"
        ))
        
        return markup
    
    def handle_coin_selection(self, call):
        """Handle cryptocurrency selection and create invoice"""
        user_id = call.from_user.id
        
        # Parse callback data: topup_coin_{coin_code}_{amount}
        parts = call.data.split('_')
        coin_code = parts[2]
        amount = float(parts[3])
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        
        # Clear user state
        self.db.clear_user_state(user_id)
        
        # Show processing message
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="⏳ <b>Creating payment invoice...</b>\n\nPlease wait...",
                parse_mode='HTML'
            )
        except:
            pass
        
        # Create OxaPay invoice
        invoice_data = self.create_oxapay_invoice(amount, coin_code)
        
        if invoice_data:
            # Save invoice to database
            invoice_id = self.db.create_topup_invoice(
                user_id=user_id,
                amount=amount,
                pay_currency=coin_code,
                pay_amount=invoice_data['pay_amount'],
                track_id=invoice_data['track_id'],
                address=invoice_data['address']
            )
            
            if invoice_id:
                # Show payment details
                self.show_payment_details(call, invoice_data, amount, coin_code, lang_code)
            else:
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="❌ <b>Error saving invoice</b>\n\nPlease try again.",
                    parse_mode='HTML'
                )
        else:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="❌ <b>Error creating payment</b>\n\nPlease try again later.",
                parse_mode='HTML'
            )
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    def show_payment_details(self, call, invoice_data, amount, coin_code, lang_code):
        """Show payment details to user"""
        currency_symbol = self.config.get('currency', {}).get('symbol', '$')
        supported_coins = self.config.get('supported_cryptocurrencies', {})
        coin_info = supported_coins.get(coin_code, {})
        coin_name = coin_info.get('name', coin_code)
        coin_emoji = coin_info.get('emoji', '🪙')
        
        text = f"""✅ <b>Payment Invoice Created!</b>

💰 <b>Top-Up Amount:</b> {currency_symbol}{amount:.2f}

{coin_emoji} <b>Pay:</b> <code>{invoice_data['pay_amount']}</code> {coin_code}
📍 <b>Address:</b>
<code>{invoice_data['address']}</code>

⏰ <b>Please wait a bit, it will be confirmed within 120 seconds automatically!</b>

📋 <i>Tap the address to copy it</i>

🔄 <b>Status:</b> Waiting for payment...

💡 <i>After payment is confirmed, your balance will be updated automatically!</i>"""
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Copy address button
        markup.row(telebot.types.InlineKeyboardButton(
            text="📋 Copy Address",
            callback_data=f"topup_copy_{invoice_data['track_id']}"
        ))
        
        # Back to menu
        markup.row(telebot.types.InlineKeyboardButton(
            text="🔙 Back to Menu",
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
            logger.error(f"Error showing payment details: {e}")
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
    
    def handle_copy_address(self, call):
        """Handle copy address button"""
        track_id = call.data.replace('topup_copy_', '')
        invoice = self.db.get_topup_invoice_by_track_id(track_id)
        
        if invoice:
            self.bot.answer_callback_query(
                call.id,
                f"📋 Address copied!\n{invoice['address']}",
                show_alert=True
            )
        else:
            self.bot.answer_callback_query(call.id, "❌ Invoice not found")
    
    def handle_cancel_invoice(self, call):
        """Handle cancel invoice button"""
        user_id = call.from_user.id
        invoice_id = int(call.data.replace('topup_cancel_', ''))
        
        if self.db.cancel_topup_invoice(invoice_id, user_id):
            self.bot.answer_callback_query(call.id, "✅ Invoice cancelled!", show_alert=True)
            
            # Show topup menu again
            user = self.db.get_or_create_user(user_id)
            lang_code = user['language_code'] if user else 'en'
            self.show_amount_selection(call, lang_code)
        else:
            self.bot.answer_callback_query(call.id, "❌ Error cancelling invoice", show_alert=True)
    
    # ==================== OXAPAY API ====================
    
    def create_oxapay_invoice(self, amount, pay_currency):
        """Create OxaPay white-label payment for topup"""
        try:
            url = 'https://api.oxapay.com/v1/payment/white-label'
            
            headers = {
                'merchant_api_key': self.oxapay_api_key,
                'Content-Type': 'application/json'
            }
            
            # Get bot username
            bot_info = self.bot.get_me()
            bot_username = bot_info.username
            
            # Get currency code
            currency_code = self.config.get('currency', {}).get('code', 'USD')
            
            # Get network for the selected currency
            supported_coins = self.config.get('supported_cryptocurrencies', {})
            coin_info = supported_coins.get(pay_currency, {})
            networks = coin_info.get('networks', [])
            network = networks[0]['code'] if networks else pay_currency
            
            data = {
                "amount": amount,
                "currency": currency_code,
                "pay_currency": network,
                "lifetime": 180,  # 3 hours
                "fee_paid_by_payer": 1,
                "under_paid_coverage": 2.5,
                "callback_url": f"https://t.me/{bot_username}",
                "email": "",
                "order_id": f"topup_{int(time.time())}",
                "description": f"Balance Top-Up ${amount}"
            }
            
            logger.info(f"💳 Creating OxaPay topup invoice:")
            logger.info(f"   - Amount: {amount} {currency_code}")
            logger.info(f"   - Pay Currency: {network}")
            logger.info(f"   - Sandbox: {self.oxapay_sandbox}")
            
            response = requests.post(url, data=json.dumps(data), headers=headers, timeout=15)
            result = response.json()
            
            logger.info(f"📊 OxaPay response: {result}")
            
            if result.get('status') == 200:
                data = result['data']
                logger.info(f"✅ OxaPay topup invoice created: {data['track_id']}")
                return {
                    'track_id': data['track_id'],
                    'address': data['address'],
                    'pay_amount': data['pay_amount'],
                    'pay_currency': data['pay_currency'],
                    'network': data['network'],
                    'expired_at': data['expired_at']
                }
            else:
                logger.error(f"OxaPay error: {result}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating OxaPay topup invoice: {e}")
            return None
    
    def check_oxapay_payment(self, track_id):
        """Check OxaPay payment status"""
        try:
            url = 'https://api.oxapay.com/v1/payment'
            
            headers = {
                'merchant_api_key': self.oxapay_api_key,
                'Content-Type': 'application/json'
            }
            
            params = {
                'track_id': track_id,
                'size': 1
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            result = response.json()
            
            if result.get('status') == 200 and result.get('data', {}).get('list'):
                payment = result['data']['list'][0]
                return payment.get('status', 'pending').lower()
            
            return 'pending'
            
        except Exception as e:
            logger.error(f"Error checking OxaPay payment: {e}")
            return 'pending'
    
    # ==================== AUTO-CHECKER WORKER ====================
    
    def start_invoice_checker(self):
        """Start the auto-checker worker thread"""
        if self.checker_running:
            logger.warning("Invoice checker already running")
            return
        
        self.checker_running = True
        self.checker_thread = threading.Thread(target=self._invoice_checker_loop, daemon=True)
        self.checker_thread.start()
        logger.info("🔄 Topup invoice checker started - checking every 30 seconds")
    
    def stop_invoice_checker(self):
        """Stop the auto-checker worker thread"""
        self.checker_running = False
        logger.info("🛑 Topup invoice checker stopped")
    
    def _invoice_checker_loop(self):
        """Main loop for checking pending invoices"""
        while self.checker_running:
            try:
                self._check_pending_invoices()
            except Exception as e:
                logger.error(f"Error in invoice checker loop: {e}")
            
            # Sleep for check_interval seconds
            time.sleep(self.check_interval)
    
    def _check_pending_invoices(self):
        """Check all pending invoices and process paid ones"""
        pending_invoices = self.db.get_all_pending_topup_invoices()
        
        if not pending_invoices:
            return
        
        logger.info(f"🔍 Checking {len(pending_invoices)} pending topup invoices...")
        
        for invoice in pending_invoices:
            try:
                track_id = invoice['track_id']
                
                # SANDBOX MODE: Auto-complete invoices after 60 seconds
                if self.oxapay_sandbox:
                    from datetime import datetime, timedelta
                    created_at = datetime.strptime(invoice['created_at'], '%Y-%m-%d %H:%M:%S')
                    age_seconds = (datetime.now() - created_at).total_seconds()
                    
                    logger.info(f"   🧪 SANDBOX Invoice {track_id}: age={age_seconds:.0f}s")
                    
                    if age_seconds >= 60:
                        logger.info(f"   ✅ SANDBOX: Auto-completing invoice {track_id}")
                        status = 'paid'
                    else:
                        logger.info(f"   ⏳ SANDBOX: Waiting {60-age_seconds:.0f}s more...")
                        continue
                else:
                    # PRODUCTION MODE: Check actual payment status
                    status = self.check_oxapay_payment(track_id)
                    logger.debug(f"   Invoice {track_id}: {status}")
                
                if status == 'paid':
                    self._process_paid_invoice(invoice)
                elif status in ['expired', 'failed', 'refunded']:
                    # Mark as cancelled/failed
                    self.db.cancel_topup_invoice(invoice['id'], invoice['user_id'])
                    logger.info(f"Invoice {track_id} marked as {status}")
                    
            except Exception as e:
                logger.error(f"Error checking invoice {invoice['track_id']}: {e}")
    
    def _notify_admin_topup(self, user_id, amount, new_balance, track_id):
        """Notify admin(s) about a successful topup"""
        try:
            # Get user info
            user = self.db.get_user(user_id)
            username = user.get('username', 'N/A')
            full_name = user.get('full_name', 'Unknown')
            
            currency_symbol = self.config.get('currency', {}).get('symbol', '$')
            
            # Build admin notification
            admin_notification = f"""💰 <b>New Top-Up Completed!</b>

👤 <b>User:</b> {full_name}
🆔 <b>User ID:</b> <code>{user_id}</code>
📱 <b>Username:</b> @{username if username != 'N/A' else 'No username'}

💵 <b>Topped Up:</b> {currency_symbol}{amount:.2f}
💳 <b>New Balance:</b> {currency_symbol}{new_balance:.2f}

🔖 <b>Track ID:</b> <code>{track_id}</code>

✅ Payment confirmed and balance credited."""
            
            # Send to all admins
            for admin_id in self.config.get('admin_ids', []):
                try:
                    self.bot.send_message(
                        chat_id=admin_id,
                        text=admin_notification,
                        parse_mode='HTML'
                    )
                    logger.info(f"📨 Admin {admin_id} notified of topup from user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error building admin topup notification: {e}")
    
    def _process_paid_invoice(self, invoice):
        """Process a paid invoice - add balance and notify user"""
        user_id = invoice['user_id']
        amount = invoice['amount']
        track_id = invoice['track_id']
        
        # Mark invoice as paid
        if self.db.mark_topup_invoice_paid(track_id):
            # Add balance to user
            if self.db.add_user_balance(user_id, amount):
                new_balance = self.db.get_user_balance(user_id)
                currency_symbol = self.config.get('currency', {}).get('symbol', '$')
                
                # Notify user
                notification_text = f"""🎉 <b>Top-Up Successful!</b>

✅ Your payment has been confirmed!

💰 <b>Added:</b> {currency_symbol}{amount:.2f}
💳 <b>New Balance:</b> {currency_symbol}{new_balance:.2f}

<i>Thank you for your top-up! Your balance is ready to use.</i>"""
                
                try:
                    self.bot.send_message(
                        chat_id=user_id,
                        text=notification_text,
                        parse_mode='HTML'
                    )
                    logger.info(f"✅ Topup confirmed for user {user_id}: +${amount}, new balance: ${new_balance}")
                    
                    # Notify admin(s) about the topup
                    self._notify_admin_topup(user_id, amount, new_balance, track_id)
                    
                except Exception as e:
                    logger.error(f"Error notifying user {user_id}: {e}")
            else:
                logger.error(f"Failed to add balance for invoice {track_id}")
        else:
            logger.error(f"Failed to mark invoice {track_id} as paid")
