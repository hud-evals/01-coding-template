# context-compressor

## Overview

**context-compressor** is a Python library providing automatic context window compression for extended conversational interactions. Implemented as a single, self-contained module comprising 745 lines of code, the library enables applications to manage token budgets in long-running conversations by intelligently summarizing intermediate dialogue turns while preserving critical context at the conversation boundaries. The library encapsulates a single class that maintains its own OpenAI client instance, eliminating external dependency management for the core compression workflow.

The compression strategy employs a two-tier approach: an auxiliary model (optimized for cost and latency) generates structured summaries of middle conversation turns, while head and tail context—typically containing system prompts, initial user queries, and recent exchanges—remain uncompressed and protected from summarization. This architecture ensures that foundational conversational context and the most recent interaction history are preserved in their original form, while intermediate turns are condensed into structured summaries. The v2 implementation introduces an improved summary template that captures Goal and Progress dimensions, providing more semantically meaningful compression compared to earlier iterations.

The library is designed as a lightweight, drop-in utility for applications requiring context management in token-constrained environments, such as long-running chatbots, multi-turn reasoning systems, or conversation-based agents interfacing with OpenAI's API.

# Natural Language Instructions for Rebuilding context-compressor

## Implementation Constraints

- **Single module file**: All code lives in `/home/ubuntu/workspace/context_compressor.py`
- **No external private packages**: Do not attempt to import from `agent.*` or other repo-internal modules; recreate needed utilities locally
- **Exact signatures**: Use the function/method signatures provided verbatim—do not rename parameters or change defaults
- **All symbols required**: Every class, method, and module-level constant listed in REQUIRED TESTED SYMBOLS must exist and be importable
- **Test-driven behavior**: Implement only what the 42 tests demonstrate; do not invent features
- **Token counting**: Implement a simple character-to-token estimation (divide by 4) for rough preflight checks
- **OpenAI client optional**: The compressor may have `client=None`; gracefully fall back to truncation when summarization is unavailable

---

## Natural Language Instructions

### Step 1: Set Up Module Structure

Create `/home/ubuntu/workspace/context_compressor.py` as a single-file module. At the top, define:

1. **Module docstring**: `"Automatic context window compression for long conversations.\n\nSelf-contained class with its own OpenAI client for summarization.\nUses auxiliary model (cheap/fast) to summarize middle turns while\nprotecting head and tail context.\n\nImprovements over v1:\n  - Structured summary template (Goal, Progress,"`

2. **Module-level constant**: `SUMMARY_PREFIX = "[CONTEXT SUMMARY]:\n"` (note the newline)

3. **Legacy constant**: `LEGACY_SUMMARY_PREFIX = "[CONTEXT SUMMARY]:"`

4. **Imports**: Include `Dict`, `Any`, `List`, `Optional`, `Tuple` from `typing`; `time` for cooldown tracking; mock/stub for OpenAI client if needed

### Step 2: Implement Helper Functions (Module-Level)

Before the class, implement these utility functions that tests may call or that the class uses internally:

- **`get_model_context_length(model: str) -> int`**: Return a hardcoded context length for known models (e.g., `gpt-4` → 128000, `gpt-3.5-turbo` → 4096). This is patched in tests but must exist as a fallback.
- **`call_llm(client, model, messages, max_tokens, temperature) -> response`**: Wrapper around `client.chat.completions.create()`. Must handle `None` client gracefully. Tests patch this to inject mock responses.
- **`estimate_tokens(text: str) -> int`**: Simple estimation: `len(text) // 4` (rough OpenAI tokenizer approximation).

### Step 3: Implement the ContextCompressor Class

#### Class-Level Constants

Define these as class attributes:

```python
_CONTENT_MAX = 100000      # Max chars to keep in a message content
_CONTENT_HEAD = 50000      # Chars to keep from start of content
_TOOL_ARGS_MAX = 50000     # Max chars for tool arguments
_TOOL_ARGS_HEAD = 25000    # Chars to keep from start of tool args
_CONTENT_TAIL = 50000      # Chars to keep from end of content
```

#### `__init__` Method

**Signature:**
```python
def __init__(self, model: str, threshold_percent: float = 0.50, protect_first_n: int = 3, 
             protect_last_n: int = 20, summary_target_ratio: float = 0.20, quiet_mode: bool = False, 
             summary_model_override: str = None, base_url: str = "", api_key: str = "", 
             config_context_length: int | None = None, provider: str = ""):
```

**Behavioral Requirements:**

1. Store `model`, `threshold_percent`, `protect_first_n`, `protect_last_n`, `summary_target_ratio`, `quiet_mode`, `summary_model_override`, `base_url`, `api_key`, `config_context_length`, `provider` as instance attributes.

