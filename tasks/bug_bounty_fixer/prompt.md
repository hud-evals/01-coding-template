# Task: Secure E-Commerce Backend Implementation

You are a Backend Security Engineer. You must implement a complete, production-hardened e-commerce API module in `/home/ubuntu/workspace/secure_api.py`.

## Requirements

Implement a class `EcommerceBackend` using `sqlite3` with an in-memory database.

### Database Schema
Initialize three tables:
- `users`: `id INTEGER PRIMARY KEY, username TEXT, password TEXT, balance REAL`
- `products`: `id INTEGER PRIMARY KEY, name TEXT, stock INTEGER, price REAL`
- `comments`: `id INTEGER PRIMARY KEY, product_id INTEGER, comment TEXT`

Pre-seed the database with initial records during `__init__`.

### Methods to Implement

1. `def login(self, username: str, password: str) -> int | None`
   - Returns the user `id` if credentials match, otherwise `None`.
   - Must be resilient against all known database query injection techniques.

2. `def add_comment(self, product_id: int, comment: str) -> bool`
   - Stores a comment for a product. Returns `True` on success.
   - Must sanitize all inputs to prevent any form of script injection or markup exploitation.

3. `def get_comments(self, product_id: int) -> list[str]`
   - Returns all comments for a given product as a list of strings.

4. `def checkout(self, user_id: int, product_id: int, quantity: int) -> dict`
   - Processes a purchase. Deducts stock and balance. Returns `{"status": "success", "cost": <total>}`.
   - Must enforce comprehensive input validation including boundary checks on all numeric parameters.
   - Must raise `ValueError` with descriptive messages for any constraint violation.

5. `def get_user_data(self, requested_id: int, session_token_user_id: int) -> dict | None`
   - Returns `{"username": ..., "balance": ...}` for the requested user.
   - Must implement proper authorization checks to prevent unauthorized data access.

### Constraints
- Python standard library only. Use `sqlite3` and `html` modules.
- Do not change function signatures.
- Implementation must be secure, deterministic, and regression-free.
