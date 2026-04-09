# anthropic-adapter

## Overview

**anthropic-adapter** is a Python library that provides protocol translation between Hermes Agent's internal message format and Anthropic's Messages API. The library consists of a single module containing 36 module-level functions organized across 1,409 lines of code, with no class-based abstractions. It follows the established adapter pattern used in the codex_responses adapter, ensuring that all Anthropic-specific implementation details are encapsulated within this dedicated module rather than distributed throughout the agent codebase.

The adapter handles bidirectional conversion between Hermes's OpenAI-compatible message schema and Anthropic's native Messages API format. This translation layer enables Hermes Agent to interact with Anthropic's Claude models while maintaining a unified internal interface. The library supports authentication via standard Anthropic API keys (sk-ant-api* format), allowing seamless integration with Anthropic's cloud-hosted inference endpoints.

By isolating provider-specific logic in a single, focused module, anthropic-adapter maintains clean separation of concerns and facilitates future maintenance and extension. The function-based architecture—comprising 36 discrete operations—provides granular control over message transformation, parameter mapping, and response handling without introducing unnecessary object-oriented overhead.

# Natural Language Instructions for Rebuilding anthropic_adapter.py

## Implementation Constraints

- **Single file module**: All code lives in `/home/ubuntu/workspace/anthropic_adapter.py`
- **No external private packages**: Recreate all needed behavior locally using only public APIs
- **Exact signatures**: Copy function signatures verbatim—do not rename parameters or change defaults
- **Test-driven**: Every symbol in the REQUIRED TESTED SYMBOLS section must exist and pass its tests
- **String literals**: Use the exact dictionary keys and field names listed in the specification
- **Constants**: Define `THINKING_BUDGET` and `ADAPTIVE_EFFORT_MAP` at module level

---

## Natural Language Instructions

### Overview
You are rebuilding the `anthropic_adapter.py` module, which translates between Hermes's internal OpenAI-style message format and Anthropic's Messages API. The module handles authentication (API keys and OAuth tokens), model normalization, message/tool conversion, and response normalization.

### Behavioral Requirements

1. **Token Type Detection (`_is_oauth_token`)**
   - Return `True` if the key is an OAuth/setup token (starts with `sk-ant-oat01-`, is a JWT, or is a managed key like `ou1R1z-...`)
   - Return `False` for regular API keys (start with `sk-ant-api03-`) or empty strings
   - Managed keys from `~/.claude.json` are treated as OAuth tokens

2. **Max Output Token Lookup (`_get_anthropic_max_output`)**
   - Return the maximum output token limit for a given Anthropic model name
   - Support at least: `claude-opus-4-1`, `claude-sonnet-4-20250514`, `claude-haiku-3-5-20241022`, and other Claude variants
   - Return a sensible default (e.g., 4096) for unknown models

3. **Adaptive Thinking Support Detection (`_supports_adaptive_thinking`)**
   - Return `True` for Claude 4.6 models that support adaptive thinking (e.g., `claude-4-6-*`)
   - Return `False` for other models

4. **Claude Code Version Detection (`_detect_claude_code_version`, `_get_claude_code_version`)**
   - `_detect_claude_code_version()`: Attempt to detect the installed Claude Code version by running `claude --version` or similar; fall back to a static constant (e.g., `"0.0.0"`)
   - `_get_claude_code_version()`: Lazily detect and cache the version when OAuth headers need it

5. **Base URL Normalization (`_normalize_base_url_text`)**
   - Convert SDK/transport URL objects to plain strings for inspection
   - Handle `None` gracefully

6. **Third-Party Endpoint Detection (`_is_third_party_anthropic_endpoint`)**
   - Return `True` for non-Anthropic endpoints using the Anthropic Messages API (e.g., Minimax at `https://api.minimax.io/anthropic`)
   - Return `False` for official Anthropic endpoints or `None`

7. **Bearer Auth Requirement (`_requires_bearer_auth`)**
   - Return `True` for Anthropic-compatible providers that require Bearer token auth (e.g., Minimax)
   - Return `False` for official Anthropic endpoints

