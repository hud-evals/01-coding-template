import sqlite3
import html
from typing import Dict, List, Optional, Any

class EcommerceBackend:
    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        c = self.conn.cursor()
        c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, balance REAL)")
        c.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, stock INTEGER, price REAL)")
        c.execute("CREATE TABLE comments (id INTEGER PRIMARY KEY, product_id INTEGER, comment TEXT)")
        
        # Seed
        c.execute("INSERT INTO users (username, password, balance) VALUES ('admin', 'supersecret', 1000.0)")
        c.execute("INSERT INTO users (username, password, balance) VALUES ('user1', 'pass123', 50.0)")
        c.execute("INSERT INTO products (name, stock, price) VALUES ('laptop', 10, 800.0)")
        self.conn.commit()

    def login(self, username: str, password: str) -> Optional[int]:
        """
        VULNERABILITY: SQL injection (e.g. username="admin' --")
        FIX: Parameterized query.
        """
        c = self.conn.cursor()
        c.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, password))
        row = c.fetchone()
        return row["id"] if row else None

    def add_comment(self, product_id: int, comment: str) -> bool:
        """
        VULNERABILITY: Stored XSS (returning unsanitized HTML later or storing it)
        FIX: HTML escaping `&`, `<`, `>`, `"`, `'`.
        """
        safe_comment = html.escape(comment)
        c = self.conn.cursor()
        c.execute("INSERT INTO comments (product_id, comment) VALUES (?, ?)", (product_id, safe_comment))
        self.conn.commit()
        return True
        
    def get_comments(self, product_id: int) -> List[str]:
        c = self.conn.cursor()
        c.execute("SELECT comment FROM comments WHERE product_id = ?", (product_id,))
        return [row["comment"] for row in c.fetchall()]

    def checkout(self, user_id: int, product_id: int, quantity: int) -> Dict[str, Any]:
        """
        VULNERABILITY: Negative quantity integer logic bug / logic bypass allowing balance increase.
        FIX: Enforce quantity > 0 and stock availability.
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive.")
            
        c = self.conn.cursor()
        c.execute("SELECT stock, price FROM products WHERE id = ?", (product_id,))
        prod = c.fetchone()
        if not prod or prod["stock"] < quantity:
            raise ValueError("Insufficient stock.")
            
        total_cost = prod["price"] * quantity
        
        c.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()
        if not user or user["balance"] < total_cost:
            raise ValueError("Insufficient funds.")
            
        # Execute safe atomic-like update
        c.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product_id))
        c.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (total_cost, user_id))
        self.conn.commit()
        return {"status": "success", "cost": total_cost}

    def get_user_data(self, requested_id: int, session_token_user_id: int) -> Optional[Dict[str, Any]]:
        """
        VULNERABILITY: Insecure Direct Object Reference (IDOR).
        FIX: Enforce that requested_id == session_token_user_id (or admin).
        """
        if requested_id != session_token_user_id:
            return None # IDOR Patch: Access Denied
            
        c = self.conn.cursor()
        c.execute("SELECT username, balance FROM users WHERE id = ?", (requested_id,))
        row = c.fetchone()
        return dict(row) if row else None
