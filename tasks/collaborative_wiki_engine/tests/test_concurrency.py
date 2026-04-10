import threading
import shutil
import tempfile
from wiki_engine import WikiEngine

def get_engine():
    tmp = tempfile.mkdtemp()
    engine = WikiEngine(tmp)
    return engine, tmp

def test_concurrent_updates():
    """
    Simulates many users attempting to update the same page.
    Only one should succeed per version increment.
    """
    engine, tmp = get_engine()
    try:
        path = "race_page"
        engine.create_page(path, "init", "admin")
        
        num_threads = 20
        results = [None] * num_threads
        
        def worker(tid):
            # Every thread tries to update from version 1 to 2
            success = engine.update_page(path, f"from_{tid}", f"u{tid}", expected_version=1)
            results[tid] = success
            
        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        # Exactly one thread should have succeeded
        assert sum(1 for r in results if r is True) == 1
        
        # Final version should be 2
        _, version = engine.get_page(path)
        assert version == 2
    finally:
        shutil.rmtree(tmp)

def test_massive_history_concurrency():
    """
    Multiple users creating DIFFERENT pages simultaneously.
    Should handle global index/history locking correctly.
    """
    engine, tmp = get_engine()
    try:
        # Initial pages
        engine.create_page("home", "# Home\nWelcome to the wiki.", "system")
        
        num_pages = 50
        threads = []
        
        def worker(pid):
            engine.create_page(f"page_{pid}", f"Content for {pid}", "user")
            
        for i in range(num_pages):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        # All pages should exist
        for i in range(num_pages):
            content, _ = engine.get_page(f"page_{i}")
            assert content == f"Content for {i}"
            
        # Search should find them all
        results = engine.search("Content")
        assert len(results) >= num_pages
    finally:
        shutil.rmtree(tmp)