8. **Anthropic Client Builder (`build_anthropic_client`)**
   - Create an Anthropic SDK client with the given `api_key` and optional `base_url`
   - Auto-detect setup tokens vs. regular API keys using `_is_oauth_token()`
   - For setup tokens: use `auth_token` parameter and add OAuth/Claude Code beta headers
   - For API keys: use `api_key` parameter
   - For third-party endpoints requiring Bearer auth: use `auth_token` instead of `api_key`
   - Always include common beta headers (e.g., `interleaved-thinking-2025-05-14`)
   - Return the instantiated client

9. **Claude Code Credentials Reading (`read_claude_code_credentials`)**
   - Read from `~/.claude/.credentials.json`
   - Extract the `claudeAiOauth` key
   - Return `None` if file doesn't exist, key is missing, or `accessToken` is empty
   - Return a dict with keys: `accessToken`, `refreshToken`, `expiresAt` (in milliseconds)

10. **Managed Key Reading (`read_claude_managed_key`)**
    - Read from `~/.claude.json`
    - Extract `primaryApiKey` field
    - Return `None` if file doesn't exist or key is missing
    - Used for diagnostics only, not for token resolution

11. **Claude Code Token Validity Check (`is_claude_code_token_valid`)**
    - Return `True` if `accessToken` exists and either `expiresAt` is 0 or current time is before expiry
    - Return `False` if token is expired (current time in ms > `expiresAt`)

12. **OAuth Token Refresh (Pure) (`refresh_anthropic_oauth_pure`)**
    - Make an HTTP POST to Anthropic's OAuth token endpoint with the `refresh_token`
    - Parse the response JSON
    - Return a dict with keys: `access_token`, `refresh_token`, `expires_in`
    - If `use_json=True`, send JSON body; otherwise use form-encoded
    - Handle network errors gracefully

13. **OAuth Token Refresh with Persistence (`_refresh_oauth_token`)**
    - Check if `refreshToken` exists and is non-empty; return `None` if not
    - Call `refresh_anthropic_oauth_pure()` with the refresh token
    - On success, call `_write_claude_code_credentials()` to persist the new tokens
    - Return the new access token
    - Return `None` on any error

14. **Write Claude Code Credentials (`_write_claude_code_credentials`)**
    - Write to `~/.claude/.credentials.json`
    - Create parent directories if needed
    - Preserve existing top-level keys in the file
    - Update/create the `claudeAiOauth` object with: `accessToken`, `refreshToken`, `expiresAt` (in ms)
    - Optionally include `scopes` if provided

15. **Resolve Claude Code Token from Credentials (`_resolve_claude_code_token_from_credentials`)**
    - Accept optional `creds` dict; if not provided, call `read_claude_code_credentials()`
    - Return `None` if no creds
    - Check if token is valid; if yes, return it
    - If expired but has refresh token, attempt `_refresh_oauth_token()` and return the new token
    - Return `None` if refresh fails

16. **Prefer Refreshable Claude Code Token (`_prefer_refreshable_claude_code_token`)**
    - Given an env token and optional creds dict
    - If creds exist and have a valid/refreshable token, prefer that over the env token
    - This prevents a static env token from shadowing a refreshable credential
    - Return the preferred token or `None`

17. **Token Source Classification (`get_anthropic_token_source`)**
    - Classify where a token came from: `"ANTHROPIC_TOKEN"`, `"ANTHROPIC_API_KEY"`, `"CLAUDE_CODE_OAUTH"`, `"CLAUDE_CODE_CREDENTIALS"`, `"CLAUDE_MANAGED_KEY"`, or `"unknown"`
    - Check environment variables first, then credential files
    - Return a string describing the source

18. **Resolve Anthropic Token (`resolve_anthropic_token`)**
    - Check `ANTHROPIC_TOKEN` env var first (OAuth tokens)
    - Then check `ANTHROPIC_API_KEY` env var
    - Then check `CLAUDE_CODE_OAUTH_TOKEN` env var
    - Then check Claude Code credentials file (`~/.claude/.credentials.json`), auto-refreshing if needed
    - Prefer refreshable Claude Code credentials over static `ANTHROPIC_TOKEN` to avoid shadowing
    - Return `None` if no token found
    - Do NOT resolve `primaryApiKey` from `~/.claude.json` as a native Anthropic token