2. Determine context length:
   - If `config_context_length` is provided, use it.
   - Otherwise, call `get_model_context_length(model)`.
   - Store as `self.context_length`.

3. Calculate `threshold_tokens = context_length * threshold_percent`.

4. Clamp `summary_target_ratio` to the range `[0.10, 0.80]`.

5. Calculate `tail_token_budget = threshold_tokens * summary_target_ratio`.

6. Calculate `max_summary_tokens = min(context_length * 0.05, 12000)`.

7. Initialize tracking fields:
   - `last_prompt_tokens = 0`
   - `last_completion_tokens = 0`
   - `last_total_tokens = 0`
   - `compression_count = 0`
   - `_summary_cooldown_until = 0.0` (for cooldown tracking)

8. Create an OpenAI client if `api_key` is provided:
   - If `base_url` is non-empty, use it as the `base_url` parameter.
   - Otherwise, set `client = None` (graceful degradation).
   - Store as `self.client`.

9. Determine the summary model:
   - If `summary_model_override` is provided, use it.
   - Otherwise, use the main `model`.
   - Store as `self.summary_model`.

#### `update_from_response` Method

**Signature:**
```python
def update_from_response(self, usage: Dict[str, Any]):
```

**Behavioral Requirements:**

1. Extract `prompt_tokens`, `completion_tokens`, `total_tokens` from the `usage` dict.
2. Default missing keys to `0`.
3. Update `self.last_prompt_tokens`, `self.last_completion_tokens`, `self.last_total_tokens`.

#### `should_compress` Method

**Signature:**
```python
def should_compress(self, prompt_tokens: int = None) -> bool:
```

**Behavioral Requirements:**

1. If `prompt_tokens` is provided, use it; otherwise use `self.last_prompt_tokens`.
2. Return `True` if `prompt_tokens >= self.threshold_tokens`, else `False`.

#### `should_compress_preflight` Method

**Signature:**
```python
def should_compress_preflight(self, messages: List[Dict[str, Any]]) -> bool:
```

**Behavioral Requirements:**

1. Estimate total tokens by summing `estimate_tokens(msg.get("content", ""))` for each message.
2. Return `True` if estimated tokens exceed `self.threshold_tokens`, else `False`.

#### `get_status` Method

**Signature:**
```python
def get_status(self) -> Dict[str, Any]:
```

**Behavioral Requirements:**

1. Return a dict with keys:
   - `"last_prompt_tokens"`: `self.last_prompt_tokens`
   - `"threshold_tokens"`: `self.threshold_tokens`
   - `"context_length"`: `self.context_length`
   - `"usage_percent"`: `(self.last_prompt_tokens / self.context_length) * 100.0`
   - `"compression_count"`: `self.compression_count`

#### `_prune_old_tool_results` Method

**Signature:**
```python
def _prune_old_tool_results(self, messages: List[Dict[str, Any]], protect_tail_count: int, 
                            protect_tail_tokens: int | None = None) -> tuple[List[Dict[str, Any]], int]:
```

**Behavioral Requirements:**

1. Identify the tail boundary: the last `protect_tail_count` messages (or fewer if `protect_tail_tokens` is specified and limits the tail).
2. For messages **outside** the tail that have `role == "tool"`:
   - Replace their `content` with a short placeholder like `"[tool result pruned]"`.
3. Return a tuple: `(modified_messages, tokens_freed)` where `tokens_freed` is the estimated token reduction.

#### `_compute_summary_budget` Method

**Signature:**
```python
def _compute_summary_budget(self, turns_to_summarize: List[Dict[str, Any]]) -> int:
```

**Behavioral Requirements:**

1. Estimate the total tokens in `turns_to_summarize`.
2. Scale the summary budget: `budget = max(500, int(total_tokens * 0.15))` (15% of compressed content, minimum 500 tokens).
3. Cap at `self.max_summary_tokens`.
4. Return the budget.

#### `_serialize_for_summary` Method

**Signature:**
```python
def _serialize_for_summary(self, turns: List[Dict[str, Any]]) -> str:
```

**Behavioral Requirements:**

1. Iterate through `turns` and format each as `"{role}: {content}"` (one per line).
2. Handle `None` content by treating it as an empty string.
3. Handle dict content by converting to string representation.
4. Return the concatenated text.

#### `_generate_summary` Method

**Signature:**
```python
def _generate_summary(self, turns_to_summarize: List[Dict[str, Any]]) -> Optional[str]:
```

**Behavioral Requirements:**

