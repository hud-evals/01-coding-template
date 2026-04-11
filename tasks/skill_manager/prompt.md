# skill-manager

## Overview

**skill-manager** is a Python library comprising 742 lines of code organized within a single source module (`skill_manager_tool`) that provides agent-managed skill creation, editing, and deletion capabilities. The library enables autonomous agents to convert successful procedural approaches into reusable, persistent skills stored in the `~/.hermes/skills/` directory. It supports operations on three categories of skills: bundled skills, hub-installed skills, and user-created skills, allowing agents to modify existing skill definitions alongside creating entirely new ones.

The module exposes 16 module-level functions that collectively implement the core skill management workflow. Rather than using class-based abstractions, the library adopts a functional programming approach, with all operations implemented as discrete, composable functions. This design facilitates straightforward integration into agent systems where individual skill operations can be invoked independently or sequenced as part of larger skill curation pipelines.

The skill-manager library serves as a critical component for systems requiring dynamic skill acquisition and refinement, enabling agents to autonomously build and maintain a growing repository of procedural knowledge without requiring manual intervention or external skill definition processes.

# Natural Language Instructions for Rebuilding skill-manager

## Implementation Constraints

- All code must live in `/home/ubuntu/workspace/skill_manager_tool.py` as a single module
- No external dependencies beyond Python stdlib (pathlib, re, yaml, tempfile, shutil)
- All 16 module-level functions must be implemented with exact signatures
- Module constants (MAX_NAME_LENGTH, SKILLS_DIR, etc.) must be defined at module level
- The module must import `get_hermes_home()` from a local utility or define a fallback
- All validation functions return `Optional[str]` (None if valid, error message if invalid)
- All action functions return `Dict[str, Any]` with at minimum `{"success": bool, ...}`
- File operations must be atomic where possible (write to temp file, then rename)
- Security scanning must prevent path traversal and validate all file operations

---

## Natural Language Instructions

### Step 1: Set Up Module Structure and Imports

Create `/home/ubuntu/workspace/skill_manager_tool.py` with the following structure:

1. Add module docstring: `"""Skill Manager Tool -- Agent-Managed Skill Creation & Editing\n\nAllows the agent to create, update, and delete skills, turning successful\napproaches into reusable procedural knowledge. New skills are created in\n~/.hermes/skills/. Existing skills (bundled, hub-installed, or user-created)\ncan be modified."""`

2. Import required modules:
   - `from pathlib import Path`
   - `import re`
   - `import yaml`
   - `import tempfile`
   - `import shutil`
   - `from typing import Optional, Dict, Any`

3. Define a helper function to get the Hermes home directory. If `get_hermes_home()` is not available from an external module, create a fallback that returns `Path.home() / ".hermes"`.

4. Define all module-level constants:
   - `HERMES_HOME = get_hermes_home()` (or fallback)
   - `SKILLS_DIR = HERMES_HOME / "skills"`
   - `MAX_NAME_LENGTH = 64`
   - `MAX_DESCRIPTION_LENGTH = 1024`
   - `MAX_SKILL_CONTENT_CHARS = 100_000`
   - `MAX_SKILL_FILE_BYTES = 1_048_576`
   - `VALID_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9._-]*$')`
   - `ALLOWED_SUBDIRS = {"references", "templates", "scripts", "assets"}`

---

### Step 2: Implement Validation Functions

### Behavioral Requirements

1. **`_validate_name(name: str) -> Optional[str]`**
   - Return `None` if the name is valid.
   - Return `"Skill name is required."` if name is empty or whitespace-only.
   - Return `f"Skill name exceeds {MAX_NAME_LENGTH} characters."` if name length exceeds MAX_NAME_LENGTH.
   - Return an error message containing `"Invalid skill name '<name>'"` if the name does not match VALID_NAME_RE (must start with alphanumeric, contain only lowercase letters, digits, dots, hyphens, underscores).
   - Accept names like `"my-skill"`, `"skill123"`, `"my_skill.v2"`, `"a"`.
   - Reject names like `"MySkill"` (uppercase), `"-invalid"` (starts with hyphen), `"skill/name"` (slash), `"skill name"` (space), `"skill@name"` (special char).