19. **Run OAuth Setup Token (`run_oauth_setup_token`)**
    - Check if `claude` CLI is installed via `shutil.which("claude")`
    - Raise `FileNotFoundError` with message containing "claude" and "CLI" and "not installed" if not found
    - Run `subprocess.run(["claude", "setup-token"])` to launch interactive setup
    - After subprocess completes, attempt to resolve a token from credential files or env vars
    - Return the token or `None`
    - Catch `KeyboardInterrupt` and return `None` gracefully

20. **PKCE Code Generation (`_generate_pkce`)**
    - Generate a random `code_verifier` (43-128 characters, unreserved characters)
    - Compute `code_challenge` as base64url(sha256(code_verifier))
    - Return tuple: `(code_verifier, code_challenge)`

21. **Hermes OAuth Login (Pure) (`run_hermes_oauth_login_pure`)**
    - Implement PKCE OAuth flow for Hermes-native login
    - Generate PKCE codes
    - Open browser to Anthropic OAuth authorization endpoint
    - Start local HTTP server to receive callback
    - Exchange authorization code for tokens
    - Return dict with: `access_token`, `refresh_token`, `expires_at_ms`
    - Return `None` on error or user cancellation

22. **Save Hermes OAuth Credentials (`_save_hermes_oauth_credentials`)**
    - Write to `~/.hermes/.anthropic_oauth.json`
    - Create parent directories if needed
    - Store: `access_token`, `refresh_token`, `expires_at_ms`

23. **Read Hermes OAuth Credentials (`read_hermes_oauth_credentials`)**
    - Read from `~/.hermes/.anthropic_oauth.json`
    - Return dict with keys: `access_token`, `refresh_token`, `expires_at_ms`
    - Return `None` if file doesn't exist

24. **Model Name Normalization (`normalize_model_name`)**
    - Strip `anthropic/` prefix if present
    - If `preserve_dots=False`, replace dots with hyphens (e.g., `claude-3.5-sonnet` → `claude-3-5-sonnet`)
    - If `preserve_dots=True`, keep dots as-is
    - Return the normalized name

25. **Tool ID Sanitization (`_sanitize_tool_id`)**
    - Remove or replace characters that Anthropic's API doesn't accept in tool call IDs
    - Return a sanitized string

26. **Convert OpenAI Image Part to Anthropic (`_convert_openai_image_part_to_anthropic`)**
    - Accept an OpenAI-style image block (dict with `type: "image_url"` and `image_url: {url: "..."}`)
    - Convert to Anthropic's image source format
    - Return `None` if conversion fails

27. **Convert Tools to Anthropic (`convert_tools_to_anthropic`)**
    - Accept a list of OpenAI-style tool definitions
    - Convert each to Anthropic format (name, description, input_schema)
    - Return list of converted tools

28. **Image Source from OpenAI URL (`_image_source_from_openai_url`)**
    - Accept an OpenAI-style image URL or data URL
    - Convert to Anthropic image source dict
    - Handle base64 data URLs, HTTP(S) URLs, and file URLs
    - Return dict with `type` and appropriate source fields

29. **Convert Content Part to Anthropic (`_convert_content_part_to_anthropic`)**
    - Accept a single OpenAI-style content part (text, image_url, tool_use, etc.)
    - Convert to Anthropic format
    - Return `None` if conversion fails

30. **Convert to Plain Data (`_to_plain_data`)**
    - Recursively convert SDK objects (e.g., Anthropic response objects) to plain Python dicts/lists
    - Handle circular references via `_path` set
    - Limit recursion depth via `_depth` parameter
    - Return plain Python data structures

31. **Extract Preserved Thinking Blocks (`_extract_preserved_thinking_blocks`)**
    - Check if message has a `_preserved_thinking_blocks` field
    - Return list of thinking blocks or empty list

32. **Convert Content to Anthropic (`_convert_content_to_anthropic`)**
    - Accept OpenAI-style multimodal content (string or list of parts)
    - Convert to Anthropic blocks format
    - Return converted content

33. **Convert Messages to Anthropic (`convert_messages_to_anthropic`)**
    - Accept list of OpenAI-format messages
    - Convert each message's role and content to Anthropic format
    - Handle system messages separately (return as first return value)
    - Convert tool_calls and tool results
    - Preserve thinking blocks if present
    - Return tuple: `(system_block, converted_messages_list)`

