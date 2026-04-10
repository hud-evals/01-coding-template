import pytest
import shutil
import tempfile
from pathlib import Path
from wiki_engine import WikiEngine

def get_engine():
    """Helper to create a fresh engine in a temp dir."""
    tmp = tempfile.mkdtemp()
    engine = WikiEngine(tmp)
    return engine, tmp

def test_page_creation():
    engine, tmp = get_engine()
    try:
        success = engine.create_page("test", "Content", "user1")
        assert success is True
        content, version = engine.get_page("test")
        assert content == "Content"
        assert version == 1
    finally:
        shutil.rmtree(tmp)

def test_page_updates():
    engine, tmp = get_engine()
    try:
        engine.create_page("test", "V1", "u1")
        # Correct update
        success = engine.update_page("test", "V2", "u1", expected_version=1)
        assert success is True
        _, version = engine.get_page("test")
        assert version == 2
    finally:
        shutil.rmtree(tmp)

def test_revision_history():
    engine, tmp = get_engine()
    try:
        engine.create_page("test", "V1", "u1")
        engine.update_page("test", "V2", "u1", expected_version=1)
        engine.update_page("test", "V3", "u1", expected_version=2)
        
        history = engine.get_history("test")
        assert len(history) == 3
        assert history[0]["version"] == 1
        assert history[2]["version"] == 3
    finally:
        shutil.rmtree(tmp)

def test_rollback():
    engine, tmp = get_engine()
    try:
        engine.create_page("test", "V1", "u1")
        engine.update_page("test", "V2", "u1", expected_version=1)
        
        # Retrieve specific version
        v1_content, v1_ver = engine.get_page("test", version=1)
        assert v1_content == "V1"
        assert v1_ver == 1
    finally:
        shutil.rmtree(tmp)

def test_conflict_detection():
    engine, tmp = get_engine()
    try:
        engine.create_page("test", "V1", "u1")
        
        # Simulate two users loading V1 (ver=1)
        # User A updates
        success_a = engine.update_page("test", "V2-A", "userA", expected_version=1)
        assert success_a is True
        
        # User B tries to update using outdated V1 reference
        success_b = engine.update_page("test", "V2-B", "userB", expected_version=1)
        assert success_b is False
        
        # Verify User A's version is there
        content, version = engine.get_page("test")
        assert content == "V2-A"
        assert version == 2
    finally:
        shutil.rmtree(tmp)
