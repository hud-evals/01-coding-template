# Lock-Free Concurrent HashMap

## Task Overview

You are a systems engineer. Your task is to implement a **lock-free concurrent hashmap** in pure Python from scratch in an empty workspace.

The hashmap must support concurrent reads and writes from multiple threads simultaneously — without using any mutex, `threading.Lock`, `threading.RLock`, `threading.Semaphore`, or any other explicit locking primitive. Correctness under concurrency must be achieved through **atomic compare-and-swap (CAS) operations** only.

This is a pure algorithmic systems task. No web frameworks, no databases, no external services.

---

## Absolute Requirements

- **No locks allowed** — `threading.Lock`, `RLock`, `Semaphore`, `Condition`, `Event`, `Barrier` are all forbidden. The grader scans your source code and fails immediately if any of these appear.
- **No `queue.Queue`** — it uses internal locks.
- **0→1 task** — empty workspace, you write everything.
- **Minimum 1,000 lines of code** across all files.
- **All 16 tests must pass** with the exact function names specified.
- **CAS must be real** — implement it via `ctypes` atomics or a thin wrapper; do not simulate with locks.

---

## Project Structure

Create this exact layout:

```
lockfree_hashmap/
├── README.md
├── requirements.txt
├── lockfree/
│   ├── __init__.py
│   ├── atomic.py
│   ├── hashmap.py
│   ├── node.py
│   └── utils.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_atomic.py
    ├── test_basic.py
    ├── test_concurrent.py
    └── test_resize.py
```

---

## Detailed Implementation Guide

### `requirements.txt`

```
pytest==8.2.0
pytest-timeout==2.3.1
```

No other dependencies allowed. The implementation must use only Python standard library modules.

---

### `README.md`

Write a technical README covering:
- Architecture overview (open-addressing vs chaining, chosen approach and why)
- CAS implementation details (how atomicity is achieved in CPython)
- Linearizability argument (brief — why each operation appears atomic to other threads)
- Known limitations (GIL interaction, ABA problem handling)
- How to run the tests

Minimum 200 words.

---

### `lockfree/atomic.py`

Implement atomic primitives. This is the foundation of the entire hashmap.

**Class `AtomicInteger`:**

```python
class AtomicInteger:
    """
    A thread-safe integer supporting atomic compare-and-swap.
    Uses ctypes to bypass Python object reference counting
    and achieve atomic reads/writes on CPython.
    """
```

Methods:

`__init__(self, value: int = 0)`
- Store value internally. Use `ctypes.c_long` for the underlying storage to allow atomic manipulation.

`get(self) -> int`
- Return current value atomically.

`set(self, value: int) -> None`
- Set value atomically.

`compare_and_swap(self, expected: int, new_value: int) -> bool`
- If current value equals `expected`, set it to `new_value` and return `True`.
- Otherwise return `False`.
- This is the **core primitive** — implement it so that under CPython's GIL, the check-and-set is not interleaved with other threads. Use `ctypes` integer manipulation.
- Signature: `cas(self, expected, new_value) -> bool` (alias: `compare_and_swap`)

`increment(self) -> int`
- Atomically increment and return the **new** value. Use a CAS loop.

`decrement(self) -> int`
- Atomically decrement and return the **new** value. Use a CAS loop.

`fetch_and_add(self, delta: int) -> int`
- Atomically add `delta`, return the **old** value. Use a CAS loop.

---

**Class `AtomicReference`:**

```python
class AtomicReference:
    """
    A thread-safe object reference supporting atomic compare-and-swap.
    Stores Python object references; CAS uses object identity (is), not equality (==).
    """
```

Methods:

`__init__(self, value=None)`

`get(self) -> object`
- Return current reference atomically.

`set(self, value) -> None`
- Set reference atomically.

`compare_and_swap(self, expected, new_value) -> bool`
- If current reference **is** `expected` (identity check), swap to `new_value` and return `True`.
- Otherwise return `False`.
- Alias: `cas(self, expected, new_value)`