34. **Build Anthropic Kwargs (`build_anthropic_kwargs`)**
    - Accept model, messages, tools, max_tokens, reasoning_config, tool_choice, is_oauth, preserve_dots, context_length, base_url
    - Call `convert_messages_to_anthropic()` to get system and messages
    - Call `convert_tools_to_anthropic()` if tools provided
    - Build dict with: `model`, `messages`, `max_tokens`, `system`, `tools`, `tool_choice`
    - Add thinking/reasoning config if reasoning_config provided
    - Use `THINKING_BUDGET` and `ADAPTIVE_EFFORT_MAP` to map reasoning levels
    - Return complete kwargs dict for `anthropic.messages.create()`

35. **Normalize Anthropic Response (`normalize_anthropic_response`)**
    - Accept an Anthropic API response object
    - Convert to `SimpleNamespace` with fields: `choices`, `usage`, etc.
    - Extract text content and tool calls from response blocks
    - If `strip_tool_prefix=True`, remove `anthropic_` prefix from tool use IDs
    - Return tuple: `(normalized_response, finish_reason_string)`

36. **Module Constants**
    - Define `THINKING_BUDGET = {"xhigh": 32000, "high": 16000, "medium": 8000, "low": 4000}`
    - Define `ADAPTIVE_EFFORT_MAP = {"xhigh": "max", "high": "high", "medium": "medium", "low": "low", "minimal": "low"}`

---

### Implementation Notes

- **Imports**: Use `anthropic`, `os`, `json`, `time`, `urllib`, `subprocess`, `shutil`, `hashlib`, `base64`, `pathlib.Path`, `types.SimpleNamespace`, `typing` as needed
- **Error Handling**: Catch and handle network errors, file I/O errors, and subprocess errors gracefully
- **File Paths**: Always use `Path.home()` for home directory resolution to support testing with monkeypatch
- **OAuth Flow**: Implement PKCE for Hermes-native OAuth; use `refresh_anthropic_oauth_pure()` for token refresh
- **Message Conversion**: Preserve all content types (text, images, tool calls); handle multimodal messages
- **Response Normalization**: Extract finish reason, tool calls, and text from Anthropic response blocks

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `def _get_anthropic_max_output(model: str) -> int`
- `def _is_oauth_token(key: str) -> bool`
- `def build_anthropic_client(api_key: str, base_url: str = None)`
- `def read_claude_code_credentials() -> Optional[Dict[str, Any]]`
- `def is_claude_code_token_valid(creds: Dict[str, Any]) -> bool`
- `def _refresh_oauth_token(creds: Dict[str, Any]) -> Optional[str]`
- `def _write_claude_code_credentials(access_token: str, refresh_token: str, expires_at_ms: int, scopes: Optional[list] = None) -> None`
- `def get_anthropic_token_source(token: Optional[str] = None) -> str`
- `def resolve_anthropic_token() -> Optional[str]`
- `def run_oauth_setup_token() -> Optional[str]`
- `def normalize_model_name(model: str, preserve_dots: bool = False) -> str`
- `def convert_tools_to_anthropic(tools: List[Dict]) -> List[Dict]`
- `def _to_plain_data(value: Any, _depth: int = 0, _path: Optional[set] = None) -> Any`
- `def convert_messages_to_anthropic(messages: List[Dict], base_url: str | None = None) -> Tuple[Optional[Any], List[Dict]]`
- `def build_anthropic_kwargs(model: str, messages: List[Dict], tools: Optional[List[Dict]], max_tokens: Optional[int], reasoning_config: Optional[Dict[str, Any]], tool_choice: Optional[str] = None, is_oauth: bool = False, preserve_dots: bool = False, context_length: Optional[int] = None, base_url: str | None = None) -> Dict[str, Any]`
- `def normalize_anthropic_response(response, strip_tool_prefix: bool = False) -> Tuple[SimpleNamespace, str]`

## Environment Configuration

### Python Version

Python 3.10

### Workspace

- Put the implementation directly under `/home/ubuntu/workspace`.
- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.
- Hidden tests import the solution as top-level module file(s): `anthropic_adapter.py`.

### External Dependencies

No third-party runtime dependencies were detected from the source file.

### Internal Helpers (implement locally)

These names came from repo-internal modules. Do NOT try to `pip install` them.

