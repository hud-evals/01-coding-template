# hermes-retry

## Overview

- Project name: hermes-retry
- Total lines of code: 57
- Number of source modules: 1
- Classes: 0
- Module-level functions: 1
- Module 'retry_utils' docstring: Retry utilities — jittered backoff for decorrelated retries.

Replaces fixed exponential backoff with jittered delays to prevent
thundering-herd retry spikes when multiple sessions hit the same
rate-limited provider concurrently.

## Natural Language Instructions

Before you start:
- Create and edit the solution under `/home/ubuntu/workspace` at the exact workspace-relative paths below.
- Workspace-relative paths for hidden-test imports: `agent/retry_utils.py`.
- Implement every symbol listed in `Required Tested Symbols`, including underscored/private helpers.
- Recreate any repo-internal helper behavior locally instead of trying to install private packages.

### Behavioral Requirements

1. Implement the function `jittered_backoff(attempt, base_delay, max_delay, jitter_ratio)`
   Compute a jittered exponential backoff delay.

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `def jittered_backoff(attempt: int, *, base_delay: float = 5.0, max_delay: float = 120.0, jitter_ratio: float = 0.5) -> float`

## Environment Configuration

### Python Version

Python 3.12

### Workspace

- Put the implementation under `/home/ubuntu/workspace` at the exact workspace-relative paths listed below.
- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.
- Hidden tests import the solution from: `agent/retry_utils.py`. A file at `pkg/mod.py` must resolve as `from pkg.mod import ...`.

### External Dependencies

No third-party runtime dependencies were detected from the source file.


## Project Directory Structure

```
workspace/
├── pyproject.toml
└── agent/
    └── retry_utils.py
```

## API Usage Guide

### 1. Module Import

```python
from agent.retry_utils import (
    jittered_backoff,
)
```

### 2. `jittered_backoff` Function

Compute a jittered exponential backoff delay.

Args:
    attempt: 1-based retry attempt number.
    base_delay: Base delay in seconds for attempt 1.
    max_delay: Maximum delay cap in seconds.
    jitter_ratio: Fraction of computed delay to use as random jitter
        range.  0.5 means jitter is uniform in [0, 0.5 * delay].

Returns:
    Delay in seconds: min(base * 2^(attempt-1), max_delay) + jitter.

The jitter decorrelates concurrent retries so multiple sessions
hitting the same provider don't all retry at the same instant.

```python
def jittered_backoff(attempt: int, *, base_delay: float = 5.0, max_delay: float = 120.0, jitter_ratio: float = 0.5) -> float:
```

**Parameters:**
- `attempt: int`
- `base_delay: float = 5.0`
- `max_delay: float = 120.0`
- `jitter_ratio: float = 0.5`

**Returns:** `float`


## Implementation Notes

The following behaviors are validated by the test suite:

### Note 1: test_backoff_is_exponential
Tests symbols: `jittered_backoff`

```python
def test_backoff_is_exponential():
    """Base delay should double each attempt (before jitter)."""
    for attempt in (1, 2, 3, 4):
        delays = [jittered_backoff(attempt, base_delay=5.0, max_delay=120.0, jitter_ratio=0.0) for _ in range(100)]
        expected = min(5.0 * (2 ** (attempt - 1)), 120.0)
        mean = sum(delays) / len(delays)
        assert abs(mean - expected) < 0.01, f"attempt {attempt}: expected {expected}, got {mean}"
```

### Note 2: test_backoff_respects_max_delay
Tests symbols: `jittered_backoff`

```python
def test_backoff_respects_max_delay():
    """Even with high attempt numbers, delay should not exceed max_delay."""
    for attempt in (10, 20, 100):
        delay = jittered_backoff(attempt, base_delay=5.0, max_delay=60.0, jitter_ratio=0.0)
        assert delay <= 60.0, f"attempt {attempt}: delay {delay} exceeds max 60s"
```

### Note 3: test_backoff_adds_jitter
Tests symbols: `jittered_backoff`

```python
def test_backoff_adds_jitter():
    """With jitter enabled, delays should vary across calls."""
    delays = [jittered_backoff(1, base_delay=10.0, max_delay=120.0, jitter_ratio=0.5) for _ in range(50)]
    assert min(delays) != max(delays), "jitter should produce varying delays"
    assert all(d >= 10.0 for d in delays), "jittered delay should be >= base delay"
    assert all(d <= 15.0 for d in delays), "jittered delay should be bounded"
```

### Note 4: test_backoff_attempt_1_is_base
Tests symbols: `jittered_backoff`

```python
def test_backoff_attempt_1_is_base():
    """First attempt delay should equal base_delay (with no jitter)."""
    delay = jittered_backoff(1, base_delay=3.0, max_delay=120.0, jitter_ratio=0.0)
    assert delay == 3.0
```

### Note 5: test_backoff_with_zero_base_delay_returns_max
Tests symbols: `jittered_backoff`

```python
def test_backoff_with_zero_base_delay_returns_max():
    """base_delay=0 should return max_delay (guard against busy-wait)."""
    delay = jittered_backoff(1, base_delay=0.0, max_delay=60.0, jitter_ratio=0.0)
    assert delay == 60.0
```

### Note 6: test_backoff_with_extreme_attempt_returns_max
Tests symbols: `jittered_backoff`

```python
def test_backoff_with_extreme_attempt_returns_max():
    """Very large attempt numbers should not overflow and should return max_delay."""
    delay = jittered_backoff(999, base_delay=5.0, max_delay=120.0, jitter_ratio=0.0)
    assert delay == 120.0
```

### Note 7: test_backoff_negative_attempt_treated_as_one
Tests symbols: `jittered_backoff`

```python
def test_backoff_negative_attempt_treated_as_one():
    """Negative attempt should not crash and behaves like attempt=1."""
    delay = jittered_backoff(-5, base_delay=10.0, max_delay=120.0, jitter_ratio=0.0)
    assert delay == 10.0
```

### Note 8: test_backoff_thread_safety
Tests symbols: `jittered_backoff`

```python
def test_backoff_thread_safety():
    """Concurrent calls should generally produce different delays."""
    results = []
    barrier = threading.Barrier(8)

    def _call_backoff():
        barrier.wait()
        results.append(jittered_backoff(1, base_delay=10.0, max_delay=120.0, jitter_ratio=0.5))

    threads = [threading.Thread(target=_call_backoff) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert len(results) == 8
    unique = len(set(results))
    assert unique >= 6, f"Expected mostly unique delays, got {unique}/8 unique"
```

### Note 9: test_backoff_uses_locked_tick_for_seed
Tests symbols: `jittered_backoff`

```python
def test_backoff_uses_locked_tick_for_seed(monkeypatch):
    """Seed derivation should use per-call tick captured under lock."""
    import time

    monkeypatch.setattr(retry_utils, "_jitter_counter", 0)

    recorded_seeds = []

    class _RecordingRandom:
        def __init__(self, seed):
            recorded_seeds.append(seed)

        def uniform(self, a, b):
            return 0.0

    monkeypatch.setattr(retry_utils.random, "Random", _RecordingRandom)

    fixed_time_ns = 123456789

    def _time_ns_wait_for_two_ticks():
```