1. Check cooldown: if `time.time() < self._summary_cooldown_until`, return `None` (skip retry).
2. If `self.client is None`, return `None` (no client available).
3. Serialize the turns using `_serialize_for_summary`.
4. Construct a system prompt asking for a structured summary (Goal, Progress, Next Steps format).
5. Call `call_llm(self.client, self.summary_model, messages=[...], max_tokens=self.max_summary_tokens, temperature=None)`.
6. Extract the response content:
   - If content is `None`, coerce to `""`.
   - If content is a dict, coerce to string.
   - Otherwise, use as-is.
7. Normalize the summary using `_with_summary_prefix`.
8. On exception:
   - Set `self._summary_cooldown_until = time.time() + 60` (60-second cooldown).
   - Return `None`.
9. Return the normalized summary string.

#### `_with_summary_prefix` Static Method

**Signature:**
```python
@staticmethod
def _with_summary_prefix(summary: str) -> str:
```

**Behavioral Requirements:**

1. If the summary already starts with `SUMMARY_PREFIX`, return it unchanged.
2. If the summary starts with `LEGACY_SUMMARY_PREFIX`, strip it and prepend `SUMMARY_PREFIX`.
3. Otherwise, prepend `SUMMARY_PREFIX` to the summary.
4. Return the normalized string.

#### `_get_tool_call_id` Static Method

**Signature:**
```python
@staticmethod
def _get_tool_call_id(tc) -> str:
```

**Behavioral Requirements:**

1. Accept a tool_call entry that may be a dict or a SimpleNamespace-like object.
2. Extract and return the `id` field.
3. Handle both `tc["id"]` (dict) and `tc.id` (object attribute) access patterns.

#### `_sanitize_tool_pairs` Method

**Signature:**
```python
def _sanitize_tool_pairs(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
```

**Behavioral Requirements:**

1. After compression, tool_call/tool_result pairs may be orphaned (e.g., tool_call removed but result remains).
2. Scan the messages and remove any `tool_result` message whose `tool_call_id` does not have a corresponding `tool_call` in an earlier `assistant` message.
3. Return the cleaned message list.

#### `_align_boundary_forward` Method

**Signature:**
```python
def _align_boundary_forward(self, messages: List[Dict[str, Any]], idx: int) -> int:
```

**Behavioral Requirements:**

1. Starting at index `idx`, move forward while the message at that index has `role == "tool"`.
2. Return the first index where `role != "tool"`, or the original `idx` if no adjustment needed.
3. This prevents starting a compression window in the middle of a tool_call/tool_result pair.

#### `_align_boundary_backward` Method

**Signature:**
```python
def _align_boundary_backward(self, messages: List[Dict[str, Any]], idx: int) -> int:
```

**Behavioral Requirements:**

1. Starting at index `idx`, move backward while the message at that index has `role == "tool"`.
2. Return the first index where `role != "tool"`, or the original `idx` if no adjustment needed.
3. This prevents ending a compression window in the middle of a tool_call/tool_result pair.

#### `_find_tail_cut_by_tokens` Method

**Signature:**
```python
def _find_tail_cut_by_tokens(self, messages: List[Dict[str, Any]], head_end: int, 
                             token_budget: int | None = None) -> int:
```

**Behavioral Requirements:**

1. Walk backward from the end of `messages`, accumulating token counts.
2. Use `token_budget` if provided; otherwise use `self.tail_token_budget`.
3. Enforce a **minimum tail of 3 messages** (never compress away the last 3 messages).
4. Enforce a **soft ceiling at 1.5x the budget**: if a message would exceed the budget but is less than 1.5x the budget, include it anyway (allows oversized messages).
5. Return the index where the tail begins (i.e., the first message to keep in the tail).

#### `compress` Method

**Signature:**
```python
def compress(self, messages: List[Dict[str, Any]], current_tokens: int = None) -> List[Dict[str, Any]]:
```

**Behavioral Requirements:**

1. **Early exit if too few messages**: If `len(messages) < (protect_first_n + 3 + protect_last_n)`, return messages unchanged.

2. **Identify head and tail**:
   - Head: first `protect_first_n` messages.
   - Tail: last `protect_last_n` messages (or fewer, determined by `_find_tail_cut_by_tokens` if token budgeting is active).

3. **Check if compression is needed**:
   - If `current_tokens` is provided, use it; otherwise estimate from messages.
   - If not exceeding threshold, return messages unchanged.

4. **Identify middle section**: Messages between head and tail.

5. **If no client available (fallback to truncation)**:
   - Remove middle messages, keeping head and tail.
   - Increment `compression_count`.
   - Return the truncated list.

