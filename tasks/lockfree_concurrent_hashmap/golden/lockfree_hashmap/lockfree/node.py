from lockfree.atomic import AtomicReference, EMPTY

class Slot:
    """
    A single slot in the open-addressing table.
    Both key and value are AtomicReferences so they can be
    swapped via CAS without a lock.
    """
    __slots__ = ('key', 'value')

    def __init__(self, key=EMPTY, value=EMPTY):
        self.key = AtomicReference(key)
        self.value = AtomicReference(value)

class ResizeMarker:
    """
    Sentinel object placed in a slot's value during table migration.
    Distinguishes 'slot is being moved' from 'slot holds DELETED'.
    """
    def __init__(self, old_value):
        self.old_value = old_value
