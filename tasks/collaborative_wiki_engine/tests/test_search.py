import pytest
import shutil
import tempfile
from wiki_engine import WikiEngine

def get_engine():
    tmp = tempfile.mkdtemp()
    engine = WikiEngine(tmp)
    return engine, tmp

def test_basic_search():
    engine, tmp = get_engine()
    try:
        engine.create_page("p1", "The quick brown fox", "u1")
        engine.create_page("p2", "Jumped over the lazy dog", "u1")
        
        results = engine.search("fox")
        assert "p1" in results
        assert "p2" not in results
    finally:
        shutil.rmtree(tmp)

def test_multi_term_search():
    engine, tmp = get_engine()
    try:
        engine.create_page("p1", "apple banana", "u1")
        engine.create_page("p2", "banana cherry", "u1")
        
        results = engine.search("apple banana")
        assert "p1" in results
        assert "p2" in results
    finally:
        shutil.rmtree(tmp)

def test_ranking_by_frequency():
    engine, tmp = get_engine()
    try:
        engine.create_page("low", "Word", "u1")
        engine.create_page("high", "Word Word Word", "u1")
        
        results = engine.search("Word")
        # 'high' has freq 3, 'low' has 1. 'high' should be first.
        assert results[0] == "high"
        assert results[1] == "low"
    finally:
        shutil.rmtree(tmp)

def test_case_insensitivity():
    engine, tmp = get_engine()
    try:
        engine.create_page("p1", "PyThOn", "u1")
        results = engine.search("python")
        assert "p1" in results
    finally:
        shutil.rmtree(tmp)

def test_index_updates_on_save():
    engine, tmp = get_engine()
    try:
        engine.create_page("p1", "v1", "u1")
        assert len(engine.search("v1")) == 1
        
        engine.update_page("p1", "v2", "u1", expected_version=1)
        assert len(engine.search("v1")) == 0
        assert len(engine.search("v2")) == 1
    finally:
        shutil.rmtree(tmp)