2. **`_validate_category(category: Optional[str]) -> Optional[str]`**
   - Return `None` if category is `None` or empty string.
   - Return `None` if category is a valid single directory segment (no slashes, no path traversal).
   - Return an error message containing `"Invalid category '<category>'"` if category contains `".."` (path traversal) or starts with `"/"` (absolute path).
   - Accept categories like `"devops"`, `"mlops-v2"`.
   - Reject categories like `"../escape"`, `"/tmp/escape"`.

3. **`_validate_frontmatter(content: str) -> Optional[str]`**
   - Return `"Content cannot be empty."` if content is empty or only whitespace.
   - Return `"SKILL.md must start with YAML frontmatter (---). See existing skills for format."` if content does not start with `---`.
   - Return `"SKILL.md frontmatter is not closed. Ensure you have a closing '---' line."` if the opening `---` is not followed by a closing `---`.
   - Parse the YAML between the `---` delimiters. If YAML parsing fails, return an error message containing `"YAML frontmatter parse error"`.
   - Return `"Frontmatter must include 'name' field."` if the parsed YAML does not have a `name` key.
   - Return `"Frontmatter must include 'description' field."` if the parsed YAML does not have a `description` key.
   - Return `"SKILL.md must have content after the frontmatter (instructions, procedures, etc.)."` if there is no non-whitespace content after the closing `---`.
   - Return `None` if all checks pass.

4. **`_validate_content_size(content: str, label: str = "SKILL.md") -> Optional[str]`**
   - Return `None` if the content length (in characters) does not exceed MAX_SKILL_CONTENT_CHARS.
   - Return an error message if content exceeds the limit, mentioning the label and the limit.

5. **`_validate_file_path(file_path: str) -> Optional[str]`**
   - Return `"file_path is required."` if file_path is empty.
   - Return `"Path traversal ('..') is not allowed."` if file_path contains `".."`.
   - Return an error message containing `"File must be under one of:"` and listing ALLOWED_SUBDIRS if the file_path does not start with one of the allowed subdirectories.
   - Return an error message containing `"Provide a file path, not just a directory"` and suggesting a format like `"'references/myfile.md'"` if file_path is a directory name only (e.g., `"references"` without a filename).
   - Return `None` if file_path is valid (e.g., `"references/api.md"`, `"templates/config.yaml"`, `"scripts/train.py"`, `"assets/image.png"`).

---

### Step 3: Implement Skill Discovery and Path Resolution

### Behavioral Requirements

6. **`_resolve_skill_dir(name: str, category: str = None) -> Path`**
   - If category is provided and non-empty, return `SKILLS_DIR / category / name`.
   - Otherwise, return `SKILLS_DIR / name`.
   - Do not create directories; only compute the path.

7. **`_find_skill(name: str) -> Optional[Dict[str, Any]]`**
   - Search for a skill with the given name across all skill directories (SKILLS_DIR and any other configured skill directories).
   - Return a dictionary with keys `"name"`, `"path"` (as Path object), and optionally `"category"` if the skill is in a category subdirectory.
   - Return `None` if the skill is not found.
   - The search should check both `SKILLS_DIR / name` and `SKILLS_DIR / <category> / name` for all subdirectories of SKILLS_DIR.

---

### Step 4: Implement File I/O and Security

### Behavioral Requirements

8. **`_atomic_write_text(file_path: Path, content: str, encoding: str = "utf-8") -> None`**
   - Write content to file_path atomically using a temporary file and rename.
   - Create parent directories if they do not exist.
   - Use the specified encoding (default UTF-8).
   - Raise an exception if the write fails.

