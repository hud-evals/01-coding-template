from lockfree.atomic import AtomicInteger, AtomicReference, EMPTY, DELETED, RESIZING
from lockfree.node import Slot, ResizeMarker
from lockfree.utils import fibonacci_hash, probe_sequence, next_power_of_two, compute_load_factor
import time

class LockFreeHashMap:
    """
    A lock-free concurrent hashmap using open addressing with quadratic probing.

    Design principles:
    - All slot mutations go through CAS operations on AtomicReference objects.
    - Resize is cooperative: threads help migrate when they encounter a ResizeMarker.
    - Keys are immutable once written to a slot.
    - Deletion uses tombstones (DELETED sentinel) in the value field.
    """
    def __init__(self, initial_capacity: int = 16, load_factor_threshold: float = 0.6):
        cap = next_power_of_two(initial_capacity)
        self._load_factor_threshold = load_factor_threshold
        
        self._count = AtomicInteger(0)
        self._capacity = AtomicInteger(cap)
        self._resize_in_progress = AtomicInteger(0) # 0: idle, 1: busy
        
        table = [Slot() for _ in range(cap)]
        self._table_ref = AtomicReference(table)
        self._next_table_ref = AtomicReference(None)

    def _get_table(self):
        return self._table_ref.get()

    def put(self, key, value) -> object:
        if key in (EMPTY, DELETED, RESIZING) or isinstance(key, ResizeMarker):
            raise ValueError("Invalid key")
            
        while True:
            table = self._get_table()
            cap = len(table)
            h = fibonacci_hash(hash(key), cap)
            
            for idx in probe_sequence(h, cap):
                slot = table[idx]
                s_key = slot.key.get()
                
                if s_key is EMPTY:
                    if slot.key.cas(EMPTY, key):
                        # Set value
                        while True:
                            old_v = slot.value.get()
                            if isinstance(old_v, ResizeMarker):
                                # Help migrate this slot
                                self._migrate_slot_to_new(key, old_v.old_value)
                                break # Retry from outer loop
                            if slot.value.cas(old_v, value):
                                self._count.increment()
                                if compute_load_factor(self.size(), cap) >= self._load_factor_threshold:
                                    self._resize()
                                return EMPTY
                        continue # Re-read table and retry
                    s_key = slot.key.get()

                if s_key == key:
                    while True:
                        old_v = slot.value.get()
                        if isinstance(old_v, ResizeMarker):
                            self._migrate_slot_to_new(key, old_v.old_value)
                            break
                        if slot.value.cas(old_v, value):
                            if old_v is DELETED:
                                self._count.increment()
                                return DELETED
                            return old_v
                    continue

                continue
            
            # Table potentially full or in flux
            self._resize()

    def get(self, key, default=None) -> object:
        while True:
            table = self._get_table()
            cap = len(table)
            h = fibonacci_hash(hash(key), cap)
            
            for idx in probe_sequence(h, cap):
                slot = table[idx]
                s_key = slot.key.get()
                
                if s_key is EMPTY:
                    return default
                
                if s_key == key:
                    val = slot.value.get()
                    if isinstance(val, ResizeMarker):
                        self._migrate_slot_to_new(key, val.old_value)
                        break # Retry from top level
                    if val is DELETED:
                        return default
                    return val
            else:
                return default

    def delete(self, key) -> object:
        while True:
            table = self._get_table()
            cap = len(table)
            h = fibonacci_hash(hash(key), cap)
            
            for idx in probe_sequence(h, cap):
                slot = table[idx]
                s_key = slot.key.get()
                
                if s_key is EMPTY:
                    return EMPTY
                
                if s_key == key:
                    while True:
                        old_v = slot.value.get()
                        if isinstance(old_v, ResizeMarker):
                            self._migrate_slot_to_new(key, old_v.old_value)
                            break
                        if old_v is DELETED:
                            return EMPTY
                        if slot.value.cas(old_v, DELETED):
                            self._count.decrement()
                            return old_v
                    continue
            else:
                return EMPTY

    def _migrate_slot_to_new(self, key, value):
        new_table = self._next_table_ref.get()
        if new_table and value not in (EMPTY, DELETED):
            self._insert_into_new(new_table, key, value)

    def _resize(self) -> None:
        # Avoid redundant work
        if self._resize_in_progress.get() == 1:
            # Already in progress, just wait/help
            return

        if not self._resize_in_progress.cas(0, 1):
            return

        try:
            old_table = self._table_ref.get()
            old_cap = len(old_table)
            new_cap = old_cap * 2
            new_table = [Slot() for _ in range(new_cap)]
            self._next_table_ref.set(new_table)
            
            for old_idx in range(old_cap):
                slot = old_table[old_idx]
                while True:
                    s_key = slot.key.get()
                    s_val = slot.value.get()
                    if isinstance(s_val, ResizeMarker):
                        break
                    if slot.value.cas(s_val, ResizeMarker(s_val)):
                        if s_key is not EMPTY and s_val not in (DELETED, EMPTY):
                            self._insert_into_new(new_table, s_key, s_val)
                        break
            
            self._capacity.set(new_cap)
            self._table_ref.set(new_table)
            self._next_table_ref.set(None)
        finally:
            self._resize_in_progress.set(0)

    def _insert_into_new(self, table, key, value):
        cap = len(table)
        h = fibonacci_hash(hash(key), cap)
        for idx in probe_sequence(h, cap):
            slot = table[idx]
            sk = slot.key.get()
            if sk is EMPTY:
                if slot.key.cas(EMPTY, key):
                    slot.value.set(value)
                    return True
                sk = slot.key.get()
            if sk == key:
                # Key already there (maybe another thread helped)
                return True
        return False

    def size(self) -> int: return self._count.get()
    def capacity(self) -> int: return self._capacity.get()
    def load_factor(self) -> float: return compute_load_factor(self.size(), self.capacity())

    def items(self) -> list:
        res = []
        table = self._table_ref.get()
        for slot in table:
            k = slot.key.get()
            v = slot.value.get()
            if k not in (EMPTY, DELETED) and v not in (EMPTY, DELETED) and not isinstance(v, ResizeMarker):
                res.append((k, v))
        return res

    def keys(self) -> list: return [k for k, v in self.items()]
    def values(self) -> list: return [v for k, v in self.items()]
    def clear(self) -> None:
        self._table_ref.set([Slot() for _ in range(self.capacity())])
        self._count.set(0)

    def __len__(self) -> int: return self.size()
    def __contains__(self, key) -> bool: return self.get(key, EMPTY) is not EMPTY
    def __getitem__(self, key) -> object:
        val = self.get(key, EMPTY)
        if val is EMPTY: raise KeyError(key)
        return val
    def __setitem__(self, key, value) -> None: self.put(key, value)
    def __delitem__(self, key) -> None:
        if self.delete(key) is EMPTY: raise KeyError(key)

    def __repr__(self) -> str:
        return f"LockFreeHashMap(size={self.size()}, capacity={self.capacity()}, load={self.load_factor():.2f})"
