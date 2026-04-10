import pytest
from lockfree import EMPTY

def test_put_and_get(hmap):
    assert hmap.put("a", 1) is EMPTY
    assert hmap.get("a") == 1
    assert hmap.put("a", 2) == 1
    assert hmap.get("a") == 2
    assert hmap.get("missing", default="x") == "x"

def test_delete(hmap):
    hmap.put("k", "v")
    assert hmap.delete("k") == "v"
    assert hmap.size() == 0
    assert hmap.get("k") is None
    assert hmap.delete("k") is EMPTY

def test_contains_and_dunder(hmap):
    hmap.put("key", "val")
    assert "key" in hmap
    assert "missing" not in hmap
    assert hmap["key"] == "val"
    with pytest.raises(KeyError):
        _ = hmap["missing"]
    
    del hmap["key"]
    assert "key" not in hmap
    with pytest.raises(KeyError):
        del hmap["missing"]
    
    assert len(hmap) == 0

def test_keys_values_items(hmap):
    data = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}
    for k, v in data.items():
        hmap.put(k, v)
        
    assert set(hmap.keys()) == set(data.keys())
    assert set(hmap.values()) == set(data.values())
    assert set(hmap.items()) == set(data.items())

def test_clear(hmap):
    for i in range(10):
        hmap.put(i, i)
    assert hmap.size() == 10
    hmap.clear()
    assert hmap.size() == 0
    assert hmap.get(0) is None
    hmap.put(0, "new")
    assert hmap.get(0) == "new"
