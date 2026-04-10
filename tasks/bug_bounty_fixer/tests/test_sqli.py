import pytest
from secure_api import EcommerceBackend

def test_sqli_protection():
    backend = EcommerceBackend()
    # Normal login
    assert backend.login("admin", "supersecret") == 1
    
    # SQLi Auth Bypass Attempts
    assert backend.login("admin", "' OR 1=1--") is None
    assert backend.login("admin' --", "anything") is None

def test_sqli_union_attack():
    """UNION-based SQLi should also be blocked."""
    backend = EcommerceBackend()
    assert backend.login("' UNION SELECT 1,2,3--", "x") is None
    assert backend.login("admin", "' UNION SELECT id FROM users--") is None

def test_sqli_stacked_queries():
    """Stacked queries like DROP TABLE should not execute."""
    backend = EcommerceBackend()
    result = backend.login("admin'; DROP TABLE users; --", "x")
    assert result is None
    # Verify the table still exists
    assert backend.login("admin", "supersecret") == 1

def test_login_wrong_password():
    backend = EcommerceBackend()
    assert backend.login("admin", "wrongpassword") is None
    assert backend.login("nonexistent", "pass") is None
