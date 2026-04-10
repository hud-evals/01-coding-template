import threading
from lockfree import LockFreeHashMap

def test_resize_triggered(small_hmap):
    # capacity=4, threshold=0.5
    # Should resize after 2nd entry (2/4 = 0.5)
    small_hmap.put("k1", "v1")
    old_cap = small_hmap.capacity()
    
    small_hmap.put("k2", "v2")
    small_hmap.put("k3", "v3")
    
    new_cap = small_hmap.capacity()
    assert new_cap > old_cap
    assert small_hmap.get("k1") == "v1"
    assert small_hmap.get("k2") == "v2"
    assert small_hmap.get("k3") == "v3"
    assert small_hmap.size() == 3

def test_concurrent_resize():
    # capacity=8, threshold=0.5
    # triggers after 4 entries
    hmap = LockFreeHashMap(initial_capacity=8, load_factor_threshold=0.5)
    
    num_threads = 16
    keys_per_thread = 50
    threads = []
    
    def worker(tid):
        for i in range(keys_per_thread):
            hmap.put(f"t{tid}_k{i}", f"val_{i}")
            
    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads: t.join()
    
    expected_total = num_threads * keys_per_thread # 800
    assert hmap.size() == expected_total
    
    # Verify a sample
    for tid in range(num_threads):
        assert hmap.get(f"t{tid}_k0") == "val_0"
        
    # Check capacity is power of two
    cap = hmap.capacity()
    assert (cap & (cap - 1)) == 0
    assert cap >= expected_total
