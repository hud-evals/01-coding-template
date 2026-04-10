import math

GOLDEN_RATIO = 0x9e3779b9  # 2^32 / phi, truncated

def fibonacci_hash(key_hash: int, table_size: int) -> int:
    """
    Use Fibonacci hashing (Knuth's multiplicative method) for better distribution.
    """
    return ((key_hash * GOLDEN_RATIO) & 0xFFFFFFFF) % table_size

def next_power_of_two(n: int) -> int:
    """
    Return the smallest power of two >= n.
    """
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()

def probe_sequence(start: int, table_size: int):
    """
    Generator that yields slot indices using quadratic probing.
    """
    for i in range(table_size):
        yield (start + i*i) % table_size

def is_prime(n: int) -> bool:
    """
    Trial division primality test.
    """
    if n < 2:
        return False
    for i in range(2, int(math.sqrt(n)) + 1):
        if n % i == 0:
            return False
    return True

def compute_load_factor(count: int, capacity: int) -> float:
    """
    Return count / capacity.
    """
    if capacity == 0:
        return 0.0
    return count / capacity
