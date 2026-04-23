# hermes_retry

## Overview

**hermes_retry** is a lightweight Python library providing retry utilities with jittered backoff mechanisms for decorrelated retries. The library consists of a single module, `retry_utils`, containing one module-level function that implements intelligent retry logic designed to mitigate thundering-herd problems in concurrent systems. With only 57 lines of code across a single source module, hermes_retry offers a minimal, focused implementation without class-based abstractions, making it suitable for direct functional integration into existing codebases.

The core functionality replaces naive fixed exponential backoff strategies with jittered delay calculations that decorrelate retry attempts across multiple concurrent sessions. This approach prevents synchronized retry spikes when multiple clients simultaneously encounter rate-limiting responses from the same upstream provider. By introducing randomized delays into the backoff sequence, hermes_retry reduces the probability of coordinated request clustering that would otherwise amplify load on already-constrained services.

The library's single exported function provides a straightforward interface for implementing resilient retry behavior in network-dependent applications, particularly those interacting with rate-limited APIs or services prone to transient failures. The decorrelated jitter strategy ensures that retry timing remains unpredictable across distributed callers, thereby improving overall system stability under concurrent load conditions.

## Natural Language Instructions

You are rebuilding a Python library called `hermes_retry` from scratch. The library provides retry utilities with jittered exponential backoff to prevent thundering-herd retry spikes.

### Implementation Constraints

- Create the file at `/home/ubuntu/workspace/agent/retry_utils.py` (create the `agent/` directory if it does not exist).
- The module must be importable as `from agent.retry_utils import jittered_backoff`.
- Implement exactly one module-level function: `jittered_backoff`.
- The function must use thread-safe randomization with a per-call seed derived from a monotonically incrementing counter and `time.time_ns()`.
- Do not use external dependencies beyond Python's standard library (`random`, `time`, `threading`).
- Preserve all function signatures exactly as specified; do not rename parameters or change defaults.
- Handle edge cases (zero base_delay, negative attempts, extreme attempt numbers) without crashing.

### Behavioral Requirements

1. **Function signature**: `jittered_backoff(attempt: int, *, base_delay: float = 5.0, max_delay: float = 120.0, jitter_ratio: float = 0.5) -> float` must exist at module level in `/home/ubuntu/workspace/agent/retry_utils.py`.

2. **Exponential backoff calculation**: The base delay (before jitter) for a given attempt must be computed as `base_delay * (2 ** (attempt - 1))`. For example:
   - attempt=1: base_delay * (2 ** 0) = base_delay * 1
   - attempt=2: base_delay * (2 ** 1) = base_delay * 2
   - attempt=3: base_delay * (2 ** 2) = base_delay * 4
   - attempt=4: base_delay * (2 ** 3) = base_delay * 8

3. **Max delay capping**: After computing the exponential backoff, the result must be capped at `max_delay`. The final base delay (before jitter) is `min(base_delay * (2 ** (attempt - 1)), max_delay)`.

4. **Jitter application**: After computing the capped base delay, jitter must be applied by selecting a random value uniformly distributed in the range `[base_delay_capped, base_delay_capped * (1 + jitter_ratio)]`. For example, if the capped base delay is 10.0 and jitter_ratio is 0.5, the jittered delay must be uniformly distributed in [10.0, 15.0].

5. **Zero jitter_ratio behavior**: When `jitter_ratio=0.0`, the function must return the capped base delay with no randomness. The range becomes `[base_delay_capped, base_delay_capped * (1 + 0.0)]` = `[base_delay_capped, base_delay_capped]`, which is a single value.

6. **Attempt 1 with no jitter**: When `attempt=1`, `base_delay=3.0`, `max_delay=120.0`, and `jitter_ratio=0.0`, the function must return exactly `3.0`.

7. **Zero base_delay guard**: When `base_delay=0.0`, the function must return `max_delay` (not 0.0). This prevents busy-wait loops. The exponential calculation would yield 0.0, but this must be treated as a special case that returns `max_delay` instead.

8. **Negative attempt handling**: When `attempt` is negative (e.g., `attempt=-5`), the function must treat it as if `attempt=1`. It must not crash and must return the same delay as `attempt=1` with the same other parameters.

9. **Extreme attempt numbers**: When `attempt` is very large (e.g., `attempt=999`), the exponential calculation may overflow or produce a value far exceeding `max_delay`. The function must cap the result at `max_delay` and return it without crashing.

10. **Randomization with per-call seeding**: The function must use Python's `random.Random` class to generate jittered delays. Each call to `jittered_backoff` must create a new `Random` instance seeded with a unique value derived from:
    - A module-level counter (`_jitter_counter`) that increments by 1 on each call, protected by a lock.
    - The result of `time.time_ns()` captured at the moment the counter is incremented (under the same lock).
    - The seed must be computed as `(time_ns_value, counter_value)` or a similar tuple that ensures uniqueness across concurrent calls.

11. **Thread safety of counter**: The module must maintain a module-level variable `_jitter_counter` initialized to 0. This counter must be incremented atomically (under a lock) each time `jittered_backoff` is called. The lock must protect both the read and increment of the counter and the capture of `time.time_ns()`.