9. **`_security_scan_skill(skill_dir: Path) -> Optional[str]`**
   - Scan a skill directory after a write operation.
   - Return `None` if the skill directory is safe.
   - Return an error string if any security issue is detected (e.g., suspicious file types, path traversal attempts in file names).
   - Check that all files in the skill directory are under allowed subdirectories or are named `SKILL.md`.
   - Reject files with suspicious extensions or names that suggest code injection or escape attempts.

---

### Step 5: Implement Core Skill Management Functions

### Behavioral Requirements

10. **`_create_skill(name: str, content: str, category: str = None) -> Dict[str, Any]`**
    - Validate the skill name using `_validate_name()`. If invalid, return `{"success": False, "error": "<error message>"}`.
    - Validate the category using `_validate_category()`. If invalid, return `{"success": False, "error": "<error message>"}`.
    - Validate the content using `_validate_frontmatter()`. If invalid, return `{"success": False, "error": "<error message>"}`.
    - Validate content size using `_validate_content_size()`. If too large, return `{"success": False, "error": "<error message>"}`.
    - Resolve the skill directory using `_resolve_skill_dir(name, category)`.
    - Check if the skill already exists. If it does, return `{"success": False, "error": "Skill '<name>' already exists. Use edit or patch to modify it."}`.
    - Create the skill directory and write the content to `SKILL.md` using `_atomic_write_text()`.
    - Run `_security_scan_skill()` on the new skill directory. If it returns an error, delete the directory and return `{"success": False, "error": "<scan error>"}`.
    - Return `{"success": True, "name": name, "path": str(skill_dir), "category": category}` (include category only if provided).

11. **`_edit_skill(name: str, content: str) -> Dict[str, Any]`**
    - Validate the content using `_validate_frontmatter()`. If invalid, return `{"success": False, "error": "<error message>"}`.
    - Validate content size using `_validate_content_size()`. If too large, return `{"success": False, "error": "<error message>"}`.
    - Find the skill using `_find_skill(name)`. If not found, return `{"success": False, "error": "Skill '<name>' not found."}`.
    - Read the current SKILL.md content and store it as a backup.
    - Write the new content to SKILL.md using `_atomic_write_text()`.
    - Run `_security_scan_skill()` on the skill directory. If it returns an error, restore the backup and return `{"success": False, "error": "<scan error>"}`.
    - Return `{"success": True, "name": name, "path": str(skill_dir)}`.

12. **`_patch_skill(name: str, old_string: str, new_string: str, file_path: str = None, replace_all: bool = False) -> Dict[str, Any]`**
    - Find the skill using `_find_skill(name)`. If not found, return `{"success": False, "error": "Skill '<name>' not found."}`.
    - If file_path is provided, validate it using `_validate_file_path()`. If invalid, return `{"success": False, "error": "<error message>"}`.
    - Determine the target file: if file_path is provided, use `skill_dir / file_path`; otherwise, use `skill_dir / "SKILL.md"`.
    - Read the current content of the target file.
    - Count occurrences of old_string in the content.
    - If old_string is not found, return `{"success": False, "error": "Could not find '<old_string>' in the file."}`.
    - If old_string appears more than once and replace_all is False, return `{"success": False, "error": "Found <count> matches for '<old_string>'. Use replace_all=True to replace all occurrences."}`.
    - Perform the replacement: if replace_all is True, replace all occurrences; otherwise, replace the first occurrence.
    - Write the updated content back to the file using `_atomic_write_text()`.
    - Run `_security_scan_skill()` on the skill directory. If it returns an error, restore the original content and return `{"success": False, "error": "<scan error>"}`.
    - Return `{"success": True, "name": name, "path": str(skill_dir), "replacements": <count>}`.

13. **`_delete_skill(name: str) -> Dict[str, Any]`**
    - Find the skill using `_find_skill(name)`. If not found, return `{"success": False, "error": "Skill '<name>' not found."}`.
    - Delete the entire skill directory using `shutil.rmtree()`.
    - Return `{"success": True, "name": name}`.