6. **Summarization path** (if client available):
   - Call `_generate_summary(middle_messages)`.
   - If summary is `None`, fall back to truncation.
   - If summary is obtained:
     - Determine the role for the summary message:
       - Default to `"assistant"` if head ends with `"user"`, else `"user"`.
       - Check for collision with the first tail message; if collision, try flipping the role.
       - If both roles collide (double collision), merge the summary into the first tail message instead of creating a standalone message.
     - Insert the summary as a new message (or merge into tail).
     - Ensure no orphaned tool_call/tool_result pairs using `_sanitize_tool_pairs`.
     - Increment `compression_count`.
     - Return the compressed list.

7. **Protect against tool result orphans**: Before returning, call `_sanitize_tool_pairs` to remove any tool results without matching tool calls.

---

### Behavioral Requirements

1. **Module-level constant `SUMMARY_PREFIX`**: Must be defined as `"[CONTEXT SUMMARY]:\n"` (with newline).

2. **Module-level constant `LEGACY_SUMMARY_PREFIX`**: Must be defined as `"[CONTEXT SUMMARY]:"` (without newline).

3. **Class attribute `_CONTENT_MAX`**: Set to `100000` (max chars to preserve in message content).

4. **Class attribute `_CONTENT_HEAD`**: Set to `50000` (chars from start of content).

5. **Class attribute `_CONTENT_TAIL`**: Set to `50000` (chars from end of content).

6. **Class attribute `_TOOL_ARGS_MAX`**: Set to `50000` (max chars for tool arguments).

7. **Class attribute `_TOOL_ARGS_HEAD`**: Set to `25000` (chars from start of tool args).

8. **Initialization**: Store all constructor parameters; compute `context_length`, `threshold_tokens`, `tail_token_budget`, `max_summary_tokens`; clamp `summary_target_ratio` to `[0.10, 0.80]`; initialize tracking fields; create OpenAI client if `api_key` provided.

9. **Token tracking**: `update_from_response` extracts and stores `prompt_tokens`, `completion_tokens`, `total_tokens` from API responses.

10. **Compression threshold check**: `should_compress` returns `True` if prompt tokens exceed the threshold.

11. **Preflight estimation**: `should_compress_preflight` uses character-to-token estimation (divide by 4) for a quick check before API calls.

12. **Status reporting**: `get_status` returns a dict with usage metrics and compression count.

13. **Tool result pruning**: `_prune_old_tool_results` replaces old tool result contents with placeholders outside the protected tail.

14. **Summary budget scaling**: `_compute_summary_budget` scales the summary token budget based on the amount of content being compressed (15% of compressed content, min 500, max `max_summary_tokens`).

15. **Serialization for summarization**: `_serialize_for_summary` formats conversation turns as labeled text (role: content).

16. **Summary generation**: `_generate_summary` calls the LLM with a structured prompt, handles response coercion (None → "", dict → str), normalizes the prefix, and implements a 60-second cooldown on failure.

17. **Summary prefix normalization**: `_with_summary_prefix` ensures the summary uses the current `SUMMARY_PREFIX`, replacing legacy prefixes if found.

18. **Tool call ID extraction**: `_get_tool_call_id` handles both dict and object attribute access patterns.

19. **Tool pair sanitization**: `_sanitize_tool_pairs` removes orphaned tool_result messages after compression.

20. **Boundary alignment**: `_align_boundary_forward` and `_align_boundary_backward` prevent splitting tool_call/tool_result pairs.

21. **Tail token budgeting**: `_find_tail_cut_by_tokens` walks backward from the end, accumulating tokens, enforcing a minimum of 3 messages and a soft ceiling at 1.5x the budget.

22. **Compression logic**:
    - Return messages unchanged if fewer than `protect_first_n + 3 + protect_last_n` messages.
    - Identify head (first N), tail (last N or token-budgeted), and middle sections.
    - If no client, truncate middle and return.
    - If client available, generate summary of middle; determine summary role to avoid consecutive same-role messages; handle double collisions by merging into tail; sanitize tool pairs; increment compression count.

23. **Role alternation**: Summary message role is chosen to avoid consecutive messages with the same role. If both roles cause collisions (with head and tail), merge the summary into the first tail message instead.

24. **Graceful degradation**: If `client` is `None` or summary generation fails, fall back to truncation.

25. **Cooldown mechanism**: After a summary generation failure, set a 60-second cooldown to avoid repeated failures.

26. **Content truncation**: When preserving message content, truncate long content to `_CONTENT_MAX` chars, keeping `_CONTENT_HEAD` from the start and `_CONTENT_TAIL` from the end.

27. **Tool arguments truncation**: Similarly truncate tool arguments to `_TOOL_ARGS_MAX` chars, keeping `_TOOL_ARGS_HEAD` from the start.

28. **None and dict content handling**: Coerce `None` content to `""` and dict content to string representation in summaries and serialization.

29. **Minimum tail protection**: Even with a tiny token budget, at least 3 messages are always protected in the tail.

