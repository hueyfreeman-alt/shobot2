import telebot
import logging
import sqlite3
import json
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io

logger = logging.getLogger(__name__)

class OrderManagementHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
    
    def handle_order_management(self, call):
        """Handle order management menu"""
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
        
        # Create order management menu
        menu_text = self.get_order_management_text(lang_code)
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add download options
        markup.add(
            telebot.types.InlineKeyboardButton(
                text="📅 Download Today's Orders",
                callback_data='order_download_today'
            )
        )
        markup.add(
            telebot.types.InlineKeyboardButton(
                text="📆 Download Yesterday's Orders", 
                callback_data='order_download_yesterday'
            )
        )
        markup.add(
            telebot.types.InlineKeyboardButton(
                text="📊 Download All Orders",
                callback_data='order_download_all'
            )
        )
        
        # Add back button
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
                text=menu_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=menu_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        
        # Answer callback query
        self.bot.answer_callback_query(call.id)
    
    def handle_order_download(self, call):
        """Handle order download requests"""
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
        
        # Extract download type from callback data
        download_type = call.data.replace('order_download_', '')
        
        # Show loading message
        self.bot.answer_callback_query(call.id, "📄 Generating PDF report...")
        
        try:
            # Generate PDF based on type
            pdf_buffer = self.generate_pdf_report(download_type, lang_code)
            
            if pdf_buffer:
                # Send PDF file
                filename = f"orders_{download_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                
                # Reset buffer position for reading
                pdf_buffer.seek(0)
                
                self.bot.send_document(
                    chat_id=call.message.chat.id,
                    document=(filename, pdf_buffer, 'application/pdf'),
                    caption=f"📦 Order Report - {download_type.title()}\n📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            else:
                self.bot.send_message(
                    chat_id=call.message.chat.id,
                    text="❌ No orders found for the selected period."
                )
        
        except Exception as e:
            logger.error(f"Error generating PDF report: {e}")
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text="❌ Error generating PDF report. Please try again."
            )
    
    def generate_pdf_report(self, download_type, lang_code):
        """Generate PDF report based on download type"""
        try:
            # Get orders from database
            awaiting_delivery, delivered_orders, selling_history, cancelled_orders = self.get_orders_by_type(download_type)
            
            if not awaiting_delivery and not delivered_orders and not selling_history and not cancelled_orders:
                return None
            
            # Create PDF buffer
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            
            # Build PDF content
            story = []
            styles = getSampleStyleSheet()
            
            # Title style
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                spaceAfter=30,
                alignment=1  # Center alignment
            )
            
            # Add title
            title_text = f"📦 Order Report - {download_type.title()}"
            story.append(Paragraph(title_text, title_style))
            story.append(Spacer(1, 20))
            
            # Add generation info
            info_text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            story.append(Paragraph(info_text, styles['Normal']))
            story.append(Spacer(1, 20))
            
            # Add awaiting delivery section
            if awaiting_delivery:
                story.append(Paragraph("⏳ Awaiting Delivery Orders", styles['Heading2']))
                story.append(Spacer(1, 10))
                
                awaiting_table_data = [
                    ['Order ID', 'User', 'Products', 'Total', 'Address', 'Date']
                ]
                
                for order in awaiting_delivery:
                    products_text = self.format_products_for_pdf(order['products'])
                    address_text = order['delivery_address'][:25] + '...' if len(order['delivery_address']) > 25 else order['delivery_address']
                    date_text = order['order_date'][:10] if order['order_date'] else 'N/A'
                    
                    awaiting_table_data.append([
                        str(order['original_order_id']),
                        (order['username'] or 'N/A')[:12],
                        products_text,
                        f"${order['total_cost']:.2f}",
                        address_text,
                        date_text
                    ])
                
                awaiting_table = Table(awaiting_table_data)
                awaiting_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.orange),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.lightyellow),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                
                story.append(awaiting_table)
                story.append(Spacer(1, 30))
            
            # Add delivered orders section
            if delivered_orders:
                story.append(Paragraph("🚚 Delivered Orders", styles['Heading2']))
                story.append(Spacer(1, 10))
                
                delivered_table_data = [
                    ['Order ID', 'User', 'Products', 'Total', 'Address', 'Order Date', 'Delivered Date']
                ]
                
                for order in delivered_orders:
                    products_text = self.format_products_for_pdf(order['products'])
                    address_text = order['delivery_address'][:20] + '...' if len(order['delivery_address']) > 20 else order['delivery_address']
                    order_date = order['order_date'][:10] if order['order_date'] else 'N/A'
                    delivered_date = order['delivered_date'][:10] if order['delivered_date'] else 'N/A'
                    
                    delivered_table_data.append([
                        str(order['original_order_id']),
                        (order['username'] or 'N/A')[:10],
                        products_text,
                        f"${order['total_cost']:.2f}",
                        address_text,
                        order_date,
                        delivered_date
                    ])
                
                delivered_table = Table(delivered_table_data)
                delivered_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.blue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
                    ('FONTSIZE', (0, 1), (-1, -1), 7),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                
                story.append(delivered_table)
                story.append(Spacer(1, 30))
            
            # Add selling history section
            if selling_history:
                story.append(Paragraph("✅ Completed Orders (Selling History)", styles['Heading2']))
                story.append(Spacer(1, 10))
                
                # Create selling history table
                history_table_data = [
                    ['Order ID', 'User', 'Products', 'Total', 'Order Date', 'Completed', 'Review']
                ]
                
                for order in selling_history:
                    products_text = self.format_products_for_pdf(order['products'])
                    review_text = order['review'][:15] + '...' if order['review'] and len(order['review']) > 15 else (order['review'] or 'No review')
                    order_date = order['order_date'][:10] if order['order_date'] else 'N/A'
                    completed_date = order['completed_date'][:10] if order['completed_date'] else 'N/A'
                    
                    history_table_data.append([
                        str(order['original_order_id']),
                        (order['username'] or 'N/A')[:12],  # Limit username length
                        products_text,
                        f"${order['total_cost']:.2f}",
                        order_date,
                        completed_date,
                        review_text
                    ])
                
                history_table = Table(history_table_data)
                history_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.lightgreen),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                
                story.append(history_table)
                story.append(Spacer(1, 30))
            
            # Add cancelled orders section
            if cancelled_orders:
                story.append(Paragraph("❌ Cancelled Orders", styles['Heading2']))
                story.append(Spacer(1, 10))
                
                cancelled_table_data = [
                    ['Order ID', 'User', 'Products', 'Total', 'Order Date', 'Cancelled Date', 'Reason']
                ]
                
                for order in cancelled_orders:
                    products_text = self.format_products_for_pdf(order['products'])
                    order_date = order['order_date'][:10] if order['order_date'] else 'N/A'
                    cancelled_date = order['cancelled_date'][:10] if order['cancelled_date'] else 'N/A'
                    reason = order.get('cancellation_reason', 'Admin cancelled')[:15]
                    
                    cancelled_table_data.append([
                        str(order['original_order_id']),
                        (order['username'] or 'N/A')[:12],
                        products_text,
                        f"${order['total_cost']:.2f}",
                        order_date,
                        cancelled_date,
                        reason
                    ])
                
                cancelled_table = Table(cancelled_table_data)
                cancelled_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.red),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.mistyrose),
                    ('FONTSIZE', (0, 1), (-1, -1), 7),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                
                story.append(cancelled_table)
                story.append(Spacer(1, 30))
            
            # Add summary
            total_awaiting = len(awaiting_delivery)
            total_delivered = len(delivered_orders)
            total_completed = len(selling_history)
            total_cancelled = len(cancelled_orders)
            total_orders = total_awaiting + total_delivered + total_completed + total_cancelled
            
            summary_text = f"""
            📊 Summary:
            • Total Orders: {total_orders}
            • Awaiting Delivery: {total_awaiting}
            • Delivered Orders: {total_delivered}
            • Completed Orders: {total_completed}
            • Cancelled Orders: {total_cancelled}
            """
            
            story.append(Paragraph("📊 Order Summary", styles['Heading2']))
            story.append(Paragraph(summary_text, styles['Normal']))
            
            # Build PDF
            doc.build(story)
            buffer.seek(0)
            
            return buffer
            
        except Exception as e:
            logger.error(f"Error generating PDF: {e}")
            return None
    
    def get_orders_by_type(self, download_type):
        """Get orders from database based on download type"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Determine date filter
                if download_type == 'today':
                    date_filter = datetime.now().strftime('%Y-%m-%d')
                    date_condition = "DATE(order_date) = ?"
                    params = (date_filter,)
                elif download_type == 'yesterday':
                    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                    date_condition = "DATE(order_date) = ?"
                    params = (yesterday,)
                else:  # all
                    date_condition = "1=1"
                    params = ()
                
                # Get delivery queue orders (separated by status)
                awaiting_delivery_query = f"""
                    SELECT * FROM delivery_queue 
                    WHERE {date_condition} AND status = 'awaiting_delivery'
                    ORDER BY order_date DESC
                """
                cursor.execute(awaiting_delivery_query, params)
                awaiting_delivery = [dict(row) for row in cursor.fetchall()]
                
                delivered_query = f"""
                    SELECT * FROM delivery_queue 
                    WHERE {date_condition} AND status = 'delivered'
                    ORDER BY order_date DESC
                """
                cursor.execute(delivered_query, params)
                delivered_orders = [dict(row) for row in cursor.fetchall()]
                
                # Get selling history orders
                history_query = f"""
                    SELECT * FROM selling_history 
                    WHERE {date_condition}
                    ORDER BY order_date DESC
                """
                cursor.execute(history_query, params)
                selling_history = [dict(row) for row in cursor.fetchall()]
                
                # Get cancelled orders
                cancelled_query = f"""
                    SELECT * FROM cancelled_orders 
                    WHERE {date_condition}
                    ORDER BY order_date DESC
                """
                cursor.execute(cancelled_query, params)
                cancelled_orders = [dict(row) for row in cursor.fetchall()]
                
                return awaiting_delivery, delivered_orders, selling_history, cancelled_orders
                
        except Exception as e:
            logger.error(f"Error querying orders: {e}")
            return [], [], [], []
    
    def format_products_for_pdf(self, products_json):
        """Format products JSON for PDF display"""
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
                        # Clean up product name (remove emojis and extra characters)
                        clean_name = ''.join(char for char in name if ord(char) < 127 or char.isalpha())[:20]
                        product_names.append(f"{clean_name} (x{quantity})")
                    else:
                        product_names.append(str(product)[:20])
                
                result = ', '.join(product_names)
                return result[:35] + ('...' if len(result) > 35 else '')
            else:
                return str(products)[:35] + ('...' if len(str(products)) > 35 else '')
                
        except Exception as e:
            logger.error(f"Error formatting products: {e}")
            return "Error formatting products"
    
    def get_order_management_text(self, lang_code):
        """Get order management menu text"""
        if lang_code == 'es':
            return """
