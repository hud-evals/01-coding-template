import threading
from lockfree.atomic import AtomicInteger, AtomicReference

def test_atomic_integer_basic():
    a = AtomicInteger(10)
    assert a.get() == 10
    a.set(42)
    assert a.get() == 42
    assert a.increment() == 43
    assert a.get() == 43
    assert a.decrement() == 42
    assert a.fetch_and_add(5) == 42
    assert a.get() == 47

def test_atomic_integer_cas():
    a = AtomicInteger(0)
    assert a.cas(0, 1) is True
    assert a.get() == 1
    assert a.cas(0, 2) is False
    assert a.get() == 1
    assert a.cas(1, 99) is True
    assert a.get() == 99

def test_atomic_reference_basic():
    r = AtomicReference(None)
    assert r.get() is None
    r.set("hello")
    assert r.get() == "hello"
    
    A = object()
    B = object()
    r.set(A)
    assert r.cas(A, B) is True
    assert r.get() is B
    assert r.cas(A, B) is False

def test_atomic_concurrent_increment():
    a = AtomicInteger(0)
    def worker():
        for _ in range(100):
            a.increment()
            
    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    assert a.get() == 5000