30. **Soft ceiling for oversized messages**: If a message exceeds the token budget but is less than 1.5x the budget, include it anyway to avoid splitting large messages.

31. **Compression count tracking**: Increment `compression_count` each time `compress` successfully reduces the message list.

32. **Default parameters**: `threshold_percent` defaults to `0.50`, `protect_first_n` defaults to `3`, `protect_last_n` defaults to `20`, `summary_target_ratio` defaults to `0.20`.

33. **Token estimation**: Use simple estimation `len(text) // 4` for rough token counts in preflight checks.

34. **OpenAI client creation**: If `api_key` is provided, create a client; if `base_url` is non-empty, pass it to the client constructor.

35. **Summary model selection**: Use `summary_model_override` if provided; otherwise use the main `model`.

36. **Context length resolution**: Use `config_context_length` if provided; otherwise call `get_model_context_length(model)`.

37. **Tail boundary determination**: Use `_find_tail_cut_by_tokens` to determine the tail boundary based on token budget, not just message count.

38. **No temperature forcing**: When calling the LLM for summarization, do not force a specific temperature (let the client use its default).

39. **Structured summary prompt**: Ask the summarizer to provide Goal, Progress, and Next Steps in the summary.

40. **Prevent tool result orphans at tail start**: Ensure the tail does not start with a tool_result message; if it does, adjust the boundary.

41. **Prevent tool call/result splitting**: Use `_align_boundary_forward` and `_align_boundary_backward` to ensure compression boundaries do not split tool_call/tool_result pairs.

42. **Minimum compressible size**: A conversation must have at least `protect_first_n + 3 + protect_last_n` messages to be compressible (8 messages with defaults: 3 + 3 + 2 = 8, but the test shows 9 is the first compressible size, so the guard is `protect_first_n + 3 + protect_last_n`).

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `class ContextCompressor`
- `def ContextCompressor.update_from_response(self, usage: Dict[str, Any])`
- `def ContextCompressor.should_compress(self, prompt_tokens: int = None) -> bool`
- `def ContextCompressor.should_compress_preflight(self, messages: List[Dict[str, Any]]) -> bool`
- `def ContextCompressor.get_status(self) -> Dict[str, Any]`
- `def ContextCompressor._prune_old_tool_results(self, messages: List[Dict[str, Any]], protect_tail_count: int, protect_tail_tokens: int | None = None) -> tuple[List[Dict[str, Any]], int]`
- `def ContextCompressor._generate_summary(self, turns_to_summarize: List[Dict[str, Any]]) -> Optional[str]`
- `def ContextCompressor._with_summary_prefix(summary: str) -> str`
- `def ContextCompressor._find_tail_cut_by_tokens(self, messages: List[Dict[str, Any]], head_end: int, token_budget: int | None = None) -> int`
- `def ContextCompressor.compress(self, messages: List[Dict[str, Any]], current_tokens: int = None) -> List[Dict[str, Any]]`
- `SUMMARY_PREFIX`

## Environment Configuration

### Python Version

Python 3.10

### Workspace

- Put the implementation directly under `/home/ubuntu/workspace`.
- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.
- Hidden tests import the solution as top-level module file(s): `context_compressor.py`.

### External Dependencies

No third-party runtime dependencies were detected from the source file.

### Internal Helpers (implement locally)

These names came from repo-internal modules. Do NOT try to `pip install` them.

- `agent.auxiliary_client`: repo-private helper module; the original code imported `call_llm` from `agent.auxiliary_client`. Recreate the needed behavior locally.
- `agent.model_metadata`: repo-private helper module; the original code imported `estimate_messages_tokens_rough`, `get_model_context_length` from `agent.model_metadata`. Recreate the needed behavior locally.


## Project Directory Structure

```
workspace/
├── pyproject.toml
├── context_compressor.py
```

## API Usage Guide

### 1. Module Import

```python
from context_compressor import (
    ContextCompressor,
    SUMMARY_PREFIX,
    LEGACY_SUMMARY_PREFIX,
)
```

### 2. `ContextCompressor` Class

Compresses conversation context when approaching the model's context limit.

Algorithm:
  1. Prune old tool results (cheap, no LLM call)
  2. Protect head messages (system prompt + first exchange)
  3. Protect tail messages by token budget (most recent ~20K tokens)
  4. Summarize middle turns with structured LLM prompt
  5. On subsequent compactions, iteratively update the previous summary

```python
class ContextCompressor():
    """Compresses conversation context when approaching the model's context limit."""
```

**Class Variables:**
- `_CONTENT_MAX`
- `_CONTENT_HEAD`
- `_CONTENT_TAIL`
- `_TOOL_ARGS_MAX`
- `_TOOL_ARGS_HEAD`


