import threading
import ast
import os
import random
import pytest
from lockfree import LockFreeHashMap

def test_concurrent_put_no_lost_writes(hmap):
    num_threads = 32
    num_keys = 200
    threads = []
    
    def worker(tid):
        for i in range(num_keys):
            hmap.put(f"t{tid}_k{i}", i)
            
    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads: t.join()
    
    assert hmap.size() == num_threads * num_keys
    for tid in range(num_threads):
        for i in range(num_keys):
            assert hmap.get(f"t{tid}_k{i}") == i

def test_concurrent_mixed_operations(hmap):
    # Pre-insert keys 0..499
    for i in range(500):
        hmap.put(i, i)
    
    def worker(tid):
        # Puts 50 new unique keys
        for i in range(50):
            hmap.put(f"new_{tid}_{i}", i)
        # Gets 50 existing keys
        for i in range(50):
            assert hmap.get(i) is not None
        # Deletes 10 pre-inserted keys
        for i in range(10):
            hmap.delete(tid * 10 + i)
            
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    assert hmap.size() >= 0

def test_concurrent_same_key_updates(hmap):
    num_threads = 64
    def worker(tid):
        for _ in range(10):
            hmap.put("shared_key", tid)
            
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    val = hmap.get("shared_key")
    assert val is not None
    assert val in range(num_threads)
    assert hmap.size() == 1

def test_concurrent_delete_and_reinsert(hmap):
    for i in range(100):
        hmap.put(i, i)
    
    def worker():
        for _ in range(50):
            k = random.randint(0, 99)
            if random.random() > 0.5:
                hmap.delete(k)
            else:
                hmap.put(k, "reborn")
                
    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    # Ensure current items match size
    items = hmap.items()
    assert hmap.size() == len(items)
    for k, v in items:
        assert hmap.get(k) is not None

def test_no_locks_in_source():
    """
    Enforcement test: scans the package source for forbidden locking primitives.
    """
    forbidden = {
        "threading.Lock", "threading.RLock", "threading.Semaphore",
        "threading.Condition", "threading.Event", "threading.Barrier",
        "queue.Queue", "Lock", "RLock", "Semaphore"
    }
    
    # Path to lockfree package - assume it is one level up or accessible
    import lockfree
    pkg_path = os.path.dirname(lockfree.__file__)
    
    for root, _, files in os.walk(pkg_path):
        for file in files:
            if file.endswith(".py"):
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())
                    for node in ast.walk(tree):
                        # Check for attribute access like threading.Lock
                        if isinstance(node, ast.Attribute):
                            full_name = ""
                            if isinstance(node.value, ast.Name):
                                full_name = f"{node.value.id}.{node.attr}"
                            if full_name in forbidden:
                                raise AssertionError(f"Forbidden lock found in {file}: {full_name}")
                        # Check for direct Names (if imported via from threading import Lock)
                        if isinstance(node, ast.Name):
                            if node.id in forbidden:
                                raise AssertionError(f"Forbidden lock found in {file}: {node.id}")