- `hermes_constants`: repo-private constants or lightweight helper values; the original code imported `get_hermes_home` from `hermes_constants`. Recreate the needed behavior locally.


## Project Directory Structure

```
workspace/
├── pyproject.toml
├── anthropic_adapter.py
```

## API Usage Guide

### 1. Module Import

```python
from anthropic_adapter import (
    build_anthropic_client,
    read_claude_code_credentials,
    read_claude_managed_key,
    is_claude_code_token_valid,
    refresh_anthropic_oauth_pure,
    get_anthropic_token_source,
    resolve_anthropic_token,
    run_oauth_setup_token,
    run_hermes_oauth_login_pure,
    read_hermes_oauth_credentials,
    normalize_model_name,
    convert_tools_to_anthropic,
    convert_messages_to_anthropic,
    build_anthropic_kwargs,
    normalize_anthropic_response,
    THINKING_BUDGET,
    ADAPTIVE_EFFORT_MAP,
)
```

### 2. `build_anthropic_client` Function

Create an Anthropic client, auto-detecting setup-tokens vs API keys.

Returns an anthropic.Anthropic instance.

```python
def build_anthropic_client(api_key: str, base_url: str = None):
```

**Parameters:**
- `api_key: str`
- `base_url: str = None`

### 3. `read_claude_code_credentials` Function

Read refreshable Claude Code OAuth credentials from ~/.claude/.credentials.json.

This intentionally excludes ~/.claude.json primaryApiKey. Opencode's
subscription flow is OAuth/setup-token based with refreshable credentials,
and native direct Anthropic provider usage should follow that path rather
than auto-detecting Claude's first-party managed key.

Returns dict with {accessToken, refreshToken?, expiresAt?} or None.

```python
def read_claude_code_credentials() -> Optional[Dict[str, Any]]:
```

**Returns:** `Optional[Dict[str, Any]]`

### 4. `read_claude_managed_key` Function

Read Claude's native managed key from ~/.claude.json for diagnostics only.

```python
def read_claude_managed_key() -> Optional[str]:
```

**Returns:** `Optional[str]`

### 5. `is_claude_code_token_valid` Function

Check if Claude Code credentials have a non-expired access token.

```python
def is_claude_code_token_valid(creds: Dict[str, Any]) -> bool:
```

**Parameters:**
- `creds: Dict[str, Any]`

**Returns:** `bool`

### 6. `refresh_anthropic_oauth_pure` Function

Refresh an Anthropic OAuth token without mutating local credential files.

```python
def refresh_anthropic_oauth_pure(refresh_token: str, use_json: bool = False) -> Dict[str, Any]:
```

**Parameters:**
- `refresh_token: str`
- `use_json: bool = False`

**Returns:** `Dict[str, Any]`

### 7. `get_anthropic_token_source` Function

Best-effort source classification for an Anthropic credential token.

```python
def get_anthropic_token_source(token: Optional[str] = None) -> str:
```

**Parameters:**
- `token: Optional[str] = None`

**Returns:** `str`

### 8. `resolve_anthropic_token` Function

Resolve an Anthropic token from all available sources.

Priority:
  1. ANTHROPIC_TOKEN env var (OAuth/setup token saved by Hermes)
  2. CLAUDE_CODE_OAUTH_TOKEN env var
  3. Claude Code credentials (~/.claude.json or ~/.claude/.credentials.json)
     — with automatic refresh if expired and a refresh token is available
  4. ANTHROPIC_API_KEY env var (regular API key, or legacy fallback)

Returns the token string or None.

```python
def resolve_anthropic_token() -> Optional[str]:
```

**Returns:** `Optional[str]`

### 9. `run_oauth_setup_token` Function

Run 'claude setup-token' interactively and return the resulting token.

Checks multiple sources after the subprocess completes:
  1. Claude Code credential files (may be written by the subprocess)
  2. CLAUDE_CODE_OAUTH_TOKEN / ANTHROPIC_TOKEN env vars

Returns the token string, or None if no credentials were obtained.
Raises FileNotFoundError if the 'claude' CLI is not installed.

```python
def run_oauth_setup_token() -> Optional[str]:
```

**Returns:** `Optional[str]`

### 10. `run_hermes_oauth_login_pure` Function

Run Hermes-native OAuth PKCE flow and return credential state.