```python
def __init__(self, model: str, threshold_percent: float = 0.50, protect_first_n: int = 3, protect_last_n: int = 20, summary_target_ratio: float = 0.20, quiet_mode: bool = False, summary_model_override: str = None, base_url: str = "", api_key: str = "", config_context_length: int | None = None, provider: str = ""):
```

**Parameters:**
- `model: str`
- `threshold_percent: float = 0.50`
- `protect_first_n: int = 3`
- `protect_last_n: int = 20`
- `summary_target_ratio: float = 0.20`
- `quiet_mode: bool = False`
- `summary_model_override: str = None`
- `base_url: str = ""`
- `api_key: str = ""`
- `config_context_length: int | None = None`
- `provider: str = ""`


Update tracked token usage from API response.

```python
def update_from_response(self, usage: Dict[str, Any]):
```

**Parameters:**
- `usage: Dict[str, Any]`


Check if context exceeds the compression threshold.

```python
def should_compress(self, prompt_tokens: int = None) -> bool:
```

**Parameters:**
- `prompt_tokens: int = None`

**Returns:** `bool`


Quick pre-flight check using rough estimate (before API call).

```python
def should_compress_preflight(self, messages: List[Dict[str, Any]]) -> bool:
```

**Parameters:**
- `messages: List[Dict[str, Any]]`

**Returns:** `bool`


Get current compression status for display/logging.

```python
def get_status(self) -> Dict[str, Any]:
```

**Returns:** `Dict[str, Any]`


Replace old tool result contents with a short placeholder.

Walks backward from the end, protecting the most recent messages that
fall within ``protect_tail_tokens`` (when provided) OR the last
``protect_tail_count`` messages (backward-compatible default).
When both are given, the token budget takes priority and the message
count acts as a hard minimum floor.

Returns (pruned_messages, pruned_count).

```python
def _prune_old_tool_results(self, messages: List[Dict[str, Any]], protect_tail_count: int, protect_tail_tokens: int | None = None) -> tuple[List[Dict[str, Any]], int]:
```

**Parameters:**
- `messages: List[Dict[str, Any]]`
- `protect_tail_count: int`
- `protect_tail_tokens: int | None = None`

**Returns:** `tuple[List[Dict[str, Any]], int]`


Scale summary token budget with the amount of content being compressed.

The maximum scales with the model's context window (5% of context,
capped at ``_SUMMARY_TOKENS_CEILING``) so large-context models get
richer summaries instead of being hard-capped at 8K tokens.

```python
def _compute_summary_budget(self, turns_to_summarize: List[Dict[str, Any]]) -> int:
```

**Parameters:**
- `turns_to_summarize: List[Dict[str, Any]]`

**Returns:** `int`


Serialize conversation turns into labeled text for the summarizer.

Includes tool call arguments and result content (up to
``_CONTENT_MAX`` chars per message) so the summarizer can preserve
specific details like file paths, commands, and outputs.

```python
def _serialize_for_summary(self, turns: List[Dict[str, Any]]) -> str:
```

**Parameters:**
- `turns: List[Dict[str, Any]]`

**Returns:** `str`


Generate a structured summary of conversation turns.

Uses a structured template (Goal, Progress, Decisions, Files, Next Steps)
inspired by Pi-mono and OpenCode. When a previous summary exists,
generates an iterative update instead of summarizing from scratch.

Returns None if all attempts fail — the caller should drop
the middle turns without a summary rather than inject a useless
placeholder.

```python
def _generate_summary(self, turns_to_summarize: List[Dict[str, Any]]) -> Optional[str]:
```

**Parameters:**
- `turns_to_summarize: List[Dict[str, Any]]`

**Returns:** `Optional[str]`


Normalize summary text to the current compaction handoff format.

```python
def _with_summary_prefix(summary: str) -> str:
```

**Parameters:**
- `summary: str`

**Returns:** `str`

**Decorators:** `staticmethod`


Extract the call ID from a tool_call entry (dict or SimpleNamespace).

```python
def _get_tool_call_id(tc) -> str:
```

**Parameters:**
- `tc`

**Returns:** `str`

**Decorators:** `staticmethod`


Fix orphaned tool_call / tool_result pairs after compression.

Two failure modes:
1. A tool *result* references a call_id whose assistant tool_call was
   removed (summarized/truncated).  The API rejects this with
   "No tool call found for function call output with call_id ...".
2. An assistant message has tool_calls whose results were dropped.
   The API rejects this because every tool_call must be followed by
   a tool result with the matching call_id.

This method removes orphaned results and inserts stub results for
orphaned calls so the message list is always well-formed.

