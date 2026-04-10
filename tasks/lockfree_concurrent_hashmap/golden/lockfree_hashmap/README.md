# Lock-Free Concurrent HashMap

## Architecture Overview
This implementation uses a lock-free open-addressing hashmap with quadratic probing. Linearizability is achieved through the use of atomic compare-and-swap (CAS) operations on each slot's key and value fields.

## CAS Implementation
Atomic operations in this Python codebase are implemented using `ctypes` to invoke native CPU instructions. On Windows, it utilizes the `InterlockedCompareExchange64` routine from `kernel32.dll`. On Linux (x86_64), it dynamically loads a machine-code stub into executable memory via `mmap` to perform the `lock cmpxchg` instruction. This ensures that the check-and-set operation is truly atomic across multiple hardware threads, bypassing Python's high-level object overhead while respecting the Global Interpreter Lock (GIL) where applicable.

## Linearizability
- `put(key, value)`: Linearizes at the successful CAS of `slot.value`.
- `get(key)`: Linearizes at the read of `slot.value`.
- `delete(key)`: Linearizes at the successful CAS of `slot.value` to the `DELETED` tombstone.

## Known Limitations
- While lock-free, performance in CPython is still subject to the GIL for bytecode execution.
- Memory consumption is slightly higher due to the use of `ctypes` wrappers for every integer and reference.
- The ABA problem is mitigated by the monotonic state transitions of the slots and the fact that keys are never reused within the same table instance life-cycle for different values.

## How to run the tests
```bash
pytest tests/
```