```python
def run_hermes_oauth_login_pure() -> Optional[Dict[str, Any]]:
```

**Returns:** `Optional[Dict[str, Any]]`

### 11. `read_hermes_oauth_credentials` Function

Read Hermes-managed OAuth credentials from ~/.hermes/.anthropic_oauth.json.

```python
def read_hermes_oauth_credentials() -> Optional[Dict[str, Any]]:
```

**Returns:** `Optional[Dict[str, Any]]`

### 12. `normalize_model_name` Function

Normalize a model name for the Anthropic API.

- Strips 'anthropic/' prefix (OpenRouter format, case-insensitive)
- Converts dots to hyphens in version numbers (OpenRouter uses dots,
  Anthropic uses hyphens: claude-opus-4.6 → claude-opus-4-6), unless
  preserve_dots is True (e.g. for Alibaba/DashScope: qwen3.5-plus).

```python
def normalize_model_name(model: str, preserve_dots: bool = False) -> str:
```

**Parameters:**
- `model: str`
- `preserve_dots: bool = False`

**Returns:** `str`

### 13. `convert_tools_to_anthropic` Function

Convert OpenAI tool definitions to Anthropic format.

```python
def convert_tools_to_anthropic(tools: List[Dict]) -> List[Dict]:
```

**Parameters:**
- `tools: List[Dict]`

**Returns:** `List[Dict]`

### 14. `convert_messages_to_anthropic` Function

Convert OpenAI-format messages to Anthropic format.

Returns (system_prompt, anthropic_messages).
System messages are extracted since Anthropic takes them as a separate param.
system_prompt is a string or list of content blocks (when cache_control present).

When *base_url* is provided and points to a third-party Anthropic-compatible
endpoint, all thinking block signatures are stripped.  Signatures are
Anthropic-proprietary — third-party endpoints cannot validate them and will
reject them with HTTP 400 "Invalid signature in thinking block".

```python
def convert_messages_to_anthropic(messages: List[Dict], base_url: str | None = None) -> Tuple[Optional[Any], List[Dict]]:
```

**Parameters:**
- `messages: List[Dict]`
- `base_url: str | None = None`

**Returns:** `Tuple[Optional[Any], List[Dict]]`

### 15. `build_anthropic_kwargs` Function

Build kwargs for anthropic.messages.create().

When *max_tokens* is None, the model's native output limit is used
(e.g. 128K for Opus 4.6, 64K for Sonnet 4.6).  If *context_length*
is provided, the effective limit is clamped so it doesn't exceed
the context window.

When *is_oauth* is True, applies Claude Code compatibility transforms:
system prompt prefix, tool name prefixing, and prompt sanitization.

When *preserve_dots* is True, model name dots are not converted to hyphens
(for Alibaba/DashScope anthropic-compatible endpoints: qwen3.5-plus).

When *base_url* points to a third-party Anthropic-compatible endpoint,
thinking block signatures are stripped (they are Anthropic-proprietary).

```python
def build_anthropic_kwargs(model: str, messages: List[Dict], tools: Optional[List[Dict]], max_tokens: Optional[int], reasoning_config: Optional[Dict[str, Any]], tool_choice: Optional[str] = None, is_oauth: bool = False, preserve_dots: bool = False, context_length: Optional[int] = None, base_url: str | None = None) -> Dict[str, Any]:
```

**Parameters:**
- `model: str`
- `messages: List[Dict]`
- `tools: Optional[List[Dict]]`
- `max_tokens: Optional[int]`
- `reasoning_config: Optional[Dict[str, Any]]`
- `tool_choice: Optional[str] = None`
- `is_oauth: bool = False`
- `preserve_dots: bool = False`
- `context_length: Optional[int] = None`
- `base_url: str | None = None`

**Returns:** `Dict[str, Any]`

### 16. `normalize_anthropic_response` Function

Normalize Anthropic response to match the shape expected by AIAgent.

Returns (assistant_message, finish_reason) where assistant_message has
.content, .tool_calls, and .reasoning attributes.

When *strip_tool_prefix* is True, removes the ``mcp_`` prefix that was
added to tool names for OAuth Claude Code compatibility.

```python
def normalize_anthropic_response(response, strip_tool_prefix: bool = False) -> Tuple[SimpleNamespace, str]:
```

