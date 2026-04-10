import pytest
from secure_api import EcommerceBackend

def test_logic_positive():
    backend = EcommerceBackend()
    res = backend.checkout(1, 1, 1) # admin buys 1 laptop
    assert res["status"] == "success"
    assert res["cost"] == 800.0
    
    user = backend.get_user_data(1, 1)
    assert user["balance"] == 200.0 # starts at 1000, 800 spent

def test_logic_insufficient_funds():
    backend = EcommerceBackend()
    with pytest.raises(ValueError):
        backend.checkout(2, 1, 1)

def test_logic_negative_quantity():
    backend = EcommerceBackend()
    with pytest.raises(ValueError):
        backend.checkout(1, 1, -5) # negative admin buy should fail

def test_logic_zero_quantity():
    """Zero quantity should also raise ValueError."""
    backend = EcommerceBackend()
    with pytest.raises(ValueError):
        backend.checkout(1, 1, 0)

def test_logic_insufficient_stock():
    """Buying more than available stock must fail."""
    backend = EcommerceBackend()
    with pytest.raises(ValueError):
        backend.checkout(1, 1, 999)

def test_logic_nonexistent_product():
    """Buying a product that doesn't exist must fail."""
    backend = EcommerceBackend()
    with pytest.raises(ValueError):
        backend.checkout(1, 999, 1)

def test_logic_stock_decrements():
    """After purchase, stock must actually decrease."""
    backend = EcommerceBackend()
    res = backend.checkout(1, 1, 1)  # admin buys 1 laptop (800)
    assert res["cost"] == 800.0
    
    # Admin now has 200.0 balance, can't afford another laptop
    with pytest.raises(ValueError):
        backend.checkout(1, 1, 1)
