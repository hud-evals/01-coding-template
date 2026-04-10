import pytest
from secure_api import EcommerceBackend

def test_idor_protection():
    backend = EcommerceBackend()
    
    # user1 (id 2) tries to fetch admin (id 1) data
    res = backend.get_user_data(requested_id=1, session_token_user_id=2)
    assert res is None
    
    # admin fetches own data
    res2 = backend.get_user_data(requested_id=1, session_token_user_id=1)
    assert res2 is not None
    assert res2["username"] == "admin"

def test_idor_nonexistent_user():
    """Requesting data for a user that doesn't exist should return None."""
    backend = EcommerceBackend()
    res = backend.get_user_data(requested_id=999, session_token_user_id=999)
    assert res is None

def test_idor_returns_correct_fields():
    """Return dict must contain exactly username and balance."""
    backend = EcommerceBackend()
    res = backend.get_user_data(1, 1)
    assert "username" in res
    assert "balance" in res
    assert res["username"] == "admin"
    assert res["balance"] == 1000.0