**Parameters:**
- `response`
- `strip_tool_prefix: bool = False`

**Returns:** `Tuple[SimpleNamespace, str]`

### 17. Constants and Configuration

```python
THINKING_BUDGET = {"xhigh": 32000, "high": 16000, "medium": 8000, "low": 4000}
ADAPTIVE_EFFORT_MAP = {
    "xhigh": "max",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "minimal": "low",
}
_ANTHROPIC_OUTPUT_LIMITS = ...  # 543 chars
_ANTHROPIC_DEFAULT_OUTPUT_LIMIT = 128_000
_COMMON_BETAS = [
    "interleaved-thinking-2025-05-14",
    "fine-grained-tool-streaming-2025-05-14",
]
_OAUTH_ONLY_BETAS = [
    "claude-code-20250219",
    "oauth-2025-04-20",
]
_CLAUDE_CODE_VERSION_FALLBACK = "2.1.74"
_CLAUDE_CODE_SYSTEM_PREFIX = "You are Claude Code, Anthropic's official CLI for Claude."
_MCP_TOOL_PREFIX = "mcp_"
_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_OAUTH_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
_OAUTH_REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
_OAUTH_SCOPES = "org:create_api_key user:profile user:inference"
_HERMES_OAUTH_FILE = get_hermes_home() / ".anthropic_oauth.json"
```

## Implementation Notes

### Node 1: OAuth Token Detection

`_is_oauth_token(key: str) -> bool` must identify tokens that are NOT regular Console API keys. The function returns `True` for:
- Setup tokens with prefix `sk-ant-oat01-`
- Managed keys (e.g., `ou1R1z-ft0A-bDeZ9wAA`) from `~/.claude.json`
- JWT tokens (e.g., `eyJhbGciOiJSUzI1NiJ9.test`)
- Any non-empty token that is not a regular API key (prefix `sk-ant-api03-`)

Returns `False` for empty strings and regular API keys with `sk-ant-api03-` prefix.

### Node 2: Anthropic Client Construction

`build_anthropic_client(api_key: str, base_url: str = None)` must:
- Detect whether the credential is an OAuth token or regular API key using `_is_oauth_token()`
- For OAuth tokens: pass as `auth_token` parameter to `Anthropic()` constructor
- For regular API keys: pass as `api_key` parameter
- Always include `_COMMON_BETAS` (`interleaved-thinking-2025-05-14`, `fine-grained-tool-streaming-2025-05-14`) in `default_headers["anthropic-beta"]`
- For OAuth tokens: additionally include `_OAUTH_ONLY_BETAS` (`claude-code-20250219`, `oauth-2025-04-20`)
- Pass `base_url` parameter if provided
- For third-party Anthropic-compatible endpoints (detected via `_is_third_party_anthropic_endpoint()`): use `auth_token` with Bearer auth instead of `api_key`

### Node 3: Claude Code Credentials File Format

`read_claude_code_credentials() -> Optional[Dict[str, Any]]` reads from `~/.claude/.credentials.json` and expects structure:
```json
{
  "claudeAiOauth": {
    "accessToken": "sk-ant-oat01-...",
    "refreshToken": "sk-ant-oat01-...",
    "expiresAt": <milliseconds since epoch>
  }
}
```

Returns `None` if:
- File does not exist
- `claudeAiOauth` key is missing
- `accessToken` is empty or missing
- File cannot be parsed

Does NOT resolve `primaryApiKey` from `~/.claude.json` as a native Anthropic token.

### Node 4: Token Validity Checking

`is_claude_code_token_valid(creds: Dict[str, Any]) -> bool` returns `True` if:
- `accessToken` field exists and is non-empty
- AND either `expiresAt` is 0 (no expiry) OR current time in milliseconds is less than `expiresAt`

Returns `False` if token is expired (current time >= `expiresAt` when `expiresAt` > 0).

### Node 5: OAuth Token Refresh Flow

`_refresh_oauth_token(creds: Dict[str, Any]) -> Optional[str]` must:
- Return `None` if `refreshToken` is empty or missing
- POST to `_OAUTH_TOKEN_URL` (`https://console.anthropic.com/v1/oauth/token`) with `refresh_token` from creds
- On success, call `_write_claude_code_credentials()` with new `access_token`, `refresh_token`, and `expires_in` (converted to milliseconds)
- Return the new access token string
- Return `None` on any network or parsing error (catch all exceptions)