---

**Sentinel values (module-level constants):**

```python
EMPTY    = object()   # slot has never been written
DELETED  = object()   # slot was written then deleted (tombstone)
RESIZING = object()   # slot is being migrated during resize
```

These must be unique singleton objects. Use `object()` — never `None`, `0`, or strings.

---

### `lockfree/node.py`

Define the internal slot structure used by the hashmap.

**Class `Slot`:**

```python
class Slot:
    """
    A single slot in the open-addressing table.
    Both key and value are AtomicReferences so they can be
    swapped via CAS without a lock.
    """
    __slots__ = ('key', 'value')

    def __init__(self, key=EMPTY, value=EMPTY):
        self.key   = AtomicReference(key)
        self.value = AtomicReference(value)
```

No additional methods needed on `Slot`. The hashmap operates on `slot.key` and `slot.value` directly via their `AtomicReference` methods.

---

**Class `ResizeMarker`:**

```python
class ResizeMarker:
    """
    Sentinel object placed in a slot's value during table migration.
    Distinguishes 'slot is being moved' from 'slot holds DELETED'.
    """
    def __init__(self, old_value):
        self.old_value = old_value
```

---

### `lockfree/utils.py`

Implement utility functions.

**`fibonacci_hash(key_hash: int, table_size: int) -> int`**