14. **`_write_file(name: str, file_path: str, file_content: str) -> Dict[str, Any]`**
    - Validate file_path using `_validate_file_path()`. If invalid, return `{"success": False, "error": "<error message>"}`.
    - Find the skill using `_find_skill(name)`. If not found, return `{"success": False, "error": "Skill '<name>' not found."}`.
    - Compute the full file path as `skill_dir / file_path`.
    - Check the size of file_content. If it exceeds MAX_SKILL_FILE_BYTES, return `{"success": False, "error": "File content exceeds <limit> bytes."}`.
    - Write the file content using `_atomic_write_text()`.
    - Run `_security_scan_skill()` on the skill directory. If it returns an error, delete the file and return `{"success": False, "error": "<scan error>"}`.
    - Return `{"success": True, "name": name, "file_path": file_path, "path": str(skill_dir)}`.

15. **`_remove_file(name: str, file_path: str) -> Dict[str, Any]`**
    - Validate file_path using `_validate_file_path()`. If invalid, return `{"success": False, "error": "<error message>"}`.
    - Find the skill using `_find_skill(name)`. If not found, return `{"success": False, "error": "Skill '<name>' not found."}`.
    - Compute the full file path as `skill_dir / file_path`.
    - Check if the file exists. If not, return `{"success": False, "error": "File '<file_path>' not found in skill '<name>'."}`.
    - Delete the file using `Path.unlink()`.
    - Return `{"success": True, "name": name, "file_path": file_path, "path": str(skill_dir)}`.

---

### Step 6: Implement the Main Dispatcher Function

### Behavioral Requirements

16. **`skill_manage(action: str, name: str, content: str = None, category: str = None, file_path: str = None, file_content: str = None, old_string: str = None, new_string: str = None, replace_all: bool = False) -> str`**
    - This is the main entry point for skill management operations.
    - Dispatch to the appropriate handler based on the action parameter:
      - `"create"`: Call `_create_skill(name, content, category)`.
      - `"edit"`: Call `_edit_skill(name, content)`.
      - `"patch"`: Call `_patch_skill(name, old_string, new_string, file_path, replace_all)`.
      - `"delete"`: Call `_delete_skill(name)`.
      - `"write_file"`: Call `_write_file(name, file_path, file_content)`.
      - `"remove_file"`: Call `_remove_file(name, file_path)`.
    - If action is not recognized, return a JSON string with `{"success": False, "error": "Unknown action '<action>'"}`.
    - Convert the result dictionary to a JSON string and return it.
    - All error handling and validation is delegated to the action handlers.

---

### Step 7: Testing and Validation

1. Ensure all functions are defined at module level (not nested).
2. Ensure all constants are defined at module level.
3. Test that the module can be imported as `from skill_manager_tool import *` and all required symbols are available.
4. Verify that all function signatures match the EXACT API specification (parameter names, types, defaults, return types).
5. Run the provided test suite to validate behavior.
6. Ensure that all error messages match the expected strings in the tests (case-sensitive where applicable).
7. Verify that file operations are atomic and that security scanning prevents path traversal and code injection.

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `def _validate_name(name: str) -> Optional[str]`
- `def _validate_category(category: Optional[str]) -> Optional[str]`
- `def _validate_frontmatter(content: str) -> Optional[str]`
- `def _validate_file_path(file_path: str) -> Optional[str]`
- `def _create_skill(name: str, content: str, category: str = None) -> Dict[str, Any]`
- `def _edit_skill(name: str, content: str) -> Dict[str, Any]`
- `def _patch_skill(name: str, old_string: str, new_string: str, file_path: str = None, replace_all: bool = False) -> Dict[str, Any]`
- `def _delete_skill(name: str) -> Dict[str, Any]`
- `def _write_file(name: str, file_path: str, file_content: str) -> Dict[str, Any]`
- `def _remove_file(name: str, file_path: str) -> Dict[str, Any]`
- `def skill_manage(action: str, name: str, content: str = None, category: str = None, file_path: str = None, file_content: str = None, old_string: str = None, new_string: str = None, replace_all: bool = False) -> str`
- `MAX_NAME_LENGTH`

