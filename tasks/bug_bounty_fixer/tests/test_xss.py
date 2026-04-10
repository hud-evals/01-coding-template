import pytest
from secure_api import EcommerceBackend

def test_xss_protection():
    backend = EcommerceBackend()
    
    payload = "<script>alert(document.cookie)</script>"
    backend.add_comment(1, payload)
    
    comments = backend.get_comments(1)
    assert len(comments) == 1
    
    # Must be escaped
    assert "<script>" not in comments[0]
    assert "&lt;script&gt;" in comments[0]

def test_xss_img_onerror():
    """IMG onerror XSS vector must also be escaped."""
    backend = EcommerceBackend()
    payload = '<img src=x onerror="alert(1)">'
    backend.add_comment(1, payload)
    comments = backend.get_comments(1)
    assert '<img' not in comments[-1]
    assert '&lt;img' in comments[-1]

def test_xss_event_handler():
    """Event handler attributes must be escaped."""
    backend = EcommerceBackend()
    payload = '<div onmouseover="steal()">'
    backend.add_comment(1, payload)
    comments = backend.get_comments(1)
    assert '<div' not in comments[-1]

def test_comment_normal_text():
    """Normal text should be stored and returned unchanged."""
    backend = EcommerceBackend()
    backend.add_comment(1, "Great product, 5 stars!")
    comments = backend.get_comments(1)
    assert "Great product, 5 stars!" in comments
