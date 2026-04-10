import pytest
from lockfree import LockFreeHashMap

@pytest.fixture
def hmap():
    """Fresh hashmap with default capacity."""
    return LockFreeHashMap(initial_capacity=16)

@pytest.fixture
def small_hmap():
    """Small hashmap to trigger resize quickly."""
    return LockFreeHashMap(initial_capacity=4, load_factor_threshold=0.5)

@pytest.fixture
def large_hmap():
    """Pre-populated hashmap with 1000 entries."""
    m = LockFreeHashMap(initial_capacity=2048)
    for i in range(1000):
        m.put(f"key_{i}", f"val_{i}")
    return m

def concurrent_put(hmap, pairs, results, idx):
    """Worker function: put all (key, value) pairs into hmap, store results[idx]."""
    results[idx] = {}
    for k, v in pairs:
        results[idx][k] = hmap.put(k, v)