```python
def _sanitize_tool_pairs(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
```

**Parameters:**
- `messages: List[Dict[str, Any]]`

**Returns:** `List[Dict[str, Any]]`


Push a compress-start boundary forward past any orphan tool results.

If ``messages[idx]`` is a tool result, slide forward until we hit a
non-tool message so we don't start the summarised region mid-group.

```python
def _align_boundary_forward(self, messages: List[Dict[str, Any]], idx: int) -> int:
```

**Parameters:**
- `messages: List[Dict[str, Any]]`
- `idx: int`

**Returns:** `int`


Pull a compress-end boundary backward to avoid splitting a
tool_call / result group.

If the boundary falls in the middle of a tool-result group (i.e.
there are consecutive tool messages before ``idx``), walk backward
past all of them to find the parent assistant message.  If found,
move the boundary before the assistant so the entire
assistant + tool_results group is included in the summarised region
rather than being split (which causes silent data loss when
``_sanitize_tool_pairs`` removes the orphaned tail results).

```python
def _align_boundary_backward(self, messages: List[Dict[str, Any]], idx: int) -> int:
```

**Parameters:**
- `messages: List[Dict[str, Any]]`
- `idx: int`

**Returns:** `int`


Walk backward from the end of messages, accumulating tokens until
the budget is reached. Returns the index where the tail starts.

``token_budget`` defaults to ``self.tail_token_budget`` which is
derived from ``summary_target_ratio * context_length``, so it
scales automatically with the model's context window.

Token budget is the primary criterion.  A hard minimum of 3 messages
is always protected, but the budget is allowed to exceed by up to
1.5x to avoid cutting inside an oversized message (tool output, file
read, etc.).  If even the minimum 3 messages exceed 1.5x the budget
the cut is placed right after the head so compression still runs.

Never cuts inside a tool_call/result group.

```python
def _find_tail_cut_by_tokens(self, messages: List[Dict[str, Any]], head_end: int, token_budget: int | None = None) -> int:
```

**Parameters:**
- `messages: List[Dict[str, Any]]`
- `head_end: int`
- `token_budget: int | None = None`

**Returns:** `int`


Compress conversation messages by summarizing middle turns.

Algorithm:
  1. Prune old tool results (cheap pre-pass, no LLM call)
  2. Protect head messages (system prompt + first exchange)
  3. Find tail boundary by token budget (~20K tokens of recent context)
  4. Summarize middle turns with structured LLM prompt
  5. On re-compression, iteratively update the previous summary

After compression, orphaned tool_call / tool_result pairs are cleaned
up so the API never receives mismatched IDs.

```python
def compress(self, messages: List[Dict[str, Any]], current_tokens: int = None) -> List[Dict[str, Any]]:
```

**Parameters:**
- `messages: List[Dict[str, Any]]`
- `current_tokens: int = None`

**Returns:** `List[Dict[str, Any]]`

### 3. Constants and Configuration

```python
SUMMARY_PREFIX = ...  # 398 chars
LEGACY_SUMMARY_PREFIX = "[CONTEXT SUMMARY]:"
_MIN_SUMMARY_TOKENS = 2000
_SUMMARY_RATIO = 0.20
_SUMMARY_TOKENS_CEILING = 12_000
_PRUNED_TOOL_PLACEHOLDER = "[Old tool output cleared to save context space]"
_CHARS_PER_TOKEN = 4
_SUMMARY_FAILURE_COOLDOWN_SECONDS = 600
```

## Implementation Notes

### Node 1: Threshold-Based Compression Triggering

The `should_compress()` method compares `last_prompt_tokens` (or an explicitly passed `prompt_tokens` parameter) against `threshold_tokens` to determine if compression is needed. The threshold is computed as `context_length * threshold_percent`. Default `threshold_percent` is 0.50 (50%). When `prompt_tokens >= threshold_tokens`, compression is triggered. The `should_compress_preflight()` method provides a rough pre-flight estimate by dividing total message character count by `_CHARS_PER_TOKEN` (4) and comparing against the threshold, without making an API call.

### Node 2: Token Usage Tracking

The `update_from_response()` method extracts `prompt_tokens`, `completion_tokens`, and `total_tokens` from an API response dictionary and stores them in `last_prompt_tokens`, `last_completion_tokens`, and `last_total_tokens` respectively. Missing fields default to 0. The `get_status()` method returns a dictionary containing these tracked values plus `threshold_tokens`, `context_length`, `usage_percent` (calculated as `last_prompt_tokens / context_length * 100`), and `compression_count`.

### Node 3: Message Protection Strategy