12. **Concurrent call behavior**: When multiple threads call `jittered_backoff` concurrently with the same parameters (e.g., `attempt=1, base_delay=10.0, max_delay=120.0, jitter_ratio=0.5`), they must generally produce different delays due to different random seeds. Out of 8 concurrent calls, at least 6 must produce unique delay values.

13. **Module imports**: The module must import `random`, `time`, and `threading` from the Python standard library. These imports must be accessible for monkeypatching in tests (e.g., `retry_utils.random`, `retry_utils.time`, `retry_utils.threading`).

14. **Docstring**: The function must have a docstring that reads: `"Compute a jittered exponential backoff delay."` (exactly as specified in the EXACT API section).

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `def jittered_backoff(attempt: int, *, base_delay: float = 5.0, max_delay: float = 120.0, jitter_ratio: float = 0.5) -> float`

## Environment Configuration

### Python Version

Python >=3.11

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

### Node 1: Exponential backoff calculation

The `jittered_backoff` function computes a base delay using exponential backoff with the formula:
```
base_delay * (2 ** (attempt - 1))
```

For `attempt=1`, the exponent is `0`, so the result is `base_delay * 1 = base_delay`.
For `attempt=2`, the exponent is `1`, so the result is `base_delay * 2`.
For `attempt=3`, the exponent is `2`, so the result is `base_delay * 4`.
For `attempt=4`, the exponent is `3`, so the result is `base_delay * 8`.

When `jittered_backoff(1, base_delay=5.0, max_delay=120.0, jitter_ratio=0.0)` is called, the result is exactly `5.0`.
When `jittered_backoff(2, base_delay=5.0, max_delay=120.0, jitter_ratio=0.0)` is called, the result is exactly `10.0`.
When `jittered_backoff(3, base_delay=5.0, max_delay=120.0, jitter_ratio=0.0)` is called, the result is exactly `20.0`.
When `jittered_backoff(4, base_delay=5.0, max_delay=120.0, jitter_ratio=0.0)` is called, the result is exactly `40.0`.

### Node 2: Maximum delay capping

The computed exponential backoff delay is capped at `max_delay`. The effective delay is:
```
min(base_delay * (2 ** (attempt - 1)), max_delay)
```

When `jittered_backoff(10, base_delay=5.0, max_delay=60.0, jitter_ratio=0.0)` is called, the result does not exceed `60.0`.
When `jittered_backoff(20, base_delay=5.0, max_delay=60.0, jitter_ratio=0.0)` is called, the result does not exceed `60.0`.
When `jittered_backoff(100, base_delay=5.0, max_delay=60.0, jitter_ratio=0.0)` is called, the result does not exceed `60.0`.
When `jittered_backoff(999, base_delay=5.0, max_delay=120.0, jitter_ratio=0.0)` is called, the result is exactly `120.0`.

### Node 3: Zero base_delay guard

When `base_delay=0.0`, the function returns `max_delay` instead of `0.0`. This prevents busy-wait behavior.

When `jittered_backoff(1, base_delay=0.0, max_delay=60.0, jitter_ratio=0.0)` is called, the result is exactly `60.0`.

### Node 4: Negative attempt handling

Negative attempt values do not cause crashes. A negative attempt is treated as if `attempt=1`.

When `jittered_backoff(-5, base_delay=10.0, max_delay=120.0, jitter_ratio=0.0)` is called, the result is exactly `10.0`.

### Node 5: Jitter application

When `jitter_ratio > 0.0`, the function applies jitter to the computed base delay. The jitter is applied as a uniform random variation.

When `jitter_ratio=0.0`, no jitter is applied and the delay is deterministic.

When `jitter_ratio=0.5` and `attempt=1` with `base_delay=10.0` and `max_delay=120.0`:
- Multiple calls produce varying delays (not all identical).
- All delays are `>= 10.0` (the base delay).
- All delays are `<= 15.0` (the base delay plus jitter).

The jitter range is bounded by `base_delay * jitter_ratio`, so the final jittered delay is in the range `[base_delay, base_delay * (1 + jitter_ratio)]`.

### Node 6: Jitter seeding with per-call tick under lock

The jitter random number generator is seeded using a per-call tick value captured under a lock. The implementation uses:
- A global counter `_jitter_counter` that increments on each call.
- A call to `time.time_ns()` to obtain a high-resolution timestamp.
- A `random.Random` instance initialized with a seed derived from the timestamp.

Each call to `jittered_backoff` increments `_jitter_counter` and captures the current `time_ns()` value under a lock. This captured tick is used as the seed for the `random.Random` instance.

When two concurrent threads call `jittered_backoff` simultaneously (synchronized via a barrier), they each capture a different tick value and thus receive different seeds. The recorded seeds are unique across the two calls.

### Node 7: Thread safety

Concurrent calls to `jittered_backoff` with `jitter_ratio > 0.0` produce different delays. When 8 threads call `jittered_backoff(1, base_delay=10.0, max_delay=120.0, jitter_ratio=0.5)` concurrently, at least 6 of the 8 results are unique (i.e., `len(set(results)) >= 6`).