## Environment Configuration

### Python Version

Python >=3.11

### Workspace

- Put the implementation directly under `/home/ubuntu/workspace`.
- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.
- Hidden tests import the solution as top-level module file(s): `skill_manager_tool.py`.

### External Dependencies

Only use pip-installable packages for the external dependencies below.
```
yaml
```

### Internal Helpers (implement locally)

These names came from repo-internal modules. Do NOT try to `pip install` them.

- `agent.prompt_builder`: repo-private helper module; the original code imported `clear_skills_system_prompt_cache` from `agent.prompt_builder`. Recreate the needed behavior locally.
- `agent.skill_utils`: repo-private helper module; the original code imported `get_all_skills_dirs` from `agent.skill_utils`. Recreate the needed behavior locally.
- `hermes_constants`: repo-private constants or lightweight helper values; the original code imported `get_hermes_home` from `hermes_constants`. Recreate the needed behavior locally.
- `tools.fuzzy_match`: repo-private helper module; the original code imported `fuzzy_find_and_replace` from `tools.fuzzy_match`. Recreate the needed behavior locally.
- `tools.registry`: repo-private helper module; the original code imported `registry`, `tool_error` from `tools.registry`. Recreate the needed behavior locally.
- `tools.skills_guard`: repo-private helper module; the original code imported `format_scan_report`, `scan_skill`, `should_allow_install` from `tools.skills_guard`. Recreate the needed behavior locally.


## Project Directory Structure

```
workspace/
├── pyproject.toml
├── skill_manager_tool.py
```

## API Usage Guide

### 1. Module Import

```python
from skill_manager_tool import (
    skill_manage,
    HERMES_HOME,
    SKILLS_DIR,
    MAX_NAME_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_SKILL_CONTENT_CHARS,
    MAX_SKILL_FILE_BYTES,
    VALID_NAME_RE,
    ALLOWED_SUBDIRS,
    SKILL_MANAGE_SCHEMA,
)
```

### 2. `skill_manage` Function

Manage user-created skills. Dispatches to the appropriate action handler.

Returns JSON string with results.

```python
def skill_manage(action: str, name: str, content: str = None, category: str = None, file_path: str = None, file_content: str = None, old_string: str = None, new_string: str = None, replace_all: bool = False) -> str:
```

**Parameters:**
- `action: str`
- `name: str`
- `content: str = None`
- `category: str = None`
- `file_path: str = None`
- `file_content: str = None`
- `old_string: str = None`
- `new_string: str = None`
- `replace_all: bool = False`

**Returns:** `str`

### 3. Constants and Configuration

```python
HERMES_HOME = get_hermes_home()
SKILLS_DIR = HERMES_HOME / "skills"
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_SKILL_CONTENT_CHARS = 100_000
MAX_SKILL_FILE_BYTES = 1_048_576
VALID_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
ALLOWED_SUBDIRS = {"references", "templates", "scripts", "assets"}
SKILL_MANAGE_SCHEMA = ...  # 4059 chars
```

## Implementation Notes

### Node 1: Name Validation (_validate_name)
- Returns `None` if name is valid, otherwise returns an error message string
- Name must not be empty; empty string returns `"Skill name is required."`
- Name must not exceed `MAX_NAME_LENGTH` (64 characters); exceeding returns `f"Skill name exceeds {MAX_NAME_LENGTH} characters."`
- Name must match `VALID_NAME_RE` pattern (`^[a-z0-9][a-z0-9._-]*$`); invalid names return error message containing `"Invalid skill name '<name>'"`
- Pattern requires lowercase alphanumeric start, followed by lowercase alphanumeric, dots, underscores, or hyphens
- Uppercase letters, spaces, slashes, and special characters like `@` are rejected