📦 <b>Gestión de Pedidos</b>

📋 <b>Descargar Reportes de Pedidos</b>
Selecciona el período de tiempo para tu reporte:
📅 <b>Hoy:</b> Pedidos realizados hoy
📆 <b>Ayer:</b> Pedidos de ayer
📊 <b>Todos:</b> Historial completo de pedidos

📱 <b>Comandos de Admin (Copiar y Usar):</b>

🚚 <b>Marcar como Entregado:</b>
<code>/delivered 51</code>
<i>Actualiza el estado del pedido a "entregado" y notifica al usuario</i>

✅ <b>Completar Pedido:</b>
<code>/completed 51</code>
<i>Mueve el pedido al historial de ventas y envía opción de reseña</i>

❌ <b>Cancelar Pedido:</b>
<code>/cancelled 51</code>
<i>Cancela el pedido y dirige al usuario al soporte admin</i>

💡 <b>Uso:</b> Reemplaza "51" con el ID real del Pedido

📊 <b>Flujo de Pedidos:</b>
1. 📦 Pedido realizado → Esperando Entrega
2. 🚚 /delivered → Estado entregado
3. ✅ /completed → Historial de Ventas + Opción de reseña
4. ❌ /cancelled → Tabla de pedidos cancelados

<i>Los reportes incluyen todos los estados de pedidos con información detallada.</i>
            """.strip()
        else:
            return """
📦 <b>Order Management</b>

📋 <b>Download Order Reports</b>
Select the time period for your order report:
📅 <b>Today:</b> Orders placed today
📆 <b>Yesterday:</b> Orders from yesterday  
📊 <b>All Orders:</b> Complete order history

📱 <b>Admin Commands (Copy & Use):</b>

🚚 <b>Mark as Delivered:</b>
<code>/delivered 51</code>
<i>Updates order status to "delivered" and notifies user</i>

✅ <b>Complete Order:</b>
<code>/completed 51</code>
<i>Moves order to selling history and sends review option</i>

❌ <b>Cancel Order:</b>
<code>/cancelled 51</code>
<i>Cancels order and directs user to admin support</i>

💡 <b>Usage:</b> Replace "51" with the actual Order ID

📊 <b>Order Flow:</b>
1. 📦 Order placed → Awaiting Delivery
2. 🚚 /delivered → Delivered status
3. ✅ /completed → Selling History + Review option
4. ❌ /cancelled → Cancelled Orders table

<i>Reports include all order statuses with detailed information.</i>
            """.strip()
