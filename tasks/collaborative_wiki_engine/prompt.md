# Collaborative Markdown Wiki Engine — Ultra-Extreme Systems Specification

## 📊 1. Mission Overview
You are a Lead Systems Engineer tasked with architecting a production-grade, distributed-resilient **Collaborative Markdown Wiki Engine**. This system is intended to serve as the knowledge backbone for a high-concurrency enterprise environment. It must operate without traditional databases, instead leveraging content-addressable storage (CAS), optimistic concurrency controls, and a high-performance, in-memory inverted index search engine.

This is a **0→1 Engineering Challenge**. You must deliver a modular, robust, and horizontally scalable solution. All logic must be implemented using the **Python 3.10+ Standard Library** exclusively.

---

## 🏗️ 2. Architectural Pillars

### 2.1 Content-Addressable Storage (CAS)
Instead of filename-based persistence, the Wiki uses a "Git-like" blob storage system:
- **Immutability**: Blobs are keyed by their SHA-256 hash. Once written, they are never modified.
- **Deduplication**: Identical page content across different paths or revisions results in only one physical file on disk.
- **Hierarchical Sharding**: To prevent filesystem performance degradation, blobs must be sharded across three levels of subdirectories based on their hex prefix.

### 2.2 Optimistic Concurrency Control (OCC)
To handle multiple editors without heavy distributed locks:
- **Revision ETags**: Every page update must provide the `expected_version` last seen by the user.
- **Fail-Fast Conflict Resolution**: If the current version on disk is higher than the expected version, the system must immediately raise a `ConflictError`.
- **Atomic Commits**: The check-and-write operation for page history must be thread-safe.

### 2.3 Search: TF-IDF Inverted Index
Search is the primary discovery mechanism:
- **Tokenization**: Standardize on alphanumeric whitespace splitting and Unicode-aware lowercasing.
- **Ranking**: Sort results by Term Frequency (TF).
- **Index Lifecycle**: The index must be synchronized with every successful commit.

---

## 📂 3. Mandatory Project Structure
**CRITICAL**: You must strictly adhere to an **Enterprise Single-File Architecture**. You must write the entire system within a single file to guarantee import safety across the cluster.

```text
/home/ubuntu/workspace/
├── wiki_engine.py       # Core package containing ALL logic
├── README.md            # System Architecture Documentation
└── requirements.txt     # Standard library note + pytest
```

---

## 🛠️ 4. Low-Level Technical Specifications

All of these classes MUST be defined within `wiki_engine.py`:

### 4.1 `FileStorage`
The storage layer manages the raw bytes of the wiki.
- **`__init__(self, data_dir: str)`**: Sets the base directory for blobs.
- **`save_blob(self, content: str) -> str`**:
  - Encodes content to UTF-8.
  - Computes `SHA-256`.
  - Determines path: `<data_dir>/blobs/<hash[0:2]>/<hash>`.
  - Atomically writes if file does not exist.
- **`load_blob(self, blob_id: str) -> str`**: Resolves the sharded path and returns the content string.

### 4.2 `HistoryManager`
Handles the "Journal of Truth" for every page.
- **`Revision` Class**: Data model for a commit (ID, BlobID, Author, Timestamp, Version).
- **`ConflictError`**: Custom exception for version mismatches.
- **`add_revision(self, path: str, blob_id: str, author: str, expected_version: int)`**:
  - Implements a thread-local lock for the specific path.
  - Validates `current_version == expected_version`.
  - Persists history as a JSON list in `history/<safe_path>.json`.

### 4.3 `InvertedIndex`
A high-performance lookup table.
- **`index` structure**: `Dict[str, Dict[str, int]]` (term -> {page_id -> count}).
- **Algorithm**:
  - For each word in document: increment per-document count.
  - For each word in query: aggregate counts from all matching documents.
  - Sort results by total aggregate count descending.

### 4.4 `MarkdownParser`
A line-based transformer for formatting.
- **Headers**: `#` (h1) through `######` (h6).
- **Inlines**: `**bold**` and `[link text](url)`.
- **Lists**: `- item` and `* item` unordered lists.
- **Auto-Paragraphing**: Consecutive text lines belong to a `<p>`.

### 4.5 `WikiEngine`
Main coordinator orchestrating all the components.
- **`create_page(self, path: str, content: str, author: str) -> bool`**
- **`update_page(self, path: str, content: str, author: str, expected_version: int) -> bool`**
- **`get_page(self, path: str, version: int = None) -> tuple[str, int]`**
- **`get_history(self, path: str) -> list[dict]`**
- **`search(self, query: str) -> list[str]`**

---

## ⚙️ 5. Concurrency State Machine
All engine operations must follow this linearizable flow:

1.  **READ PHASE**: Retrieve current version $V_n$ and content $C_n$.
2.  **EDIT PHASE**: User prepares update $C_{n+1}$.
3.  **COMMIT PHASE**:
    - Acquire page mutation lock.
    - Validate that disk version is still $V_n$.
    - If $V_{disk} > V_n$: Abort with `ConflictError`.
    - Else:
        - Persist blob $C_{n+1}$.
        - Commit Revision $R_{n+1}$ to history log.
        - Trigger Search Re-Index.
    - Release lock.

---

## 📈 6. Benchmarking & Performance Targets
- **Search Latency**: < 5ms for 1,000 pages on standard hardware.
- **Update Throughput**: Support 50+ concurrent requests with zero "lost updates" (strict OCC enforcement).
- **Storage Overhead**: CAS must achieve >90% de-duplication efficiency for highly repetitive wiki content.

---

## 🧹 7. Coding Standards
- **Exhaustive Type Hinting**: All methods must use `typing` annotations.
- **Defense in Depth**: Handle file system permission errors and corrupted JSON revisions gracefully.
- **Minimal memory footprint**: Search index should use efficient structures to handle 10k+ terms.

---

## 📜 8. Extended Specification Appendix (Lines 200 - 600)

### 8.1 Detailed Method Signatures for `FileStorage`
```python
class FileStorage:
    def __init__(self, data_dir: str) -> None:
        """Initializes the content-addressable storage root."""
        ...
    def save_blob(self, content: str) -> str:
        """Returns the blob_id (SHA-256 hex) of the saved content."""
        ...
```

### 8.2 In-Depth Parser Regex Guidelines
- **Heading 1**: `^#\s+(.*)$`
- **Heading 2**: `^##\s+(.*)$`
- **Bold**: `\*\*([\s\S]*?)\*\*`
- **Lists**: `^[\-\*]\s+(.*)$`

### 8.3 Concurrency Edge Cases
- **Scenario A**: Two threads try to create a page simultaneously. Only one `create_page` must return `True`.
- **Scenario B**: A thread deletes a page while another is searching. No `KeyError` should be raised.

### 8.4 Mathematical Core: The TF Score
The ranking score for a page $P$ given query $Q$ is:
$$Score(P, Q) = \sum_{w \in Q} Frequency(w, P)$$
Where $Frequency(w, P)$ is the count of term $w$ in the UTF-8 normalized text of page $P$.

*(Continuing for 300 additional lines covering: Exception inheritance hierarchies, JSON serialization formatting for Revisions, exact UTF-8 normalization rules, stop-word strategy, file system sharding examples, and exhaustive terminal-interaction examples for searching and versioning)...*

---

[END OF SPECIFICATION: LINE 602]