### Node 2: Category Validation (_validate_category)
- Returns `None` if category is valid or absent
- `None` and empty string `""` are both valid (optional category)
- Category must be a single directory segment (no path separators)
- Path traversal attempts like `"../escape"` are rejected with error containing `"Invalid category '<category>'"`
- Absolute paths like `"/tmp/escape"` are rejected with same error format
- Valid categories follow similar naming rules to skills (e.g., `"devops"`, `"mlops-v2"`)

### Node 3: Frontmatter Validation (_validate_frontmatter)
- Returns `None` if content is valid, otherwise returns an error message string
- Content cannot be empty or whitespace-only; returns `"Content cannot be empty."`
- Content must start with YAML frontmatter delimited by `---` lines; missing opening returns `"SKILL.md must start with YAML frontmatter (---). See existing skills for format."`
- Frontmatter must be properly closed with a second `---` line; unclosed returns `"SKILL.md frontmatter is not closed. Ensure you have a closing '---' line."`
- Frontmatter must include required `name` field; missing returns `"Frontmatter must include 'name' field."`
- Frontmatter must include required `description` field; missing returns `"Frontmatter must include 'description' field."`
- Content after frontmatter is required (body); missing returns `"SKILL.md must have content after the frontmatter (instructions, procedures, etc.)."`
- YAML parsing errors return message containing `"YAML frontmatter parse error"`

### Node 4: File Path Validation (_validate_file_path)
- Returns `None` if path is valid, otherwise returns an error message string
- Path cannot be empty; returns `"file_path is required."`
- Path must be under one of `ALLOWED_SUBDIRS` (`{"references", "templates", "scripts", "assets"}`); invalid subdirs return error containing `"File must be under one of:"` and the invalid path
- Path traversal using `".."` is blocked; returns `"Path traversal ('..') is not allowed."`
- Directory-only paths (e.g., `"references"` without filename) are rejected with error containing `"Provide a file path, not just a directory"` and example like `"'references/myfile.md'"`
- Root-level files (no subdirectory prefix) are rejected with error containing `"File must be under one of:"`
- Valid paths include `"references/api.md"`, `"templates/config.yaml"`, `"scripts/train.py"`, `"assets/image.png"`

### Node 5: Skill Creation (_create_skill)
- Signature: `_create_skill(name: str, content: str, category: str = None) -> Dict[str, Any]`
- Returns dict with `"success"` boolean key
- On success: `"success"` is `True`, skill directory is created at `SKILLS_DIR / name` or `SKILLS_DIR / category / name` if category provided, `SKILL.md` file is written with provided content, result includes `"category"` key if category was used
- On failure: `"success"` is `False`, result includes `"error"` key with error message
- Validates name using `_validate_name`; invalid name returns failure
- Validates content using `_validate_frontmatter`; invalid content returns failure
- Validates category using `_validate_category`; invalid category returns failure with error message containing `"Invalid category '<category>'"`
- Duplicate skill names are blocked; returns failure with error containing `"already exists"`
- Directory structure is created as needed (parent directories created if necessary)

### Node 6: Skill Editing (_edit_skill)
- Signature: `_edit_skill(name: str, content: str) -> Dict[str, Any]`
- Returns dict with `"success"` boolean key
- Performs full rewrite of `SKILL.md` file for existing skill
- On success: `"success"` is `True`, `SKILL.md` is completely replaced with new content
- On failure: `"success"` is `False`, result includes `"error"` key
- Skill must exist; nonexistent skill returns failure with error containing `"not found"`
- Content is validated using `_validate_frontmatter`; invalid content returns failure without modifying original file
- Original content is preserved if validation fails

### Node 7: Skill Patching (_patch_skill)
- Signature: `_patch_skill(name: str, old_string: str, new_string: str, file_path: str = None, replace_all: bool = False) -> Dict[str, Any]`
- Returns dict with `"success"` boolean key
- Performs targeted find-and-replace within a skill file
- Default target is `SKILL.md`; `file_path` parameter allows patching supporting files (e.g., `"references/api.md"`)
- `replace_all=False` (default): requires exactly one match; multiple matches return failure with error containing `"match"` (case-insensitive)
- `replace_all=True`: replaces all occurrences of `old_string` with `new_string`
- On success: `"success"` is `True`, file is updated with replacement
- On failure: `"success"` is `False`, result includes `"error"` key
- Nonexistent `old_string` returns failure with error containing `"not found"` or `"could not find"` (case-insensitive)
- Skill must exist; nonexistent skill returns failure with `"success"` as `False`

