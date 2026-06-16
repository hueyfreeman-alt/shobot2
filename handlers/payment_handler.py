import telebot
import logging
import json
import sqlite3
import requests
import os
import time
from datetime import datetime
from cache_manager import save_json_safely

logger = logging.getLogger(__name__)

class PaymentHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        
        self.oxapay_api_key = config.get('oxapay_api_key', '')
        self.oxapay_sandbox = config.get('oxapay_sandbox', False)
        self.testing_mode = config.get('payment_testing_mode', False)
        
        # Log payment configuration on initialization
        logger.info(f"💳 Payment Handler Initialized:")
        logger.info(f"   - Testing Mode: {self.testing_mode}")
        logger.info(f"   - Sandbox Mode: {self.oxapay_sandbox}")
        logger.info(f"   - API Key Present: {'Yes' if self.oxapay_api_key else 'No'}")
    
    # DELIVERABLE PRODUCT HANDLERS - COMPLETELY SEPARATE
    def handle_deliverable_pay_now(self, call):
        """Handle Pay Now button for DELIVERABLE products - show coin selection"""
        logger.info(f"DELIVERABLE: handle_deliverable_pay_now called with callback data: {call.data}")
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract order ID
        order_id = int(call.data.replace('cart_deliverable_pay_', ''))
        
        # Get order details
        order = self.get_order_by_id(order_id)
        if not order:
            self.bot.answer_callback_query(call.id, "❌ Order not found")
            return
        
        # Check if order already has valid payment
        if self.has_valid_payment(order):
            # Show existing payment instead of creating new one
            self.show_existing_payment(call, order, 'deliverable')
        else:
            # Show coin selection
            self.show_coin_selection(call, order_id, 'deliverable')
    
    def show_coin_selection(self, call, order_id, order_type):
        """Show cryptocurrency selection menu with balance option"""
        user_id = call.from_user.id
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code']
        
        # Get order to check total cost
        order = self.get_order_by_id(order_id)
        order_total = order['total_cost'] if order else 0
        
        # Get user balance
        user_balance = self.db.get_user_balance(user_id)
        currency_symbol = self.config.get('currency', {}).get('symbol', '$')
        
        message_text = f"<b>{self.language.get_text('select_payment_method', lang_code)}</b>\n\n"
        message_text += f"💰 <b>Order Total:</b> {currency_symbol}{order_total:.2f}\n"
        message_text += f"💳 <b>Your Balance:</b> {currency_symbol}{user_balance:.2f}\n\n"
        message_text += f"{self.language.get_text('select_payment_method_message', lang_code)}"
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add "Pay with Balance" button if user has enough balance
        if user_balance >= order_total:
            markup.add(telebot.types.InlineKeyboardButton(
                text=f"💳 Pay with Balance ({currency_symbol}{user_balance:.2f})",
                callback_data=f'payment_balance_{order_type}_{order_id}'
            ))
            # Add separator text
            message_text += "\n\n<b>━━━ Or pay with crypto ━━━</b>"
        elif user_balance > 0:
            # Show balance info but not enough
            message_text += f"\n\n⚠️ <i>You need {currency_symbol}{(order_total - user_balance):.2f} more in balance to pay directly.</i>"
        
        # Get supported cryptocurrencies from config
        supported_coins = self.config.get('supported_cryptocurrencies', {})
        
        for coin_code, coin_info in supported_coins.items():
            coin_name = coin_info['name']
            coin_emoji = coin_info['emoji']
            
            markup.add(telebot.types.InlineKeyboardButton(
                text=f"{coin_emoji} {coin_name} ({coin_code})",
                callback_data=f'payment_coin_{order_type}_{order_id}_{coin_code}'
            ))
        
        # Add back button
        back_text = self.language.get_text('back_to_menu_button', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
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
        
        self.bot.answer_callback_query(call.id)
    
    def handle_balance_payment(self, call):
        """Handle payment with user balance"""
        logger.info(f"💳 Balance payment initiated: {call.data}")
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Parse callback data: payment_balance_{order_type}_{order_id}
        parts = call.data.split('_')
        order_type = parts[2]  # deliverable or digital
        order_id = int(parts[3])
        
        # Get order details
        order = self.get_order_by_id(order_id)
        if not order:
            self.bot.answer_callback_query(call.id, "❌ Order not found")
            return
        
        # SECURITY: Verify order belongs to user
        if order['user_id'] != user_id:
            logger.error(f"🚨 SECURITY: User {user_id} tried to pay for order {order_id} belonging to user {order['user_id']}")
            self.bot.answer_callback_query(call.id, "❌ Access denied")
            return
        
        # SECURITY: Verify order is not already completed
        if order.get('status') == 'completed':
            self.bot.answer_callback_query(call.id, "❌ Order already completed")
            return
        
        order_total = order['total_cost']
        user_balance = self.db.get_user_balance(user_id)
        
        # Verify sufficient balance
        if user_balance < order_total:
            currency_symbol = self.config.get('currency', {}).get('symbol', '$')
            self.bot.answer_callback_query(
                call.id, 
                f"❌ Insufficient balance!\nYou need {currency_symbol}{order_total:.2f} but have {currency_symbol}{user_balance:.2f}",
                show_alert=True
            )
            return
        
        # Deduct balance
        if not self.db.add_user_balance(user_id, -order_total):
            self.bot.answer_callback_query(call.id, "❌ Error processing payment. Please try again.")
            return
        
        # Mark order as paid with balance
        self.update_order_payment_info(order_id, f"balance_{int(time.time())}", "PAID_WITH_BALANCE")
        
        logger.info(f"✅ Balance payment successful: User {user_id} paid {order_total} for order {order_id}")
        
        # Process based on order type
        if order_type == 'deliverable':
            # Process deliverable order
            self.process_deliverable_order(order, lang_code, call)
        else:
            # Process digital order - deliver files immediately
            self.process_successful_payment(order, lang_code, call)
        
        # Show success notification with new balance
        new_balance = self.db.get_user_balance(user_id)
        currency_symbol = self.config.get('currency', {}).get('symbol', '$')
        self.bot.answer_callback_query(
            call.id,
            f"✅ Payment successful!\nDeducted: {currency_symbol}{order_total:.2f}\nNew balance: {currency_symbol}{new_balance:.2f}",
            show_alert=True
        )
    
    def handle_coin_selection(self, call):
        """Handle cryptocurrency selection and create white-label payment"""
        logger.info(f"handle_coin_selection called with callback data: {call.data}")
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Parse callback data: payment_coin_{order_type}_{order_id}_{coin_code}
        parts = call.data.split('_')
        order_type = parts[2]  # deliverable or digital
        order_id = int(parts[3])
        coin_code = parts[4]
        
        # Get order details
        order = self.get_order_by_id(order_id)
        if not order:
            self.bot.answer_callback_query(call.id, "❌ Order not found")
            return
        
        # Show processing message
        processing_text = self.language.get_text('payment_processing', lang_code)
        self.bot.answer_callback_query(call.id, processing_text)
        
        # Create white-label payment
        payment_result = self.create_oxapay_white_label(order, coin_code)
        if not payment_result:
            error_text = self.language.get_text('payment_failed', lang_code)
            self.bot.answer_callback_query(call.id, error_text, show_alert=True)
            return
        
        # Store payment info in database (using payment_url field to store white-label data)
        white_label_data = f"{payment_result['address']}-{coin_code}-{payment_result['network']}-{payment_result['pay_amount']}"
        self.update_order_payment_info(order_id, payment_result['track_id'], white_label_data)
        
        # Show payment details
        self.show_white_label_payment(call, order, payment_result, coin_code, order_type)
    
    def show_white_label_payment(self, call, order, payment_result, coin_code, order_type):
        """Display white-label payment information"""
        user_id = call.from_user.id
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code']
        
        # Get coin info
        supported_coins = self.config.get('supported_cryptocurrencies', {})
        coin_info = supported_coins.get(coin_code, {})
        coin_emoji = coin_info.get('emoji', '💰')
        coin_name = coin_info.get('name', coin_code)
        
        # Format amount properly (force full decimal display, no scientific notation)
        pay_amount = payment_result['pay_amount']
        if isinstance(pay_amount, float):
            # Use format with enough decimal places to avoid scientific notation
            formatted_amount = f"{pay_amount:.12f}".rstrip('0').rstrip('.')
            # Ensure we don't get empty string
            if not formatted_amount or formatted_amount == '':
                formatted_amount = str(pay_amount)
        else:
            formatted_amount = str(pay_amount)
        
        # Format payment message
        message_text = f"<b>{self.language.get_text('payment_details_title', lang_code)}</b>\n\n"
        message_text += f"{self.language.get_text('track_id_label', lang_code)} <code>{payment_result['track_id']}</code>\n\n"
        message_text += f"{self.language.get_text('currency_label', lang_code)} {coin_emoji} {coin_name}\n"
        message_text += f"{self.language.get_text('network_label', lang_code)} {payment_result['network']}\n"
        message_text += f"{self.language.get_text('amount_label', lang_code)} <code>{formatted_amount}</code> {coin_code}\n\n"
        message_text += f"{self.language.get_text('payment_address_label', lang_code)}\n<code>{payment_result['address']}</code>\n\n"
        message_text += f"{self.language.get_text('important_label', lang_code)}\n"
        message_text += f"{self.language.get_text('send_exactly_instruction', lang_code).format(amount=formatted_amount, currency=coin_code)}\n"
        message_text += f"{self.language.get_text('use_network_instruction', lang_code).format(network=payment_result['network'])}\n"
        message_text += f"{self.language.get_text('double_check_instruction', lang_code)}\n"
        message_text += f"{self.language.get_text('payment_expires_instruction', lang_code).format(minutes=payment_result.get('lifetime', 180))}\n\n"
        message_text += f"{self.language.get_text('qr_code_instruction', lang_code)}\n{payment_result.get('qr_code', '')}"
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add copy address button
        markup.add(telebot.types.InlineKeyboardButton(
            text=self.language.get_text('copy_address_button', lang_code),
            callback_data=f'copy_address_{payment_result["track_id"]}'
        ))
        
        # Add check payment button
        if order_type == 'deliverable':
            check_text = self.language.get_text('check_place_order_button', lang_code)
            check_callback = f'cart_deliverable_place_{order["id"]}'
        else:
            check_text = self.language.get_text('check_payment_button', lang_code)
            check_callback = f'cart_digital_check_{order["id"]}'
            
        markup.add(telebot.types.InlineKeyboardButton(
            text=check_text,
            callback_data=check_callback
        ))
        
        # Add back to menu button
        back_text = self.language.get_text('back_to_menu_button', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
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
    
    def handle_copy_address(self, call):
        """Handle copy address button"""
        # Extract track_id from callback data
        track_id = call.data.replace('copy_address_', '')
        
        # Get order by track_id to find the address
        order = self.get_order_by_track_id(track_id)
        if order and order.get('payment_url'):
            # Extract address from stored white-label data
            parts = order['payment_url'].split('-')
            if len(parts) >= 4:
                address = parts[0]
                self.bot.answer_callback_query(
                    call.id, 
                    self.language.get_text('address_copied_message', self.db.get_user(call.from_user.id)['language_code']).format(address=address), 
                    show_alert=True
                )
            else:
                user = self.db.get_user(call.from_user.id)
                lang_code = user['language_code'] if user else 'en'
                self.bot.answer_callback_query(call.id, self.language.get_text('address_not_found', lang_code))
        else:
            user = self.db.get_user(call.from_user.id)
            lang_code = user['language_code'] if user else 'en'
            self.bot.answer_callback_query(call.id, self.language.get_text('address_not_found', lang_code))
    
    def has_valid_payment(self, order):
        """Check if order has valid payment that hasn't expired"""
        if not order.get('payment_track_id') or not order.get('payment_url'):
            return False
        
        # Check if payment hasn't expired (order deadline)
        current_timestamp = int(time.time())
        if order.get('deadline', 0) <= current_timestamp:
            return False
        
        return True
    
    def show_existing_payment(self, call, order, order_type):
        """Show existing payment details instead of creating new one"""
        user_id = call.from_user.id
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code']
        
        # Parse stored white-label data: address-coin-network-amount
        payment_data = order.get('payment_url', '').split('-')
        if len(payment_data) >= 4:
            address = payment_data[0]
            coin_code = payment_data[1]
            network = payment_data[2]
            pay_amount = payment_data[3]
            
            # Get coin info
            supported_coins = self.config.get('supported_cryptocurrencies', {})
            coin_info = supported_coins.get(coin_code, {})
            coin_emoji = coin_info.get('emoji', '💰')
            coin_name = coin_info.get('name', coin_code)
            
            # Format amount properly (force full decimal display, no scientific notation)
            try:
                pay_amount_float = float(pay_amount)
                # Use format with enough decimal places to avoid scientific notation
                formatted_amount = f"{pay_amount_float:.12f}".rstrip('0').rstrip('.')
                # Ensure we don't get empty string
                if not formatted_amount or formatted_amount == '':
                    formatted_amount = str(pay_amount_float)
            except:
                formatted_amount = str(pay_amount)
            
            # Calculate remaining time
            current_timestamp = int(time.time())
            remaining_minutes = max(0, (order.get('deadline', 0) - current_timestamp) // 60)
            
            # Format payment message
            message_text = f"<b>{self.language.get_text('existing_payment_details_title', lang_code)}</b>\n\n"
            message_text += f"{self.language.get_text('track_id_label', lang_code)} <code>{order.get('payment_track_id', 'N/A')}</code>\n\n"
            message_text += f"{self.language.get_text('currency_label', lang_code)} {coin_emoji} {coin_name}\n"
            message_text += f"{self.language.get_text('network_label', lang_code)} {network}\n"
            message_text += f"{self.language.get_text('amount_label', lang_code)} <code>{formatted_amount}</code> {coin_code}\n\n"
            message_text += f"{self.language.get_text('payment_address_label', lang_code)}\n<code>{address}</code>\n\n"
            message_text += f"{self.language.get_text('important_label', lang_code)}\n"
            message_text += f"{self.language.get_text('send_exactly_instruction', lang_code).format(amount=formatted_amount, currency=coin_code)}\n"
            message_text += f"{self.language.get_text('use_network_instruction', lang_code).format(network=network)}\n"
            message_text += f"{self.language.get_text('double_check_instruction', lang_code)}\n"
            message_text += f"{self.language.get_text('payment_expires_instruction', lang_code).format(minutes=remaining_minutes)}\n\n"
            message_text += f"{self.language.get_text('existing_payment_note', lang_code)}"
            
        else:
            # Fallback message if data parsing fails
            message_text = f"<b>{self.language.get_text('payment_in_progress_title', lang_code)}</b>\n\n"
            message_text += f"{self.language.get_text('track_id_label', lang_code)} <code>{order.get('payment_track_id', 'N/A')}</code>\n\n"
            message_text += f"{self.language.get_text('payment_already_in_progress', lang_code)}"
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add copy address button if we have the address
        if len(payment_data) >= 4:
            markup.add(telebot.types.InlineKeyboardButton(
                text=self.language.get_text('copy_address_button', lang_code),
                callback_data=f'copy_address_{order.get("payment_track_id", "")}'
            ))
        
        # Add check payment button with network delay message
        if order_type == 'deliverable':
            check_text = self.language.get_text('check_place_order_button', lang_code)
            check_callback = f'cart_deliverable_place_{order["id"]}'
        else:
            check_text = self.language.get_text('check_payment_button', lang_code)
            check_callback = f'cart_digital_check_{order["id"]}'
            
        markup.add(telebot.types.InlineKeyboardButton(
            text=f"🔍 {check_text}",
            callback_data=check_callback
        ))
        
        # Add back to menu button
        back_text = self.language.get_text('back_to_menu_button', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
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
        
        self.bot.answer_callback_query(call.id)
    
    def handle_deliverable_place_order(self, call):
        """Handle Check & Place Order for DELIVERABLE products ONLY"""
        logger.info(f"DELIVERABLE: handle_deliverable_place_order called with callback data: {call.data}")
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract order ID - FIXED: use correct prefix for place order
        order_id = int(call.data.replace('cart_deliverable_place_', ''))
        
        # Get order details
        order = self.get_order_by_id(order_id)
        if not order:
            self.bot.answer_callback_query(call.id, "❌ Order not found")
            return
        
        # Check if payment exists and is paid
        if self.testing_mode:
            payment_status = 'paid'  # Always paid in testing
        else:
            if not order.get('payment_track_id'):
                # No payment yet - redirect to payment by creating a modified call object
                # Create a new call-like object with the correct callback data for payment
                class PaymentCall:
                    def __init__(self, original_call, order_id):
                        self.from_user = original_call.from_user
                        self.message = original_call.message
                        self.id = original_call.id
                        self.data = f'cart_deliverable_pay_{order_id}'
                
                payment_call = PaymentCall(call, order_id)
                self.handle_deliverable_pay_now(payment_call)
                return
            payment_status = self.check_oxapay_payment(order['payment_track_id'])
        
        if payment_status == 'paid':
            # Mark order as deliverable and notify admin
            self.process_deliverable_order(order, lang_code, call)
        elif payment_status == 'pending':
            # Payment pending with network delay message (shortened for callback)
            pending_message = f"⏳ Payment verification in progress...\n\n🌐 Networks can take time to confirm.\nIf paid, please wait and try again."
            self.bot.answer_callback_query(call.id, pending_message, show_alert=True)
        else:
            # Payment failed or not found (shortened for callback)
            failed_message = f"❌ Payment not detected yet.\n\nEnsure you sent exact amount to correct address.\n🕐 Wait 5-15 minutes for confirmation."
            self.bot.answer_callback_query(call.id, failed_message, show_alert=True)
    
    # DIGITAL PRODUCT HANDLERS - COMPLETELY SEPARATE
    def handle_digital_pay_now(self, call):
        """Handle Pay Now button for DIGITAL products - show coin selection"""
        logger.info(f"DIGITAL: handle_digital_pay_now called with callback data: {call.data}")
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract order ID
        order_id = int(call.data.replace('cart_digital_pay_', ''))
        
        # Get order details
        order = self.get_order_by_id(order_id)
        if not order:
            self.bot.answer_callback_query(call.id, "❌ Order not found")
            return
        
        # Check if order already has valid payment
        if self.has_valid_payment(order):
            # Show existing payment instead of creating new one
            self.show_existing_payment(call, order, 'digital')
        else:
            # Show coin selection
            self.show_coin_selection(call, order_id, 'digital')
    
    def handle_digital_check_payment(self, call):
        """Handle Check Payment button for DIGITAL products - verify payment status with STRICT security"""
        logger.info(f"🔒 SECURITY: DIGITAL payment check initiated for callback: {call.data}")
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract order ID with validation
        try:
            order_id = int(call.data.replace('cart_digital_check_', ''))
            logger.info(f"🔒 SECURITY: Checking payment for order ID: {order_id}")
        except ValueError:
            logger.error(f"🚨 SECURITY: Invalid order ID in callback data: {call.data}")
            self.bot.answer_callback_query(call.id, "❌ Invalid order ID")
            return
        
        # Get order details with ownership verification
        order = self.get_order_by_id(order_id)
        if not order:
            logger.error(f"🚨 SECURITY: Order {order_id} not found")
            self.bot.answer_callback_query(call.id, "❌ Order not found")
            return
        
        # CRITICAL: Verify order belongs to the user making the request
        if order['user_id'] != user_id:
            logger.error(f"🚨 SECURITY BREACH: User {user_id} tried to check payment for order {order_id} belonging to user {order['user_id']}")
            self.bot.answer_callback_query(call.id, "❌ Access denied")
            return
        
        # CRITICAL: Verify order hasn't already been processed
        if order.get('status') == 'completed':
            logger.warning(f"🚨 SECURITY: User {user_id} tried to check already completed order {order_id}")
            self.bot.answer_callback_query(call.id, "❌ Order already completed")
            return
        
        # CRITICAL: Verify payment track ID exists
        track_id = order.get('payment_track_id')
        if not track_id:
            logger.error(f"🚨 SECURITY: Order {order_id} has no payment_track_id")
            self.bot.answer_callback_query(call.id, "❌ Payment not initialized")
            return
        
        # MULTI-LAYER PAYMENT VERIFICATION
        logger.info(f"🔒 SECURITY: Starting STRICT payment verification for order {order_id}, track_id: {track_id}")
        
        # Layer 1: Check payment status
        if self.testing_mode:
            logger.warning(f"⚠️ TESTING MODE: Allowing payment for order {order_id}")
            payment_status = 'paid'
        else:
            # Real OxaPay check with retry logic
            payment_status = self.check_oxapay_payment(track_id)
            logger.info(f"🔒 SECURITY: Payment verification result for order {order_id}: {payment_status}")
        
        # Layer 2: Double-check payment status
        if payment_status == 'paid':
            # FINAL SECURITY CHECK: Verify order is still valid and not processed
            fresh_order = self.get_order_by_id(order_id)
            if not fresh_order or fresh_order.get('status') == 'completed':
                logger.error(f"🚨 SECURITY: Order {order_id} was completed between checks - preventing duplicate delivery")
                self.bot.answer_callback_query(call.id, "❌ Order already processed")
                return
            
            # FINAL VERIFICATION: Ensure this is still the same user
            if fresh_order['user_id'] != user_id:
                logger.error(f"🚨 SECURITY BREACH: Order ownership changed during verification for order {order_id}")
                self.bot.answer_callback_query(call.id, "❌ Security error")
                return
            
            logger.info(f"✅ SECURITY: All checks passed for order {order_id} - processing payment")
            # Payment successful - process digital order
            self.process_successful_payment(fresh_order, lang_code, call)
            
        elif payment_status == 'pending':
            # Payment pending with network delay message (shortened for callback)
            pending_message = f"⏳ Payment verification in progress...\n\n🌐 Networks can take time to confirm.\nIf paid, please wait and try again."
            logger.info(f"⏳ PENDING: Payment still pending for order {order_id}")
            self.bot.answer_callback_query(call.id, pending_message, show_alert=True)
        else:
            # Payment failed or not found (shortened for callback)
            failed_message = f"❌ Payment not detected yet.\n\nEnsure you sent exact amount to correct address.\n🕐 Wait 5-15 minutes for confirmation."
            logger.info(f"❌ FAILED: Payment not confirmed for order {order_id}")
            self.bot.answer_callback_query(call.id, failed_message, show_alert=True)
    
    def handle_check_payment(self, call):
        """Handle Check Payment button - verify payment status with STRICT security"""
        logger.info(f"🔒 SECURITY: Payment check initiated for callback: {call.data}")
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract order ID with validation
        try:
            order_id = int(call.data.replace('cart_check_', ''))
            logger.info(f"🔒 SECURITY: Checking payment for order ID: {order_id}")
        except ValueError:
            logger.error(f"🚨 SECURITY: Invalid order ID in callback data: {call.data}")
            self.bot.answer_callback_query(call.id, "❌ Invalid order ID")
            return
        
        # Get order details with ownership verification
        order = self.get_order_by_id(order_id)
        if not order:
            logger.error(f"🚨 SECURITY: Order {order_id} not found")
            self.bot.answer_callback_query(call.id, "❌ Order not found")
            return
        
        # CRITICAL: Verify order belongs to the user making the request
        if order['user_id'] != user_id:
            logger.error(f"🚨 SECURITY BREACH: User {user_id} tried to check payment for order {order_id} belonging to user {order['user_id']}")
            self.bot.answer_callback_query(call.id, "❌ Access denied")
            return
        
        # CRITICAL: Verify order hasn't already been processed
        if order.get('status') == 'completed':
            logger.warning(f"🚨 SECURITY: User {user_id} tried to check already completed order {order_id}")
            self.bot.answer_callback_query(call.id, "❌ Order already completed")
            return
        
        # CRITICAL: Verify payment track ID exists
        track_id = order.get('payment_track_id')
        if not track_id:
            logger.error(f"🚨 SECURITY: Order {order_id} has no payment_track_id")
            self.bot.answer_callback_query(call.id, "❌ Payment not initialized")
            return
        
        # MULTI-LAYER PAYMENT VERIFICATION
        logger.info(f"🔒 SECURITY: Starting STRICT payment verification for order {order_id}, track_id: {track_id}")
        
        # Layer 1: Check payment status
        if self.testing_mode:
            logger.warning(f"⚠️ TESTING MODE: Allowing payment for order {order_id}")
            payment_status = 'paid'
        else:
            # Real OxaPay check
            payment_status = self.check_oxapay_payment(track_id)
            logger.info(f"🔒 SECURITY: Payment verification result for order {order_id}: {payment_status}")
        
        # Layer 2: Double-check payment status
        if payment_status == 'paid':
            # FINAL SECURITY CHECK: Verify order is still valid and not processed
            fresh_order = self.get_order_by_id(order_id)
            if not fresh_order or fresh_order.get('status') == 'completed':
                logger.error(f"🚨 SECURITY: Order {order_id} was completed between checks - preventing duplicate delivery")
                self.bot.answer_callback_query(call.id, "❌ Order already processed")
                return
            
            # FINAL VERIFICATION: Ensure this is still the same user
            if fresh_order['user_id'] != user_id:
                logger.error(f"🚨 SECURITY BREACH: Order ownership changed during verification for order {order_id}")
                self.bot.answer_callback_query(call.id, "❌ Security error")
                return
            
            logger.info(f"✅ SECURITY: All checks passed for order {order_id} - processing payment")
            # Payment successful - process order
            self.process_successful_payment(fresh_order, lang_code, call)
            
        elif payment_status == 'pending':
            # Payment pending
            pending_text = self.language.get_text('payment_pending', lang_code)
            logger.info(f"⏳ PENDING: Payment still pending for order {order_id}")
            self.bot.answer_callback_query(call.id, pending_text, show_alert=True)
        else:
            # Payment failed or not found
            failed_text = self.language.get_text('payment_failed', lang_code)
            logger.info(f"❌ FAILED: Payment not confirmed for order {order_id}")
            self.bot.answer_callback_query(call.id, failed_text, show_alert=True)
    
    def handle_check_and_place_order(self, call):
        """Handle Check & Place Order for deliverable products with STRICT security"""
        logger.info(f"🔒 SECURITY: Check and place order initiated for callback: {call.data}")
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract order ID with validation
        try:
            order_id = int(call.data.replace('cart_check_place_', ''))
            logger.info(f"🔒 SECURITY: Checking and placing order ID: {order_id}")
        except ValueError:
            logger.error(f"🚨 SECURITY: Invalid order ID in callback data: {call.data}")
            self.bot.answer_callback_query(call.id, "❌ Invalid order ID")
            return
        
        # Get order details with ownership verification
        order = self.get_order_by_id(order_id)
        if not order:
            logger.error(f"🚨 SECURITY: Order {order_id} not found")
            self.bot.answer_callback_query(call.id, "❌ Order not found")
            return
        
        # CRITICAL: Verify order belongs to the user making the request
        if order['user_id'] != user_id:
            logger.error(f"🚨 SECURITY BREACH: User {user_id} tried to place order {order_id} belonging to user {order['user_id']}")
            self.bot.answer_callback_query(call.id, "❌ Access denied")
            return
        
        # CRITICAL: Verify order hasn't already been processed
        if order.get('status') == 'completed':
            logger.warning(f"🚨 SECURITY: User {user_id} tried to place already completed order {order_id}")
            self.bot.answer_callback_query(call.id, "❌ Order already completed")
            return
        
        # Check if payment exists and is paid with strict verification
        if self.testing_mode:
            logger.warning(f"⚠️ TESTING MODE: Allowing order placement for order {order_id}")
            payment_status = 'paid'  # Always paid in testing
        else:
            track_id = order.get('payment_track_id')
            if not track_id:
                logger.info(f"📋 No payment track ID for order {order_id} - redirecting to payment")
                # No payment yet - redirect to payment
                self.handle_pay_now(call)
                return
            
            logger.info(f"🔒 SECURITY: Starting payment verification for deliverable order {order_id}, track_id: {track_id}")
            payment_status = self.check_oxapay_payment(track_id)
            logger.info(f"🔒 SECURITY: Payment verification result for order {order_id}: {payment_status}")
        
        if payment_status == 'paid':
            # FINAL SECURITY CHECK: Verify order is still valid and not processed
            fresh_order = self.get_order_by_id(order_id)
            if not fresh_order or fresh_order.get('status') == 'completed':
                logger.error(f"🚨 SECURITY: Order {order_id} was completed between checks - preventing duplicate processing")
                self.bot.answer_callback_query(call.id, "❌ Order already processed")
                return
            
            # FINAL VERIFICATION: Ensure this is still the same user
            if fresh_order['user_id'] != user_id:
                logger.error(f"🚨 SECURITY BREACH: Order ownership changed during verification for order {order_id}")
                self.bot.answer_callback_query(call.id, "❌ Security error")
                return
            
            logger.info(f"✅ SECURITY: All checks passed for deliverable order {order_id} - processing")
            # Mark order as deliverable and notify admin
            self.process_deliverable_order(fresh_order, lang_code, call)
            
        elif payment_status == 'pending':
            pending_text = self.language.get_text('payment_pending', lang_code)
            logger.info(f"⏳ PENDING: Payment still pending for deliverable order {order_id}")
            self.bot.answer_callback_query(call.id, pending_text, show_alert=True)
        else:
            failed_text = self.language.get_text('payment_failed', lang_code)
            logger.info(f"❌ FAILED: Payment not confirmed for deliverable order {order_id}")
            self.bot.answer_callback_query(call.id, failed_text, show_alert=True)
    
    def create_oxapay_white_label(self, order, pay_currency):
        """Create OxaPay white-label payment"""
        try:
            url = 'https://api.oxapay.com/v1/payment/white-label'
            
            headers = {
                'merchant_api_key': self.oxapay_api_key,
                'Content-Type': 'application/json'
            }
            
            # Get bot username dynamically
            bot_info = self.bot.get_me()
            bot_username = bot_info.username
            
            # Get currency conversion
            currency_code = self.config.get('currency', {}).get('code', 'USD')
            amount = order['total_cost']
            
            # Get network for the selected currency
            supported_coins = self.config.get('supported_cryptocurrencies', {})
            coin_info = supported_coins.get(pay_currency, {})
            networks = coin_info.get('networks', [])
            network = networks[0]['code'] if networks else pay_currency
            
            data = {
                "amount": amount,
                "currency": currency_code,
                "pay_currency": network,  # Use network code directly for proper conversion
                "lifetime": 180,  # 180 minutes
                "fee_paid_by_payer": 1,
                "under_paid_coverage": 2.5,
                "callback_url": f"https://t.me/{bot_username}",
                "email": "",
                "order_id": str(order['id']),
                "description": f"Order #{order['id']} - {len(order['products'])} items"
            }
            
            # Log payment request details
            logger.info(f"💳 Creating OxaPay white-label payment:")
            logger.info(f"   - Order ID: {order['id']}")
            logger.info(f"   - Amount: {amount} {currency_code}")
            logger.info(f"   - Pay Currency: {network}")
            logger.info(f"   - Testing Mode: {self.testing_mode}")
            logger.info(f"   - API URL: {url}")
            
            response = requests.post(url, data=json.dumps(data), headers=headers, timeout=15)
            
            # Check if response is valid JSON
            try:
                result = response.json()
            except json.JSONDecodeError as json_error:
                logger.error(f"Invalid JSON response from OxaPay: {json_error}")
                logger.error(f"Response status: {response.status_code}")
                logger.error(f"Response text: {response.text[:500]}")
                
                # Fall back to testing mode if API fails
                if self.testing_mode:
                    logger.info("Falling back to testing mode due to API error")
                    return {
                        'track_id': f'test_track_{order["id"]}',
                        'address': f'test_address_{order["id"]}_{pay_currency}',
                        'pay_amount': amount * 0.001,  # Mock conversion rate
                        'pay_currency': pay_currency,
                        'network': f'{pay_currency} Network',
                        'qr_code': f'https://api.qrserver.com/v1/create-qr-code/?data=test&size=150x150',
                        'expired_at': int(time.time()) + 3600,
                        'lifetime': 180
                    }
                return None
            
            if result.get('status') == 200:
                data = result['data']
                logger.info(f"✅ OxaPay payment created successfully:")
                logger.info(f"   - Track ID: {data['track_id']}")
                logger.info(f"   - Pay Amount: {data['pay_amount']} {data['pay_currency']}")
                logger.info(f"   - Network: {data['network']}")
                logger.info(f"   - Address: {data['address'][:20]}...")
                return {
                    'track_id': data['track_id'],
                    'address': data['address'],
                    'pay_amount': data['pay_amount'],
                    'pay_currency': data['pay_currency'],
                    'network': data['network'],
                    'qr_code': data.get('qr_code', ''),
                    'expired_at': data['expired_at'],
                    'lifetime': data.get('lifetime', 180)
                }
            else:
                logger.error(f"OxaPay error: {result}")
                
                # Fall back to testing mode if API fails
                if self.testing_mode:
                    logger.info("Falling back to testing mode due to API error")
                    return {
                        'track_id': f'test_track_{order["id"]}',
                        'address': f'test_address_{order["id"]}_{pay_currency}',
                        'pay_amount': amount * 0.001,  # Mock conversion rate
                        'pay_currency': pay_currency,
                        'network': f'{pay_currency} Network',
                        'qr_code': f'https://api.qrserver.com/v1/create-qr-code/?data=test&size=150x150',
                        'expired_at': int(time.time()) + 3600,
                        'lifetime': 180
                    }
                return None
                
        except Exception as e:
            logger.error(f"Error creating OxaPay white-label payment: {e}")
            
            # Fall back to testing mode if API fails
            if self.testing_mode:
                logger.info("Falling back to testing mode due to exception")
                return {
                    'track_id': f'test_track_{order["id"]}',
                    'address': f'test_address_{order["id"]}_{pay_currency}',
                    'pay_amount': amount * 0.001,  # Mock conversion rate
                    'pay_currency': pay_currency,
                    'network': f'{pay_currency} Network',
                    'qr_code': f'https://api.qrserver.com/v1/create-qr-code/?data=test&size=150x150',
                    'expired_at': int(time.time()) + 3600,
                    'lifetime': 180
                }
            return None
    
    def check_oxapay_payment(self, track_id):
        """Check OxaPay payment status"""
        logger.info(f"🔍 Checking OxaPay payment for track_id: {track_id}")
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
            
            logger.debug(f"🌐 Making OxaPay API request to: {url}")
            response = requests.get(url, params=params, headers=headers, timeout=10)
            result = response.json()
            
            logger.info(f"📊 OxaPay API response status: {result.get('status')}")
            logger.debug(f"📊 OxaPay API full response: {result}")
            
            if result.get('status') == 200 and result.get('data', {}).get('list'):
                payment = result['data']['list'][0]
                payment_status = payment.get('status', 'pending').lower()
                logger.info(f"💰 Payment status for track_id {track_id}: {payment_status}")
                return payment_status
            else:
                logger.warning(f"⚠️ No payment data found for track_id {track_id}, returning pending")
                return 'pending'
                
        except Exception as e:
            logger.error(f"❌ Error checking OxaPay payment for track_id {track_id}: {e}")
            return 'pending'
    
    def process_successful_payment(self, order, lang_code, call):
        """Process successful payment for digital products with STRICT security"""
        order_id = order['id']
        logger.info(f"🔒 SECURITY: Starting order processing for order {order_id}")
        
        # CRITICAL: Immediately mark order as completed to prevent race conditions
        try:
            self.mark_order_as_completed(order_id)
            logger.info(f"✅ SECURITY: Order {order_id} marked as completed")
        except Exception as e:
            logger.error(f"🚨 SECURITY: Failed to mark order {order_id} as completed: {e}")
            return
        
        # Move order to selling history
        self.move_order_to_history(order)
        logger.info(f"📊 Order {order_id} moved to history")
        
        # Send digital products to user
        self.deliver_digital_products(order, lang_code, call.message.chat.id)
        logger.info(f"📦 Digital products delivered for order {order_id}")
        
        # Clear stock reservations
        self.clear_stock_reservations(order['id'])
        logger.info(f"🔄 Stock reservations cleared for order {order_id}")
        
        # Delete order from orders table
        self.delete_order(order['id'])
        logger.info(f"🗑️ Order {order_id} deleted from active orders")
        
        # Show success message with review option
        success_text = self.language.get_text('order_delivered_message', lang_code)
        review_prompt = self.language.get_text('please_review_product', lang_code)
        
        message_text = f"{success_text}\n\n{review_prompt}"
        
        markup = telebot.types.InlineKeyboardMarkup()
        review_text = self.language.get_text('review_button', lang_code)
        back_text = self.language.get_text('back_to_menu_button', lang_code)
        
        markup.add(telebot.types.InlineKeyboardButton(
            text=review_text,
            callback_data=f'review_order_{order["id"]}'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
        # Delete the previous message
        try:
            self.bot.delete_message(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
        except:
            pass  # Ignore if message already deleted
        
        # Send new message
        self.bot.send_message(
            chat_id=call.message.chat.id,
            text=message_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def process_deliverable_order(self, order, lang_code, call):
        """Process deliverable order - move to delivery_queue and notify admin"""
        try:
            logger.info(f"DELIVERABLE: Starting process_deliverable_order for order {order['id']}")
            
            # Move order to delivery_queue table with awaiting_delivery status
            logger.info(f"DELIVERABLE: Moving order to delivery_queue")
            self.move_order_to_delivery_queue(order)
            
            # Clear stock reservations
            logger.info(f"DELIVERABLE: Clearing stock reservations")
            self.clear_stock_reservations(order['id'])
            
            # Delete order from orders table
            logger.info(f"DELIVERABLE: Deleting order from orders table")
            self.delete_order(order['id'])
            
            # Send detailed order to admin
            logger.info(f"DELIVERABLE: Sending admin notification")
            self.notify_admin_deliverable_order(order)
            
        except Exception as e:
            logger.error(f"DELIVERABLE: Error in process_deliverable_order: {e}")
            logger.error(f"DELIVERABLE: Error type: {type(e)}")
            import traceback
            logger.error(f"DELIVERABLE: Traceback: {traceback.format_exc()}")
            raise e
        
        logger.info(f"DELIVERABLE: Showing confirmation message to user")
        # Show proper message to user for deliverable orders
        success_text = self.language.get_text('order_placed_for_delivery', lang_code)
        
        message_text = success_text
        
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_menu_button', lang_code)
        
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
        # Delete the previous message and send new one
        try:
            self.bot.delete_message(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
        except:
            pass  # Ignore if message already deleted
        
        # Send new message
        self.bot.send_message(
            chat_id=call.message.chat.id,
            text=message_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def deliver_digital_products(self, order, lang_code, chat_id):
        """Deliver digital products to user"""
        # Import file serving handler
        from handlers.file_serving_handler import FileServingHandler
        file_server = FileServingHandler(self.bot, self.db, self.language, self.config)
        
        # Load products data
        products_data = self.load_products()
        
        for item in order['products']:
            product_id = item['product_id']
            quantity = item['quantity']
            product_type = item.get('type', 'delivered')
            
            # Find product in products data
            product = None
            for p in products_data.get('products', []):
                if p['id'] == product_id:
                    product = p
                    break
            
            if not product:
                continue
            
            if product_type == 'downloadable':
                # Send ONLY the number of files equal to quantity (first N files)
                if product.get('files'):
                    files_to_send = product['files'][:max(0, quantity)]
                    if files_to_send:
                        file_server.send_product_files(chat_id, files_to_send, product['name'])
            
            elif product_type == 'line_file':
                # Create and send text file with lines from separate JSON file
                self.send_line_file(chat_id, product, quantity)
    
    def send_line_file(self, chat_id, product, quantity):
        """Create and send text file with line content from separate JSON file"""
        try:
            # Get the actual file path from product files array
            files = product.get('files', [])
            if not files:
                logger.error(f"No files found for line-based product {product['name']}")
                return
            
            # Get the first file (line-based products should only have one JSON file)
            file_data = files[0]
            json_file_path = file_data.get('local_path') or file_data.get('relative_path')
            
            if not json_file_path or not os.path.exists(json_file_path):
                logger.error(f"Product JSON file not found: {json_file_path}")
                return
            
            with open(json_file_path, 'r', encoding='utf-8') as f:
                line_data = json.load(f)
            
            # Get available products (lines) and take the requested quantity
            available_products = [p for p in line_data.get('products', []) if p.get('status') == 'available']
            lines_to_deliver = available_products[:quantity]
            
            if lines_to_deliver:
                # Create text file content with the actual content values
                content_lines = [line['content'] for line in lines_to_deliver]
                content = "\n".join(content_lines)
                
                # Create temporary file
                filename = f"{product['name']}_lines.txt"
                filepath = f"temp_{filename}"
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Send file
                with open(filepath, 'rb') as f:
                    self.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        caption=f"📄 {product['name']} - {quantity} lines delivered"
                    )
                
                # Mark delivered lines as sold
                for line in lines_to_deliver:
                    for i, p in enumerate(line_data['products']):
                        if p['id'] == line['id']:
                            line_data['products'][i]['status'] = 'sold'
                
                # Save updated JSON file
                with open(json_file_path, 'w', encoding='utf-8') as f:
                    json.dump(line_data, f, indent=2, ensure_ascii=False)
                
                # Clean up temp file
                os.remove(filepath)
                
                logger.info(f"Delivered {quantity} lines for product {product['name']}")
            else:
                logger.warning(f"No available lines to deliver for product {product['name']}")
                
        except Exception as e:
            logger.error(f"Error sending line file: {e}")

    
    def notify_admin_deliverable_order(self, order):
        """Send detailed order information to admin for delivery"""
        admin_ids = self.config.get('admin_ids', [])
        
        if not admin_ids:
            logger.warning("No admin IDs found in config!")
            return
        
        # Build comprehensive order summary for admin
        message = f"🚚 <b>NEW DELIVERY ORDER - IMMEDIATE ACTION REQUIRED</b>\n"
        message += f"{'='*50}\n\n"
        
        # Customer Information
        message += f"👤 <b>CUSTOMER DETAILS:</b>\n"
        message += f"• Name: {order.get('username', 'N/A')}\n"
        message += f"• User ID: <code>{order['user_id']}</code>\n"
        message += f"• Order ID: <code>{order['id']}</code>\n\n"
        
        # Order Details
        message += f"💰 <b>ORDER SUMMARY:</b>\n"
        message += f"• Total Amount: <b>{self.format_price(order['total_cost'])}</b>\n"
        # Handle created_at timestamp conversion
        try:
            if isinstance(order['created_at'], str):
                # If it's already a formatted date string, use it directly
                if '-' in order['created_at'] and ':' in order['created_at']:
                    order_time = order['created_at']
                else:
                    # Try to convert string timestamp to int then format
                    created_at = int(order['created_at'])
                    order_time = datetime.fromtimestamp(created_at).strftime('%Y-%m-%d %H:%M:%S')
            else:
                # It's already an integer timestamp
                order_time = datetime.fromtimestamp(order['created_at']).strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError) as e:
            logger.warning(f"Using raw created_at value due to conversion error: {e}")
            order_time = str(order['created_at'])
        
        message += f"• Order Time: {order_time}\n"
        message += f"• Payment Status: ✅ <b>PAID</b>\n\n"
        
        # Products List
        message += f"📦 <b>ITEMS TO DELIVER:</b>\n"
        for i, item in enumerate(order['products'], 1):
            message += f"{i}. <b>{item['name']}</b>\n"
            message += f"   • Code: <code>{item.get('code', 'N/A')}</code>\n"
            message += f"   • Quantity: <b>{item['quantity']}</b>\n"
            message += f"   • Unit Price: {self.format_price(item['unit_price'])}\n"
            message += f"   • Total: <b>{self.format_price(item['total_price'])}</b>\n\n"
        
        # Delivery Address
        message += f"📍 <b>DELIVERY ADDRESS:</b>\n"
        message += f"<code>{order.get('delivery_address', 'NO ADDRESS PROVIDED')}</code>\n\n"
        
        # Instructions
        message += f"⚠️ <b>ACTION REQUIRED:</b>\n"
        message += f"1. Prepare the items listed above\n"
        message += f"2. Contact customer for delivery coordination\n"
        message += f"3. Update order status after delivery\n\n"
        
        message += f"🔔 This order requires physical delivery to the address above."
        
        # Send to all admins
        for admin_id in admin_ids:
            try:
                self.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode='HTML'
                )
                logger.info(f"Admin notification sent to {admin_id} for order {order['id']}")
            except Exception as e:
                logger.error(f"Error sending admin notification to {admin_id}: {e}")
    
    # Database helper methods
    def get_order_by_id(self, order_id):
        """Get order by ID"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, user_id, username, products, total_cost, status, deadline,
                           delivery_address, payment_track_id, payment_url, created_at
                    FROM orders WHERE id = ?
                ''', (order_id,))
                
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
            logger.error(f"Error getting order: {e}")
            return None
    
    def mark_order_as_completed(self, order_id):
        """Mark order as completed to prevent race conditions and duplicate processing"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE orders SET status = 'completed' WHERE id = ? AND status != 'completed'
                ''', (order_id,))
                
                if cursor.rowcount == 0:
                    # Order was already completed or doesn't exist
                    raise Exception(f"Order {order_id} was already completed or doesn't exist")
                
                conn.commit()
                logger.info(f"🔒 SECURITY: Order {order_id} successfully marked as completed")
                return True
                
        except sqlite3.Error as e:
            logger.error(f"🚨 SECURITY: Database error marking order {order_id} as completed: {e}")
            raise Exception(f"Database error: {e}")
        except Exception as e:
            logger.error(f"🚨 SECURITY: Error marking order {order_id} as completed: {e}")
            raise
    
    def get_order_by_track_id(self, track_id):
        """Get order by payment track ID"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, user_id, username, products, total_cost, status, deadline,
                           delivery_address, payment_track_id, payment_url, created_at
                    FROM orders WHERE payment_track_id = ?
                ''', (track_id,))
                
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
            logger.error(f"Error getting order by track_id: {e}")
            return None
    
    def update_order_payment_info(self, order_id, track_id, payment_url):
        """Update order with payment information"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE orders 
                    SET payment_track_id = ?, payment_url = ?, status = 'payment_phase', updated_at = ?
                    WHERE id = ?
                ''', (track_id, payment_url, int(datetime.now().timestamp()), order_id))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error updating order payment info: {e}")
    
    def update_order_status(self, order_id, status):
        """Update order status"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE orders 
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                ''', (status, int(datetime.now().timestamp()), order_id))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error updating order status: {e}")
    
    def move_order_to_delivery_queue(self, order):
        """Move deliverable order to delivery_queue table"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO delivery_queue 
                    (original_order_id, user_id, username, products, total_cost, 
                     delivery_address, payment_track_id, order_date, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    order['id'], order['user_id'], order.get('username', ''),
                    json.dumps(order['products']), order['total_cost'],
                    order.get('delivery_address', ''), order.get('payment_track_id', ''),
                    order['created_at'], 'awaiting_delivery'
                ))
                conn.commit()
                logger.info(f"Order {order['id']} moved to delivery_queue with status awaiting_delivery")
        except sqlite3.Error as e:
            logger.error(f"Error moving order to delivery_queue: {e}")

    def move_order_to_history(self, order):
        """Move completed order to selling history"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO selling_history 
                    (original_order_id, user_id, username, products, total_cost, 
                     delivery_address, payment_track_id, order_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    order['id'], order['user_id'], order.get('username', ''),
                    json.dumps(order['products']), order['total_cost'],
                    order.get('delivery_address', ''), order.get('payment_track_id', ''),
                    order['created_at']
                ))
                conn.commit()
                logger.info(f"Order {order['id']} moved to selling history")
        except sqlite3.Error as e:
            logger.error(f"Error moving order to history: {e}")
    
    def clear_stock_reservations(self, order_id):
        """Clear stock reservations for completed order"""
        try:
            products_data = self.load_products()
            
            # Remove reservations for this order
            for i, product in enumerate(products_data.get('products', [])):
                if 'reserved_stock' in product:
                    # Remove reservations for this order
                    updated_reservations = [r for r in product['reserved_stock'] if r.get('order_id') != order_id]
                    products_data['products'][i]['reserved_stock'] = updated_reservations
            
            # Save updated products
            save_json_safely("products.json", products_data)
                
        except Exception as e:
            logger.error(f"Error clearing stock reservations: {e}")
    
    def delete_order(self, order_id):
        """Delete order from orders table"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM orders WHERE id = ?', (order_id,))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error deleting order: {e}")
    
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
