# prompt-caching

## Overview

**prompt-caching** is a lightweight Python library that implements Anthropic's prompt caching mechanism to optimize token consumption in multi-turn conversations. The library consists of a single module containing 72 lines of code organized around 2 module-level functions, with no class-based abstractions. It implements the `system_and_3` caching strategy, which leverages Anthropic's maximum of 4 cache_control breakpoints to reduce input token costs by approximately 75% on multi-turn interactions.

The caching strategy operates by maintaining a fixed set of cache control boundaries: the system prompt (which remains stable across all conversation turns) and a rolling window of the last 3 non-system messages. This approach ensures that frequently-reused context—particularly the system prompt and recent conversation history—is cached at the API level, minimizing redundant token processing while preserving the dynamic nature of ongoing conversations. The implementation is pure functional in design, relying entirely on module-level functions rather than stateful class instances.

This library is designed for developers building conversational AI applications with Anthropic's API who need to optimize costs without managing complex caching logic. By abstracting the cache_control breakpoint placement strategy into a simple interface, prompt-caching enables straightforward integration into existing message-passing workflows while maintaining full compatibility with Anthropic's caching constraints.

# Natural Language Instructions

## Implementation Constraints

- **Single module file**: Create `/home/ubuntu/workspace/prompt_caching.py` with both functions at module level
- **No external dependencies** beyond Python standard library (use `copy.deepcopy()` for deep copying)
- **Exact signatures**: Match parameter names, types, defaults, and return types precisely
- **Dict key literals**: Use exact strings: `'cache_control'`, `'content'`, `'role'`, `'ttl'`, `'type'`, `'text'`, `'ephemeral'`
- **No class definitions**: Only module-level functions
- **Immutability of inputs**: Always return a deep copy; never mutate the input `api_messages` list or its nested dicts
- **Native Anthropic vs. OpenRouter behavior**: Handle the `native_anthropic` flag to control where `cache_control` is placed on tool messages

---

## Behavioral Requirements

1. **`_apply_cache_marker(msg: dict, cache_marker: dict, native_anthropic: bool = False) -> None`**
   - Modifies a single message dict in-place to add a cache control marker
   - If `msg["role"] == "tool"` and `native_anthropic == False`: do NOT add `cache_control` (OpenRouter does not support it on tool messages)
   - If `msg["role"] == "tool"` and `native_anthropic == True`: add `cache_control` at the top level of the message dict
   - If `msg["content"]` is `None` or an empty string `""`: add `cache_control` at the top level of the message dict (do NOT wrap empty strings into a list)
   - If `msg["content"]` is a non-empty string: convert it to a list with a single dict `{"type": "text", "text": <original_string>, "cache_control": cache_marker}`, then replace `msg["content"]` with this list
   - If `msg["content"]` is already a list: add `cache_control` to the last item in the list only
   - If `msg["content"]` is an empty list: do nothing (no crash, no marker added)

2. **`apply_anthropic_cache_control(api_messages: List[Dict[str, Any]], cache_ttl: str = "5m", native_anthropic: bool = False) -> List[Dict[str, Any]]`**
   - Returns a deep copy of `api_messages` (original list and all nested dicts must remain unmodified)
   - If `api_messages` is empty, return an empty list
   - Implements the "system_and_3" caching strategy: place cache control markers on up to 4 messages maximum
   - **Breakpoint 1**: The first message if it has `role == "system"` (system prompt is stable across turns)
   - **Breakpoints 2–4**: The last 3 non-system messages in the list (rolling window of recent context)
   - Create a cache marker dict with structure `{"type": "ephemeral", "ttl": cache_ttl}` where `cache_ttl` is the parameter value (e.g., `"5m"` or `"1h"`)
   - Pass `native_anthropic` flag to `_apply_cache_marker()` for each marked message
   - Apply markers in order: first to the system message (if present), then to the last 3 non-system messages (if they exist)
   - Never apply more than 4 cache control markers total, even if there are more messages

3. **Cache marker structure**
   - The marker dict passed to `_apply_cache_marker()` must have keys `"type"` (value: `"ephemeral"`) and `"ttl"` (value: the `cache_ttl` parameter)

4. **Deep copy requirement**
   - Use `copy.deepcopy()` to ensure the returned list and all nested message dicts are independent copies
   - Verify that modifying the returned list does not affect the original `api_messages`