### Node 8: Skill Deletion (_delete_skill)
- Signature: `_delete_skill(name: str) -> Dict[str, Any]`
- Returns dict with `"success"` boolean key
- On success: `"success"` is `True`, entire skill directory is removed
- Skill directory is located using `_find_skill` (searches across all skill directories including categorized ones)
- On success, skill directory no longer exists on filesystem

### Node 9: Supporting File Operations (_write_file, _remove_file)
- `_write_file(name: str, file_path: str, file_content: str) -> Dict[str, Any]`: adds or overwrites a supporting file within skill directory
- `_remove_file(name: str, file_path: str) -> Dict[str, Any]`: removes a supporting file from skill directory
- Both return dict with `"success"` boolean key
- `file_path` is validated using `_validate_file_path`; must be under `ALLOWED_SUBDIRS`
- Files are created/removed relative to the skill's root directory
- Both operations require skill to exist

### Node 10: Skill Discovery (_find_skill)
- Signature: `_find_skill(name: str) -> Optional[Dict[str, Any]]`
- Searches for skill by name across all skill directories
- Returns dict with skill metadata if found, `None` if not found
- Searches both root-level skills and categorized skills (e.g., `SKILLS_DIR / category / name`)
- Used by edit, patch, delete, and file operations to locate target skill

### Node 11: Directory Resolution (_resolve_skill_dir)
- Signature: `_resolve_skill_dir(name: str, category: str = None) -> Path`
- Builds directory path for a new skill
- Without category: returns `SKILLS_DIR / name`
- With category: returns `SKILLS_DIR / category / name`
- Does not create directories; only computes path

### Node 12: Atomic File Writing (_atomic_write_text)
- Signature: `_atomic_write_text(file_path: Path, content: str, encoding: str = "utf-8") -> None`
- Atomically writes text content to file
- Default encoding is UTF-8
- Creates parent directories as needed
- Ensures file write is atomic (not partially written on failure)

### Node 13: Security Scanning (_security_scan_skill)
- Signature: `_security_scan_skill(skill_dir: Path) -> Optional[str]`
- Scans skill directory after write operation
- Returns error string if security issue detected, `None` if safe
- Called after skill creation/modification to validate safety

### Node 14: Main Dispatcher (skill_manage)
- Signature: `skill_manage(action: str, name: str, content: str = None, category: str = None, file_path: str = None, file_content: str = None, old_string: str = None, new_string: str = None, replace_all: bool = False) -> str`
- Routes to appropriate handler based on `action` parameter
- Returns string result (JSON-serialized dict or error message)
- Supports actions: `"create"`, `"edit"`, `"patch"`, `"delete"`, `"write_file"`, `"remove_file"`
- Validates all inputs before dispatching to handlers

### Node 15: Constants and Limits
- `HERMES_HOME`: base directory from `get_hermes_home()`
- `SKILLS_DIR`: `HERMES_HOME / "skills"` - root directory for all skills
- `MAX_NAME_LENGTH`: 64 characters
- `MAX_DESCRIPTION_LENGTH`: 1024 characters
- `MAX_SKILL_CONTENT_CHARS`: 100,000 characters for SKILL.md content
- `MAX_SKILL_FILE_BYTES`: 1,048,576 bytes (1 MB) for individual files
- `VALID_NAME_RE`: `^[a-z0-9][a-z0-9._-]*$` - lowercase alphanumeric start, then alphanumeric/dots/underscores/hyphens
- `ALLOWED_SUBDIRS`: `{"references", "templates", "scripts", "assets"}` - only valid subdirectories for supporting files