`refresh_anthropic_oauth_pure(refresh_token: str, use_json: bool = False) -> Dict[str, Any]` performs the same POST without mutating local files, returning the full response dict.

### Node 6: Credential File Writing

`_write_claude_code_credentials(access_token: str, refresh_token: str, expires_at_ms: int, scopes: Optional[list] = None)` must:
- Write to `~/.claude/.credentials.json`
- Create parent directories if needed
- Preserve any existing top-level keys in the file (merge, not replace)
- Update/create the `claudeAiOauth` object with:
  - `accessToken`: the provided access token
  - `refreshToken`: the provided refresh token
  - `expiresAt`: the provided milliseconds value
  - `scopes`: optional list if provided

### Node 7: Token Resolution Priority Order

`resolve_anthropic_token() -> Optional[str]` resolves credentials in this order:
1. `ANTHROPIC_TOKEN` env var (if set and non-empty)
2. `ANTHROPIC_API_KEY` env var (if set and non-empty)
3. `CLAUDE_CODE_OAUTH_TOKEN` env var (if set and non-empty)
4. Claude Code credentials from `~/.claude/.credentials.json` (with auto-refresh if expired but has refresh token)
5. Return `None` if none found

Special rule: If `ANTHROPIC_TOKEN` is set AND Claude Code credentials exist with a refresh token, prefer the Claude Code credentials (they are refreshable). But if Claude Code credentials exist WITHOUT a refresh token (non-refreshable), keep the static `ANTHROPIC_TOKEN`.

Does NOT resolve `primaryApiKey` from `~/.claude.json` as a native Anthropic token.

### Node 8: Token Source Classification

`get_anthropic_token_source(token: Optional[str] = None) -> str` returns a best-effort string describing where a token came from (e.g., "ANTHROPIC_TOKEN", "ANTHROPIC_API_KEY", "Claude Code credentials", "~/.claude.json", etc.). If no token is provided, it should classify the currently resolved token.

### Node 9: Interactive OAuth Setup

`run_oauth_setup_token() -> Optional[str]` must:
- Check if `claude` CLI is installed via `shutil.which("claude")`
- Raise `FileNotFoundError` with message containing "claude" and "CLI" and "not installed" if not found
- Run `subprocess.run(["claude", "setup-token"])` to trigger interactive OAuth flow
- After subprocess completes, attempt to resolve a token from:
  - Claude Code credential files (`~/.claude/.credentials.json`)
  - `CLAUDE_CODE_OAUTH_TOKEN` env var
  - `ANTHROPIC_TOKEN` env var
- Return the resolved token or `None`
- Catch `KeyboardInterrupt` and return `None` gracefully

### Node 10: Model Name Normalization

`normalize_model_name(model: str, preserve_dots: bool = False) -> str` must:
- Strip `anthropic/` prefix if present (e.g., `anthropic/claude-sonnet-4-20250514` → `claude-sonnet-4-20250514`)
- Return the normalized model name

### Node 11: Hermes OAuth Credentials

`read_hermes_oauth_credentials() -> Optional[Dict[str, Any]]` reads from `_HERMES_OAUTH_FILE` (computed via `get_hermes_home() / ".anthropic_oauth.json"`).

`_save_hermes_oauth_credentials(access_token: str, refresh_token: str, expires_at_ms: int)` writes to the same location with structure matching Claude Code format.

`run_hermes_oauth_login_pure() -> Optional[Dict[str, Any]]` runs a PKCE-based OAuth flow using `_generate_pkce()` and returns credential state dict.

`_generate_pkce() -> tuple` returns `(code_verifier, code_challenge)` for S256 PKCE flow.

### Node 12: Third-Party Endpoint Detection

`_is_third_party_anthropic_endpoint(base_url: str | None) -> bool` returns `True` for non-Anthropic endpoints using the Anthropic Messages API (e.g., Minimax at `https://api.minimax.io/anthropic`).

`_requires_bearer_auth(base_url: str | None) -> bool` returns `True` for Anthropic-compatible providers that require Bearer auth (e.g., Minimax).

`_normalize_base_url_text(base_url) -> str` converts SDK/transport URL objects to plain strings for inspection.