The compressor protects the first `protect_first_n` messages (default 3) and last `protect_last_n` messages (default 20) from compression. Messages between these protected ranges are candidates for summarization. A minimum of `protect_first_n + protect_last_n + 1` messages is required to attempt compression; otherwise messages are returned unchanged. The `compression_count` field increments each time `compress()` is called and actually performs compression.

### Node 4: Tail Token Budget Calculation

The `tail_token_budget` is computed as `threshold_tokens * summary_target_ratio`. The `summary_target_ratio` parameter (default 0.20) is clamped to the range [0.10, 0.80]. The `max_summary_tokens` is set to 5% of `context_length`, capped at `_SUMMARY_TOKENS_CEILING` (12,000). These budgets control how many tokens are reserved for the tail (recent messages) and how large a generated summary can be.

### Node 5: Compression Fallback Path

When no LLM client is available (client is None), the compressor falls back to truncation: it removes middle messages while preserving the first `protect_first_n` and last `protect_last_n` messages. This ensures compression can still occur even without summarization capability. System messages are always preserved at the head.

### Node 6: Summary Generation and Prefix Normalization

The `_generate_summary()` method calls an LLM to summarize a list of conversation turns. The summary response content is normalized via `_with_summary_prefix()`, which:
- Replaces the legacy prefix `LEGACY_SUMMARY_PREFIX` ("[CONTEXT SUMMARY]:") with the current format `SUMMARY_PREFIX` + newline
- Does not duplicate if the current prefix already exists
- Coerces non-string content (dict, None) to string representation

The summary is only generated if at least `_MIN_SUMMARY_TOKENS` (2000) of content exists to summarize.

### Node 7: Summary Failure Cooldown

If `_generate_summary()` raises an exception, the compressor enters a cooldown state for `_SUMMARY_FAILURE_COOLDOWN_SECONDS` (600 seconds). During cooldown, subsequent calls to `_generate_summary()` return None immediately without retrying the LLM call. This prevents repeated failures from blocking compression attempts.

### Node 8: Summary Budget Scaling

The `_compute_summary_budget()` method scales the summary token budget based on the amount of content being compressed. It ensures the summary is proportional to the conversation size while respecting `max_summary_tokens` as an upper bound and `_MIN_SUMMARY_TOKENS` as a lower bound.

### Node 9: Tool Call Pair Integrity

The `_sanitize_tool_pairs()` method ensures that tool_call and tool_result messages remain paired after compression. If a tool_call message is removed but its corresponding tool_result remains, or vice versa, the method fixes the orphaned pair. The `_get_tool_call_id()` static method extracts the call ID from a tool_call entry, handling both dict and SimpleNamespace formats.

### Node 10: Boundary Alignment for Tool Calls

The `_align_boundary_forward()` method pushes a compression-start boundary forward past any orphan tool_result messages that would be left unmatched. The `_align_boundary_backward()` method pulls a compression-end boundary backward to avoid splitting a tool_call/tool_result pair. These ensure the compression window does not create broken tool call sequences.

### Node 11: Tail Cutoff by Token Budget

The `_find_tail_cut_by_tokens()` method walks backward from the end of messages, accumulating tokens until the `tail_token_budget` is reached. It enforces a minimum of 3 protected tail messages and allows a soft ceiling of 1.5× the budget to avoid splitting oversized messages. This replaces simple message-count protection with token-aware protection, enabling compression even when the tail contains large tool outputs.

### Node 12: Tool Result Pruning

The `_prune_old_tool_results()` method replaces the content of old tool_result messages with the placeholder `_PRUNED_TOOL_PLACEHOLDER` ("[Old tool output cleared to save context space]") to reduce token usage while preserving the message structure. This is applied to messages outside the protected tail range.

### Node 13: Summary Role Collision Avoidance

When inserting a summary message, the compressor chooses its role to avoid consecutive messages with the same role:
- If the last head message and first tail message have different roles, the summary takes the role that does not collide with either.
- If both roles collide (double collision), the summary is merged into the first tail message's content instead of creating a standalone message.
- This ensures valid alternating role sequences in the final message list.

### Node 14: Serialization for Summarization

The `_serialize_for_summary()` method converts a list of conversation turns into labeled text suitable for LLM summarization. Each turn is formatted with role and content labels, preserving the conversational structure for the summarizer to understand context.

### Node 15: Compression Workflow

The `compress()` method orchestrates the full compression pipeline:
1. Check if compression is needed; return unchanged if not.
2. Identify protected head and tail ranges.
3. Attempt summarization if an LLM client is available; fall back to truncation if not.
4. Prune old tool results to save tokens.
5. Sanitize tool call pairs to fix orphans.
6. Increment `compression_count`.
7. Return the compressed message list.

The method accepts an optional `current_tokens` parameter to override the tracked `last_prompt_tokens` for the compression decision.