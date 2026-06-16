import sqlite3
import logging
import json
import os
from database_pool import DatabasePool
from performance_optimizations import database_operation
from user_manager import UserManager

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path='shop_bot.db'):
        self.db_path = db_path
        # Initialize connection pool for better performance
        self.pool = DatabasePool(db_path)
        # Initialize bulletproof user manager
        self.user_manager = UserManager(self.pool)
        # Enable WAL mode and optimize SQLite for better performance
        self._optimize_sqlite()
        self.init_database()
    
    def _optimize_sqlite(self):
        """Optimize SQLite for better performance"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('PRAGMA journal_mode=WAL')  # Better concurrency
                conn.execute('PRAGMA synchronous=NORMAL')  # Faster writes
                conn.execute('PRAGMA cache_size=10000')  # Larger cache
                conn.execute('PRAGMA temp_store=memory')  # Use memory for temp tables
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not optimize SQLite: {e}")
    
    def init_database(self):
        """Initialize database and create tables if they don't exist"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create users table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER UNIQUE NOT NULL,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        language_code TEXT DEFAULT 'en',
                        balance REAL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Add balance column if it doesn't exist (for existing databases)
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0")
                    logger.info("Added balance column to users table")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                # Create categories table (for future use)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS categories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        description TEXT,
                        is_active BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create products table (for future use)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        description TEXT,
                        price REAL NOT NULL,
                        category_id INTEGER,
                        is_active BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (category_id) REFERENCES categories (id)
                    )
                ''')
                
                # Create user states table for input handling
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_states (
                        user_id INTEGER PRIMARY KEY,
                        state TEXT,
                        data TEXT,
                        message_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create orders table for shopping cart and orders
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        products TEXT NOT NULL,
                        total_cost REAL DEFAULT 0,
                        status TEXT DEFAULT 'pending',
                        deadline TIMESTAMP NOT NULL,
                        delivery_address TEXT,
                        payment_track_id TEXT,
                        payment_url TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create delivery_queue table for deliverable products awaiting delivery
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS delivery_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        original_order_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        products TEXT NOT NULL,
                        total_cost REAL NOT NULL,
                        delivery_address TEXT NOT NULL,
                        payment_track_id TEXT,
                        status TEXT DEFAULT 'awaiting_delivery',
                        order_date TIMESTAMP NOT NULL,
                        payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        delivered_date TIMESTAMP,
                        review TEXT DEFAULT 'pending',
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create selling_history table for completed orders
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS selling_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        original_order_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        products TEXT NOT NULL,
                        total_cost REAL NOT NULL,
                        delivery_address TEXT,
                        payment_track_id TEXT,
                        review TEXT DEFAULT 'pending',
                        order_date TIMESTAMP NOT NULL,
                        completed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create reviews table for storing detailed reviews
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        product_ids TEXT NOT NULL,
                        products TEXT NOT NULL,
                        star_rating INTEGER NOT NULL CHECK(star_rating >= 1 AND star_rating <= 5),
                        review_text TEXT,
                        order_type TEXT NOT NULL,
                        review_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Add review column to existing tables if they don't have it
                try:
                    cursor.execute("ALTER TABLE selling_history ADD COLUMN review TEXT DEFAULT 'pending'")
                    logger.info("Added review column to selling_history table")
                except sqlite3.OperationalError:
                    # Column already exists
                    pass
                
                try:
                    cursor.execute("ALTER TABLE delivery_queue ADD COLUMN review TEXT DEFAULT 'pending'")
                    logger.info("Added review column to delivery_queue table")
                except sqlite3.OperationalError:
                    # Column already exists
                    pass
                
                # Create topup_invoices table for tracking balance top-ups
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS topup_invoices (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        amount REAL NOT NULL,
                        pay_currency TEXT NOT NULL,
                        pay_amount REAL,
                        track_id TEXT UNIQUE,
                        address TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        paid_at TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create disputes table for order issues
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS disputes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        order_id INTEGER NOT NULL,
                        order_type TEXT NOT NULL,
                        dispute_type TEXT NOT NULL,
                        message TEXT NOT NULL,
                        status TEXT DEFAULT 'open',
                        admin_response TEXT,
                        resolved_by INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        resolved_at TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
    
    def get_or_create_user(self, user_id, username=None, first_name=None, last_name=None, language_code='en'):
        """BULLETPROOF: Get user if exists, create if not - NO RACE CONDITIONS"""
        return self.user_manager.get_or_ensure_user(user_id, username, first_name, last_name, language_code)
    
    @database_operation
    def get_user(self, user_id):
        """Get user by user_id - DEPRECATED, use get_or_create_user instead"""
        user_data = self.get_or_create_user(user_id)
        if user_data and not user_data['is_new']:
            return user_data
        return None
    
    def create_user(self, user_id, username=None, first_name=None, last_name=None, language_code='en'):
        """DEPRECATED: Use get_or_create_user instead"""
        result = self.get_or_create_user(user_id, username, first_name, last_name, language_code)
        return result is not None
    
    def update_user_language(self, user_id, language_code):
        """Update user's language preference"""
        return self.user_manager.update_user_language(user_id, language_code)
    
    def is_admin(self, user_id, admin_ids):
        """Check if user is admin"""
        return user_id in admin_ids
    
    def set_user_state(self, user_id, state, data=None, message_id=None):
        """Set user's current state for input handling"""
        try:
            # Serialize data as JSON if it's a dict
            serialized_data = json.dumps(data) if isinstance(data, dict) else data
            
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO user_states (user_id, state, data, message_id)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, state, serialized_data, message_id))
                conn.commit()
                logger.info(f"User {user_id} state set to {state}")
                return True
        except sqlite3.Error as e:
            logger.error(f"Error setting user state: {e}")
            return False
    
    @database_operation
    def get_user_state(self, user_id):
        """Get user's current state"""
        import time
        start_time = time.time()
        logger.info(f"🔍 DEBUG: Database get_user_state START for user {user_id} at {start_time:.3f}")
        
        try:
            conn_start = time.time()
            with self.pool.get_connection() as conn:
                conn_time = time.time() - conn_start
                logger.info(f"🔍 DEBUG: Database connection acquired in {conn_time:.3f}s")
                
                cursor = conn.cursor()
                query_start = time.time()
                cursor.execute('SELECT state, data, message_id FROM user_states WHERE user_id = ?', (user_id,))
                result = cursor.fetchone()
                query_time = time.time() - query_start
                logger.info(f"🔍 DEBUG: Database query executed in {query_time:.3f}s")
                
                if result:
                    # Deserialize data if it's JSON
                    process_start = time.time()
                    data = result[1]
                    if isinstance(data, str) and data.startswith('{'):
                        try:
                            data = json.loads(data)
                        except json.JSONDecodeError:
                            pass  # Keep as string if JSON parsing fails
                    
                    user_state = {
                        'state': result[0],
                        'data': data,
                        'message_id': result[2]
                    }
                    process_time = time.time() - process_start
                    logger.info(f"🔍 DEBUG: Data processing took {process_time:.3f}s")
                    
                    total_time = time.time() - start_time
                    logger.info(f"🔍 DEBUG: Database get_user_state COMPLETE in {total_time:.3f}s for user {user_id}, state: {result[0]}")
                    return user_state
                    
                total_time = time.time() - start_time
                logger.info(f"🔍 DEBUG: Database get_user_state COMPLETE in {total_time:.3f}s for user {user_id}, no state found")
                return None
        except sqlite3.Error as e:
            total_time = time.time() - start_time
            logger.error(f"🔍 DEBUG: Database get_user_state ERROR in {total_time:.3f}s for user {user_id}: {e}")
            return None
    
    def clear_user_state(self, user_id):
        """Clear user's state"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM user_states WHERE user_id = ?', (user_id,))
                conn.commit()
                logger.info(f"User {user_id} state cleared")
                return True
        except sqlite3.Error as e:
            logger.error(f"Error clearing user state: {e}")
            return False
    
    # ==================== TOPUP METHODS ====================
    
    def get_user_balance(self, user_id):
        """Get user's balance"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
                result = cursor.fetchone()
                return result[0] if result else 0.0
        except sqlite3.Error as e:
            logger.error(f"Error getting user balance: {e}")
            return 0.0
    
    def add_user_balance(self, user_id, amount):
        """Add amount to user's balance"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (amount, user_id))
                conn.commit()
                logger.info(f"Added ${amount} to user {user_id} balance")
                return True
        except sqlite3.Error as e:
            logger.error(f"Error adding user balance: {e}")
            return False
    
    def create_topup_invoice(self, user_id, amount, pay_currency, pay_amount, track_id, address):
        """Create a new topup invoice"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO topup_invoices (user_id, amount, pay_currency, pay_amount, track_id, address, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending')
                ''', (user_id, amount, pay_currency, pay_amount, track_id, address))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Error creating topup invoice: {e}")
            return None
    
    def get_pending_topup_invoice(self, user_id):
        """Get user's pending topup invoice"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, user_id, amount, pay_currency, pay_amount, track_id, address, status, created_at
                    FROM topup_invoices 
                    WHERE user_id = ? AND status = 'pending'
                    ORDER BY created_at DESC LIMIT 1
                ''', (user_id,))
                result = cursor.fetchone()
                if result:
                    return {
                        'id': result[0],
                        'user_id': result[1],
                        'amount': result[2],
                        'pay_currency': result[3],
                        'pay_amount': result[4],
                        'track_id': result[5],
                        'address': result[6],
                        'status': result[7],
                        'created_at': result[8]
                    }
                return None
        except sqlite3.Error as e:
            logger.error(f"Error getting pending topup invoice: {e}")
            return None
    
    def get_all_pending_topup_invoices(self):
        """Get all pending topup invoices for auto-checking"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, user_id, amount, pay_currency, pay_amount, track_id, address, status, created_at
                    FROM topup_invoices 
                    WHERE status = 'pending'
                ''')
                results = cursor.fetchall()
                invoices = []
                for result in results:
                    invoices.append({
                        'id': result[0],
                        'user_id': result[1],
                        'amount': result[2],
                        'pay_currency': result[3],
                        'pay_amount': result[4],
                        'track_id': result[5],
                        'address': result[6],
                        'status': result[7],
                        'created_at': result[8]
                    })
                return invoices
        except sqlite3.Error as e:
            logger.error(f"Error getting all pending topup invoices: {e}")
            return []
    
    def mark_topup_invoice_paid(self, track_id):
        """Mark a topup invoice as paid"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE topup_invoices 
                    SET status = 'paid', paid_at = CURRENT_TIMESTAMP
                    WHERE track_id = ?
                ''', (track_id,))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error marking topup invoice paid: {e}")
            return False
    
    def cancel_topup_invoice(self, invoice_id, user_id):
        """Cancel a topup invoice"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM topup_invoices 
                    WHERE id = ? AND user_id = ? AND status = 'pending'
                ''', (invoice_id, user_id))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error cancelling topup invoice: {e}")
            return False
    
    def get_topup_invoice_by_track_id(self, track_id):
        """Get topup invoice by track_id"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, user_id, amount, pay_currency, pay_amount, track_id, address, status, created_at
                    FROM topup_invoices 
                    WHERE track_id = ?
                ''', (track_id,))
                result = cursor.fetchone()
                if result:
                    return {
                        'id': result[0],
                        'user_id': result[1],
                        'amount': result[2],
                        'pay_currency': result[3],
                        'pay_amount': result[4],
                        'track_id': result[5],
                        'address': result[6],
                        'status': result[7],
                        'created_at': result[8]
                    }
                return None
        except sqlite3.Error as e:
            logger.error(f"Error getting topup invoice by track_id: {e}")
            return None
    
    # ==================== REVIEWS ====================
    
    def get_all_reviews(self, page=1, per_page=5):
        """Get all reviews with pagination"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                offset = (page - 1) * per_page
                
                cursor.execute('''
                    SELECT id, order_id, user_id, username, products, star_rating, review_text, review_date
                    FROM reviews
                    ORDER BY review_date DESC
                    LIMIT ? OFFSET ?
                ''', (per_page, offset))
                
                reviews = []
                for row in cursor.fetchall():
                    reviews.append({
                        'id': row[0],
                        'order_id': row[1],
                        'user_id': row[2],
                        'username': row[3],
                        'products': row[4],
                        'star_rating': row[5],
                        'review_text': row[6],
                        'review_date': row[7]
                    })
                return reviews
        except sqlite3.Error as e:
            logger.error(f"Error getting all reviews: {e}")
            return []
    
    def get_reviews_count(self):
        """Get total count of reviews"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM reviews')
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Error getting reviews count: {e}")
            return 0
    
    def get_average_rating(self):
        """Get average star rating from all reviews"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT AVG(star_rating), COUNT(*) FROM reviews')
                result = cursor.fetchone()
                avg = result[0] if result[0] else 0
                count = result[1] if result[1] else 0
                return {'average': round(avg, 1), 'count': count}
        except sqlite3.Error as e:
            logger.error(f"Error getting average rating: {e}")
            return {'average': 0, 'count': 0}
    
    # ==================== DISPUTES ====================
    
    def create_dispute(self, user_id, order_id, order_type, dispute_type, message):
        """Create a new dispute"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO disputes (user_id, order_id, order_type, dispute_type, message)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, order_id, order_type, dispute_type, message))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Error creating dispute: {e}")
            return None
    
    def get_user_disputes(self, user_id):
        """Get all disputes for a user"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, order_id, order_type, dispute_type, message, status, admin_response, created_at, resolved_at
                    FROM disputes
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                ''', (user_id,))
                
                disputes = []
                for row in cursor.fetchall():
                    disputes.append({
                        'id': row[0],
                        'order_id': row[1],
                        'order_type': row[2],
                        'dispute_type': row[3],
                        'message': row[4],
                        'status': row[5],
                        'admin_response': row[6],
                        'created_at': row[7],
                        'resolved_at': row[8]
                    })
                return disputes
        except sqlite3.Error as e:
            logger.error(f"Error getting user disputes: {e}")
            return []
    
    def get_open_dispute_for_order(self, user_id, order_id, order_type):
        """Check if there's an open dispute for an order"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id FROM disputes
                    WHERE user_id = ? AND order_id = ? AND order_type = ? AND status = 'open'
                ''', (user_id, order_id, order_type))
                return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Error checking open dispute: {e}")
            return False
    
    def get_all_open_disputes(self):
        """Get all open disputes for admin"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT d.id, d.user_id, d.order_id, d.order_type, d.dispute_type, d.message, d.status, d.created_at, u.username
                    FROM disputes d
                    LEFT JOIN users u ON d.user_id = u.user_id
                    WHERE d.status = 'open'
                    ORDER BY d.created_at ASC
                ''')
                
                disputes = []
                for row in cursor.fetchall():
                    disputes.append({
                        'id': row[0],
                        'user_id': row[1],
                        'order_id': row[2],
                        'order_type': row[3],
                        'dispute_type': row[4],
                        'message': row[5],
                        'status': row[6],
                        'created_at': row[7],
                        'username': row[8]
                    })
                return disputes
        except sqlite3.Error as e:
            logger.error(f"Error getting all open disputes: {e}")
            return []
    
    def get_dispute_by_id(self, dispute_id):
        """Get dispute by ID"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT d.id, d.user_id, d.order_id, d.order_type, d.dispute_type, d.message, d.status, d.admin_response, d.created_at, d.resolved_at, u.username
                    FROM disputes d
                    LEFT JOIN users u ON d.user_id = u.user_id
                    WHERE d.id = ?
                ''', (dispute_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'user_id': row[1],
                        'order_id': row[2],
                        'order_type': row[3],
                        'dispute_type': row[4],
                        'message': row[5],
                        'status': row[6],
                        'admin_response': row[7],
                        'created_at': row[8],
                        'resolved_at': row[9],
                        'username': row[10]
                    }
                return None
        except sqlite3.Error as e:
            logger.error(f"Error getting dispute by id: {e}")
            return None
    
    def resolve_dispute(self, dispute_id, admin_id, admin_response):
        """Resolve a dispute"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE disputes 
                    SET status = 'resolved', admin_response = ?, resolved_by = ?, resolved_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (admin_response, admin_id, dispute_id))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error resolving dispute: {e}")
            return False
    
    def get_dispute_count(self, status='open'):
        """Get count of disputes by status"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM disputes WHERE status = ?', (status,))
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Error getting dispute count: {e}")
            return 0