5. **Content transformation rules** (in `_apply_cache_marker`)
   - String content (non-empty) → wrap in list with text block containing cache_control
   - List content → add cache_control only to the last item
   - None or empty string → add cache_control at message top level
   - Empty list → no action
   - Tool messages on OpenRouter → skip cache_control entirely

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `def _apply_cache_marker(msg: dict, cache_marker: dict, native_anthropic: bool = False) -> None`
- `def apply_anthropic_cache_control(api_messages: List[Dict[str, Any]], cache_ttl: str = "5m", native_anthropic: bool = False) -> List[Dict[str, Any]]`

## Environment Configuration

### Python Version

Python 3.10

### Workspace

- Put the implementation directly under `/home/ubuntu/workspace`.
- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.
- Hidden tests import the solution as top-level module file(s): `prompt_caching.py`.

### External Dependencies

No third-party runtime dependencies were detected from the source file.


## Project Directory Structure

```
workspace/
├── pyproject.toml
├── prompt_caching.py
```

## API Usage Guide

### 1. Module Import

```python
from prompt_caching import (
    apply_anthropic_cache_control,
)
```

### 2. `apply_anthropic_cache_control` Function

Apply system_and_3 caching strategy to messages for Anthropic models.

Places up to 4 cache_control breakpoints: system prompt + last 3 non-system messages.

Returns:
    Deep copy of messages with cache_control breakpoints injected.

```python
def apply_anthropic_cache_control(api_messages: List[Dict[str, Any]], cache_ttl: str = "5m", native_anthropic: bool = False) -> List[Dict[str, Any]]:
```

**Parameters:**
- `api_messages: List[Dict[str, Any]]`
- `cache_ttl: str = "5m"`
- `native_anthropic: bool = False`

**Returns:** `List[Dict[str, Any]]`


## Implementation Notes

### Node 1: _apply_cache_marker Function Behavior

**Purpose:** Add `cache_control` marker to a single message dict, with behavior varying by platform and content type.

**Platform-Specific Behavior:**
- When `native_anthropic=True`: Always add `cache_control` at top level for `role: "tool"` messages (adapter will relocate it internally)
- When `native_anthropic=False` (e.g., OpenRouter): Skip adding `cache_control` to `role: "tool"` messages entirely (top-level markers on tool messages cause silent hangs)

**Content Type Handling:**

1. **None or empty string content** (`content: None` or `content: ""`):
   - Add `cache_control` at message top level
   - Do NOT wrap content into a list structure
   - Preserve original content value

2. **String content** (non-empty):
   - Convert to list format: `[{"type": "text", "text": <original>, "cache_control": <marker>}]`
   - Marker placed on the text block, not at message level

3. **List content**:
   - Locate last item in the list
   - Add `cache_control` to that final item only
   - Leave all preceding items unchanged
   - Handle empty lists without crashing (no-op)

**Marker Structure:** The `cache_marker` parameter is a dict (e.g., `{"type": "ephemeral", "ttl": "5m"}`) that is assigned directly to the `cache_control` key.

---

### Node 2: apply_anthropic_cache_control Function Behavior

**Purpose:** Apply the "system_and_3" caching strategy to a message list, adding cache markers to system message and last 3 non-system messages.

**Input/Output:**
- Returns a deep copy of the input message list (original list and all nested dicts remain unmodified)
- Empty input list returns empty list
- Default `cache_ttl="5m"` parameter controls TTL value in cache markers

**Caching Strategy (system_and_3):**
- **System message** (if present): Always receives a cache marker
- **Non-system messages**: Only the last 3 receive cache markers
- **Maximum breakpoints:** 4 total (1 system + 3 non-system)
- If fewer than 3 non-system messages exist, all non-system messages get markers
- If no system message exists, up to 4 non-system messages can receive markers

**Cache Marker Structure:**
- Built with `type: "ephemeral"` and `ttl: <cache_ttl>` parameter value
- Applied via `_apply_cache_marker()` using the same content-type rules

**Message Processing:**
- Identifies system message (first message with `role: "system"`)
- Counts non-system messages and marks the last 3 (or fewer if list is shorter)
- Applies markers using `_apply_cache_marker()` with `native_anthropic` parameter passed through