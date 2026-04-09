# Task: Build a Fuzzy Text Matching Module

Create a Python module at `/home/ubuntu/workspace/fuzzy_match.py` that implements a multi-strategy fuzzy find-and-replace system for text content.

This module is designed for robustly finding and replacing text in source code files, accommodating variations in whitespace, indentation, and escaping that are common in LLM-generated edits.

## Core API

### `fuzzy_find_and_replace(content, old_string, new_string, replace_all=False)`

The main entry point. Finds `old_string` in `content` using a chain of increasingly fuzzy matching strategies, and replaces it with `new_string`.

**Parameters:**
- `content` (str): The file content to search in
- `old_string` (str): The text to find
- `new_string` (str): The replacement text
- `replace_all` (bool): If `True`, replace all occurrences. If `False`, require the match to be unique (return an error if multiple matches found).

**Returns:** A tuple of `(new_content, match_count, error_message)`
- Success: `(modified_content, number_of_replacements, None)`
- Failure: `(original_content, 0, error_description)`

**Edge cases:**
- If `old_string` is empty, return error `"old_string cannot be empty"`
- If `old_string == new_string`, return error `"old_string and new_string are identical"`
- If no strategy finds a match, return error `"Could not find a match for old_string in the file"`
- If multiple matches are found and `replace_all=False`, return error containing `"Found {n} matches"` with advice to provide more context or use `replace_all=True`

## Matching Strategy Chain

The module must implement **8 matching strategies**, tried in order from most strict to most fuzzy. The first strategy that finds matches wins — no further strategies are attempted.

### Strategy 1: Exact Match
Direct `str.find()` string comparison. Find all occurrences of the pattern as-is.

### Strategy 2: Line-Trimmed
Strip leading and trailing whitespace from each line (both in the pattern and the content) before comparing. When a match is found in the normalized form, map the positions back to the original content so the replacement covers the correct character range.

### Strategy 3: Whitespace Normalized
Collapse multiple consecutive spaces and tabs into a single space (using regex `[ \t]+` → `' '`), preserving newlines. Find matches in the normalized content, then map positions back to the original.

### Strategy 4: Indentation Flexible
Strip all leading whitespace from each line (using `lstrip()`) before comparing. This ignores indentation differences entirely. Map matches back to original positions.

### Strategy 5: Escape Normalized
Convert literal escape sequences (`\\n` → newline, `\\t` → tab, `\\r` → carriage return) in the pattern, then do an exact search with the unescaped pattern. Skip this strategy if the pattern contains no escape sequences.

### Strategy 6: Trimmed Boundary
Trim whitespace from only the first and last lines of the pattern (and corresponding content blocks). Leave middle lines untouched. Compare blocks of the same line count.

### Strategy 7: Block Anchor
Anchor matching on the first and last lines of the pattern:
1. Find all positions where the first line (stripped) and last line (stripped) of the pattern match the content
2. For each candidate, compute similarity of the middle lines using `SequenceMatcher.ratio()`
3. Use a threshold of `0.10` if there's only one candidate (maximum flexibility), or `0.30` if there are multiple candidates
4. If the pattern has only 2 lines, similarity is automatically `1.0`

Before comparing, normalize both content and pattern through a Unicode normalization step that converts:
- Smart double quotes (`\u201c`, `\u201d`) → `"`
- Smart single quotes (`\u2018`, `\u2019`) → `'`
- Em dash (`\u2014`) → `--`, en dash (`\u2013`) → `-`
- Ellipsis (`\u2026`) → `...`
- Non-breaking space (`\u00a0`) → ` `

Use the normalized text for matching logic but the original text for calculating character positions.

### Strategy 8: Context-Aware
Sliding window line-by-line similarity:
1. For each possible position in the content, compare the block of N lines against the pattern's N lines
2. For each line pair, compute `SequenceMatcher.ratio()` on the stripped lines
3. A line is considered a "high similarity" match if ratio >= `0.80`
4. The block matches if at least 50% of lines have high similarity

## Replacement Logic

When replacing, if there are multiple matches, sort them by position descending and replace from end to start. This preserves the positions of earlier matches.

## Position Mapping Helpers

Several strategies work by normalizing both content and pattern, finding matches in the normalized form, then mapping positions back to the original content. You'll need helpers for:

1. **Line-based position calculation**: Given a list of content lines and a start/end line index, calculate the character positions in the original string. Account for newline characters between lines. Clamp the end position to the content length.

2. **Normalized line matching**: Given original content lines, normalized content lines, and a normalized pattern, slide the pattern over the normalized content lines. When a block matches, use the original lines to calculate character positions.

3. **Character-level position mapping** (for whitespace normalization): Build a bidirectional mapping between character positions in the original and normalized strings, then translate match positions from normalized back to original coordinates.

## Dependencies

Only use the Python standard library:
- `re` for regex operations
- `difflib.SequenceMatcher` for similarity computation
- `typing` for type annotations

No external packages.

## File Structure

The entire implementation should be in a single file `/home/ubuntu/workspace/fuzzy_match.py`. It must be importable:

```python
from fuzzy_match import fuzzy_find_and_replace
```