Use Fibonacci hashing (Knuth's multiplicative method) for better distribution:

```python
GOLDEN_RATIO = 0x9e3779b9  # 2^32 / phi, truncated

def fibonacci_hash(key_hash: int, table_size: int) -> int:
    return ((key_hash * GOLDEN_RATIO) & 0xFFFFFFFF) % table_size
```

**`next_power_of_two(n: int) -> int`**

Return the smallest power of two ≥ `n`. Handle `n <= 1` → return 1.

**`probe_sequence(start: int, table_size: int)`**

Generator that yields slot indices using **quadratic probing**:

```
index = (start + i*i) % table_size   for i = 0, 1, 2, ...
```

Stop after `table_size` steps (full table scan). Must be a generator function (use `yield`).

**`is_prime(n: int) -> bool`**

Trial division primality test. Used for table size validation in tests.

**`compute_load_factor(count: int, capacity: int) -> float`**

Return `count / capacity`. Return `0.0` if capacity is 0.

---

### `lockfree/hashmap.py`

This is the main implementation. It must be the largest single file (≥ 600 lines including docstrings).

**Class `LockFreeHashMap`:**

```python
class LockFreeHashMap:
    """
    A lock-free concurrent hashmap using open addressing with quadratic probing.

    Design principles:
    - All slot mutations go through CAS operations on AtomicReference objects.
    - Resize is cooperative: any thread that detects overload can initiate it,
      and all threads help migrate slots before proceeding.
    - Keys are immutable once written to a slot (key CAS never changes an
      existing key — it only claims an EMPTY slot).
    - Deletion uses tombstones (DELETED sentinel) in the value field,
      never in the key field, preserving probe chain integrity.
    - The ABA problem is mitigated by never reusing a slot for a different key.
    """
```

**Constructor:**

```python
def __init__(self, initial_capacity: int = 16, load_factor_threshold: float = 0.6):
```

- Round `initial_capacity` up to next power of two.
- `load_factor_threshold`: trigger resize when `count / capacity >= threshold`.
- Create an internal `_table: list[Slot]` of length `capacity`, each `Slot` initialized with `EMPTY` key and `EMPTY` value.
- `_count = AtomicInteger(0)` — number of live (non-deleted) entries.
- `_capacity = AtomicInteger(capacity)` — current table size.
- `_resize_in_progress = AtomicInteger(0)` — flag: 0 = idle, 1 = resizing.
- `_table_ref = AtomicReference(table)` — atomic reference to current table (swapped on resize).

---

**`put(self, key, value) -> object`**

Insert or update a key-value pair. Return the **previous value** (or `EMPTY` if new).

Algorithm:
1. Hash the key: `h = fibonacci_hash(hash(key), self._capacity.get())`.
2. Probe the table using `probe_sequence(h, capacity)`.
3. For each slot in the probe sequence:
   a. Read `slot_key = slot.key.get()`.
   b. If `slot_key is EMPTY`: attempt `slot.key.cas(EMPTY, key)`.
      - If CAS succeeds: this thread owns the slot. Set `slot.value` to `value`. Increment `_count`. Check load factor → trigger resize if needed. Return `EMPTY`.
      - If CAS fails: another thread claimed this slot. Re-read `slot_key` and continue (the slot may now hold our key or a different key).
   c. If `slot_key == key` (equality, not identity): this is our key.
      - Read old value: `old = slot.value.get()`.
      - If `old is DELETED`: the key was deleted. CAS `slot.value` from `DELETED` to `new_value`. If success, increment `_count`, return `DELETED`. If fail, retry.
      - Otherwise: CAS `slot.value` from `old` to `new_value`. If fail, retry from step c.
   d. If `slot_key is DELETED` (key tombstone — should not happen per design, but handle gracefully): skip.
   e. Otherwise: collision, continue probing.
4. If probe sequence exhausted without placing: the table is full (should not happen if resize works). Raise `RuntimeError("HashMap is full — resize failed")`.

---

**`get(self, key, default=None) -> object`**

Look up a key. Return its value or `default` if not found.

Algorithm:
1. Hash and probe as in `put`.
2. For each slot:
   a. `slot_key = slot.key.get()`
   b. If `slot_key is EMPTY`: key definitely not present → return `default`.
   c. If `slot_key == key`: read `slot.value.get()`.
      - If `DELETED` or `RESIZING`: return `default`.
      - Otherwise: return value.
   d. Otherwise: continue probing.
3. Return `default` if exhausted.

---

**`delete(self, key) -> object`**

Remove a key. Return the old value, or `EMPTY` if key not found.

Algorithm:
1. Locate the slot (same probe logic as `get`).
2. When found: CAS `slot.value` from current value to `DELETED`.
   - If CAS succeeds: decrement `_count`. Return old value.
   - If CAS fails (concurrent writer): re-read and retry.
3. If not found: return `EMPTY`.

---

**`contains(self, key) -> bool`**

Return `True` if key exists and is not deleted. Equivalent to `get(key, EMPTY) is not EMPTY`.

---

**`size(self) -> int`**

Return `_count.get()`. This is the number of live (non-deleted) entries.

---

**`capacity(self) -> int`**

Return `_capacity.get()`. Current table size (number of slots).

---

**`load_factor(self) -> float`**

Return `size() / capacity()`.

---

**`keys(self) -> list`**

Return a **snapshot** list of all live keys at the moment of the call. Not guaranteed to be consistent under concurrent modification — document this.

Algorithm: scan the current table linearly. For each slot where `key is not EMPTY and key is not DELETED and value is not DELETED and value is not EMPTY`: add key to list.

---

**`values(self) -> list`**

Same as `keys()` but return values.

---

**`items(self) -> list`**

Return a snapshot list of `(key, value)` tuples for all live entries.

---

**`clear(self) -> None`**

Replace the internal table with a fresh one of the same capacity. Reset `_count` to 0. Use `_table_ref.set(new_table)` atomically.

---

**`_resize(self) -> None`**

This is the most complex method. Implement cooperative resize.

```
Algorithm:
1. CAS _resize_in_progress from 0 → 1.
   - If CAS fails: another thread is resizing. Spin-wait until _resize_in_progress == 0, then return.
2. Compute new_capacity = next_power_of_two(current_capacity * 2).
3. Create new_table = [Slot() for _ in range(new_capacity)].
4. Migrate all live slots from old_table to new_table:
   For each slot in old_table:
     a. Read key = slot.key.get(). Skip if EMPTY.
     b. Read val = slot.value.get(). Skip if DELETED or RESIZING.
     c. Mark the old slot as migrated: CAS slot.value from val → ResizeMarker(val).
        If CAS fails, re-read val and retry step b-c.
     d. Insert (key, val) into new_table using the same open-addressing probe logic
        (but directly — no recursion into put() to avoid triggering another resize).
5. Update _capacity to new_capacity.
6. Atomically swap _table_ref to new_table.
7. CAS _resize_in_progress from 1 → 0.
```

Any thread that encounters a `ResizeMarker` in a slot's value during `put` or `get` must **help complete the migration**: it should re-insert the wrapped value into the new table before proceeding with its own operation.

---

**`__len__(self) -> int`**

Return `self.size()`.

---

**`__contains__(self, key) -> bool`**

Return `self.contains(key)`.

---

**`__getitem__(self, key) -> object`**

Return `self.get(key, default=EMPTY)`. Raise `KeyError(key)` if result is `EMPTY`.

---

**`__setitem__(self, key, value) -> None`**

Call `self.put(key, value)`.

---

**`__delitem__(self, key) -> None`**

Call `self.delete(key)`. Raise `KeyError(key)` if result is `EMPTY`.

---

**`__repr__(self) -> str`**

Return something like `LockFreeHashMap(size=3, capacity=16, load=0.19)`.

---

### `lockfree/__init__.py`

Export the public API:

```python
from lockfree.hashmap import LockFreeHashMap
from lockfree.atomic import AtomicInteger, AtomicReference, EMPTY, DELETED
from lockfree.utils import fibonacci_hash, probe_sequence, next_power_of_two

__all__ = [
    "LockFreeHashMap",
    "AtomicInteger",
    "AtomicReference",
    "EMPTY",
    "DELETED",
    "fibonacci_hash",
    "probe_sequence",
    "next_power_of_two",
]
__version__ = "1.0.0"
```

---

### `tests/conftest.py`

Define these fixtures:

```python
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
```

Also define a helper (not a fixture):

```python
def concurrent_put(hmap, pairs, results, idx):
    """Worker function: put all (key, value) pairs into hmap, store old values in results[idx]."""
    results[idx] = {}
    for k, v in pairs:
        results[idx][k] = hmap.put(k, v)
```

---

### `tests/test_atomic.py`

Implement exactly these **4 test functions**:

**`test_atomic_integer_basic`**
- Create `AtomicInteger(10)`.
- Assert `get() == 10`.
- `set(42)` → assert `get() == 42`.
- `increment()` → assert returns 43, `get() == 43`.
- `decrement()` → assert returns 42.
- `fetch_and_add(5)` → assert returns 42 (old value), `get() == 47`.

**`test_atomic_integer_cas`**
- Create `AtomicInteger(0)`.
- `cas(0, 1)` → assert `True`, `get() == 1`.
- `cas(0, 2)` → assert `False` (expected 0, actual 1), `get() == 1`.
- `cas(1, 99)` → assert `True`, `get() == 99`.

**`test_atomic_reference_basic`**
- Create `AtomicReference(None)`.
- `get()` returns `None`.
- `set("hello")` → `get() == "hello"`.
- Create sentinel `A = object()`, `B = object()`.
- `set(A)` → `cas(A, B)` returns `True`, `get() is B`.
- `cas(A, B)` returns `False` (A is no longer current).

**`test_atomic_concurrent_increment`**
- Create `AtomicInteger(0)`.
- Launch 50 threads, each calling `increment()` 100 times.
- Join all threads.
- Assert `get() == 5000`.
- **No locks may be used in this test.**

---

### `tests/test_basic.py`

Implement exactly these **5 test functions**:

**`test_put_and_get`**
- `hmap.put("a", 1)` → returns `EMPTY` (new key).
- `hmap.get("a")` → returns `1`.
- `hmap.put("a", 2)` → returns `1` (old value).
- `hmap.get("a")` → returns `2`.
- `hmap.get("missing", default="x")` → returns `"x"`.

**`test_delete`**
- Insert `"k" → "v"`.
- `hmap.delete("k")` → returns `"v"`, `hmap.size() == 0`.
- `hmap.get("k")` → returns `None`.
- `hmap.delete("k")` → returns `EMPTY` (already gone).

**`test_contains_and_dunder`**
- Insert several keys. Assert `"existing" in hmap` is `True`.
- Assert `"missing" in hmap` is `False`.
- `hmap["key"]` returns value.
- `hmap["missing"]` raises `KeyError`.
- `del hmap["key"]` removes it.
- `del hmap["missing"]` raises `KeyError`.
- `len(hmap)` returns correct count.

**`test_keys_values_items`**
- Insert 5 key-value pairs.
- `keys()` returns list containing all 5 keys (order not guaranteed).
- `values()` returns list containing all 5 values.
- `items()` returns list of 5 `(key, value)` tuples.
- Assert set equality (not order).

**`test_clear`**
- Insert 10 entries.
- `clear()` → `size() == 0`, `len(hmap) == 0`.
- `get("any_key")` → `None`.
- Capacity unchanged.
- Can insert again after clear.

---

### `tests/test_concurrent.py`

Implement exactly these **5 test functions**. Each must use `threading.Thread` only — no locks.

**`test_concurrent_put_no_lost_writes`**
- Launch 32 threads. Each thread inserts 200 unique keys (e.g. `f"t{thread_id}_k{i}"`).
- Total keys: 6,400. Join all threads.
- Assert `hmap.size() == 6400`.
- Assert every key is retrievable with its correct value.

**`test_concurrent_mixed_operations`**
- Pre-insert keys `0..499`.
- Launch 16 threads. Each thread:
  - Puts 50 new unique keys.
  - Gets 50 existing keys and asserts values are non-None.
  - Deletes 10 pre-inserted keys (disjoint per thread).
- Join all threads.
- Assert no `KeyError` or exception during the run.
- Assert `size() >= 0` (basic sanity).

**`test_concurrent_same_key_updates`**
- All 64 threads race to `put("shared_key", thread_id)` 10 times each.
- After joining: `get("shared_key")` must return **some** valid thread_id (not `EMPTY`, not `DELETED`).
- `size()` must equal exactly 1 (one live entry).

**`test_concurrent_delete_and_reinsert`**
- Insert keys `0..99`.
- Launch 20 threads. Each thread loops 50 times:
  - Pick a random key from `0..99`.
  - Either delete it or re-insert it with a new value.
- Join all threads.
- After completion: for every key that currently exists, assert `get(key)` is not `DELETED` and not `EMPTY`.
- Assert `size()` matches actual count of `items()`.

**`test_no_locks_in_source`**
- Use `inspect` and `ast` modules to parse all `.py` files in `lockfree/`.
- Assert none of these names appear as identifiers in the source:
  `threading.Lock`, `threading.RLock`, `threading.Semaphore`, `threading.Condition`, `threading.Event`, `threading.Barrier`, `queue.Queue`.
- This test must pass — it is the enforcement mechanism for the no-locks rule.

---

### `tests/test_resize.py`

Implement exactly these **2 test functions**:

**`test_resize_triggered`**
- Create `small_hmap` (capacity=4, threshold=0.5).
- Insert 3 entries → load factor > 0.5 → resize should trigger.
- Assert `capacity() > 4` (table grew).
- Assert all 3 inserted keys are still retrievable with correct values.
- Assert `size() == 3`.

**`test_concurrent_resize`**
- Create `LockFreeHashMap(initial_capacity=8, load_factor_threshold=0.5)`.
- Launch 16 threads, each inserting 50 unique keys.
- Total: 800 keys — far more than initial capacity, will trigger multiple resizes.
- Join all threads.
- Assert `size() == 800`.
- Assert every key is retrievable.
- Assert final `capacity()` is a power of two.
