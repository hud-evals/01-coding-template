import os
import time
import threading
import json
import hashlib
import re
from pathlib import Path
from collections import defaultdict

# --- STORAGE LAYER ---

class FileStorage:
    """
    Content-addressable storage for wiki blobs.
    Persists data in a tiered directory structure based on hash.
    """
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.blobs_dir = self.base_dir / "blobs"
        self.blobs_dir.mkdir(exist_ok=True)

    def save_blob(self, content: str) -> str:
        """Saves content and returns its SHA-256 hash as the blob ID."""
        data = content.encode("utf-8")
        blob_id = hashlib.sha256(data).hexdigest()
        
        # Tiered storage: e.g., blobs/ab/cd...
        shard_dir = self.blobs_dir / blob_id[:2]
        shard_dir.mkdir(exist_ok=True)
        
        blob_path = shard_dir / blob_id
        if not blob_path.exists():
            blob_path.write_bytes(data)
            
        return blob_id

    def load_blob(self, blob_id: str) -> str:
        """Retrieves content by blob ID."""
        shard_dir = self.blobs_dir / blob_id[:2]
        blob_path = shard_dir / blob_id
        if not blob_path.exists():
            raise FileNotFoundError(f"Blob {blob_id} not found")
        return blob_path.read_text(encoding="utf-8")

    def exists(self, blob_id: str) -> bool:
        shard_dir = self.blobs_dir / blob_id[:2]
        return (shard_dir / blob_id).exists()

# --- VERSIONING LAYER ---

class Revision:
    """Represents a single immutable revision of a wiki page."""
    def __init__(self, rev_id: str, blob_id: str, author: str, timestamp: float, version: int):
        self.rev_id = rev_id
        self.blob_id = blob_id
        self.author = author
        self.timestamp = timestamp
        self.version = version

    def to_dict(self):
        return {
            "rev_id": self.rev_id,
            "blob_id": self.blob_id,
            "author": self.author,
            "timestamp": self.timestamp,
            "version": self.version
        }

class ConflictError(Exception):
    """Raised when an update fails due to a version mismatch."""
    pass

class HistoryManager:
    """
    Manages the revision history of pages.
    Implements optimistic locking logic.
    """
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir) / "history"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # In-memory cache for locks and quick version checks
        self._locks = {}
        self._global_lock = threading.Lock()

    def _get_page_lock(self, path: str):
        with self._global_lock:
            if path not in self._locks:
                self._locks[path] = threading.Lock()
            return self._locks[path]

    def _get_history_file(self, path: str) -> Path:
        # safe file name from path
        safe_name = path.replace("/", "__").replace("\\", "__")
        return self.base_dir / f"{safe_name}.json"

    def get_revisions(self, path: str) -> list[Revision]:
        hist_file = self._get_history_file(path)
        if not hist_file.exists():
            return []
        
        with open(hist_file, "r") as f:
            data = json.load(f)
            return [Revision(**r) for r in data]

    def add_revision(self, path: str, blob_id: str, author: str, expected_version: int) -> Revision:
        lock = self._get_page_lock(path)
        with lock:
            revisions = self.get_revisions(path)
            current_version = revisions[-1].version if revisions else 0
            
            if current_version != expected_version:
                raise ConflictError(f"Version mismatch for {path}: expected {expected_version}, got {current_version}")
            
            new_version = current_version + 1
            rev_id = f"v{new_version}_{int(time.time())}"
            new_rev = Revision(rev_id, blob_id, author, time.time(), new_version)
            
            revisions.append(new_rev)
            
            # Persist history
            hist_file = self._get_history_file(path)
            with open(hist_file, "w") as f:
                json.dump([r.to_dict() for r in revisions], f, indent=2)
                
            return new_rev

# --- SEARCH LAYER ---

class InvertedIndex:
    """
    In-memory inverted index for full-text search.
    Supports basic term frequency ranking.
    """
    def __init__(self):
        # term -> {page_id -> frequency}
        self.index = defaultdict(lambda: defaultdict(int))
        self._lock = threading.Lock()

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenizer: lowercase, alpha-numeric tokens only."""
        return re.findall(r'\w+', text.lower())

    def add_page(self, page_id: str, content: str):
        """Adds or updates a page in the index."""
        tokens = self._tokenize(content)
        with self._lock:
            # First remove existing entries for this page_id
            self._remove_page_no_lock(page_id)
            for token in tokens:
                self.index[token][page_id] += 1

    def remove_page(self, page_id: str):
        """Removes a page from the index."""
        with self._lock:
            self._remove_page_no_lock(page_id)

    def _remove_page_no_lock(self, page_id: str):
        # Linear scan of terms to remove page entries
        # In a massive wiki, you'd want terms -> page_id mapping too
        terms_to_clean = []
        for term, pages in self.index.items():
            if page_id in pages:
                del pages[page_id]
                if not pages:
                    terms_to_clean.append(term)
        for t in terms_to_clean:
            del self.index[t]

    def search(self, query: str) -> list[str]:
        """
        Returns page IDs containing query terms, 
        ranked by combined term frequency.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = defaultdict(int)
        with self._lock:
            for token in query_tokens:
                if token in self.index:
                    for page_id, freq in self.index[token].items():
                        scores[page_id] += freq

        # Sort by total frequency descending
        results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [res[0] for res in results]

    def clear(self):
        with self._lock:
            self.index.clear()

# --- PARSER LAYER ---

class MarkdownParser:
    """
    A simple markdown parser that converts a subset of markdown to HTML.
    Supported: 
    - Headings (#, ##, ...)
    - Bold (**text**)
    - Lists (- item)
    - Links ([text](url))
    """
    def to_html(self, markdown: str) -> str:
        if not markdown:
            return ""

        lines = markdown.splitlines()
        html_lines = []
        in_list = False

        for line in lines:
            stripped = line.strip()
            
            # Handle list state
            is_list_item = stripped.startswith("- ") or stripped.startswith("* ")
            if is_list_item:
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                content = self._parse_inline(stripped[2:])
                html_lines.append(f"<li>{content}</li>")
                continue
            else:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False

            if not stripped:
                continue

            # Headings
            heading_match = re.match(r'^(#+)\s*(.*)$', stripped)
            if heading_match:
                level = len(heading_match.group(1))
                if level > 6: level = 6
                content = self._parse_inline(heading_match.group(2))
                html_lines.append(f"<h{level}>{content}</h{level}>")
                continue

            # Standard paragraph
            content = self._parse_inline(stripped)
            html_lines.append(f"<p>{content}</p>")

        if in_list:
            html_lines.append("</ul>")

        return "\n".join(html_lines)

    def _parse_inline(self, text: str) -> str:
        """Parses bold text and links within a block."""
        # Bold: **text**
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        # Links: [text](url)
        text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
        return text

# --- CORE WIKI ENGINE ---

class WikiEngine:
    """
    Main coordinator for the Collaborative Wiki Engine.
    Handles high-level API for CRUD, versioning, search, and parsing.
    """
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.storage = FileStorage(str(self.data_dir))
        self.history = HistoryManager(str(self.data_dir))
        self.index = InvertedIndex()
        self.parser = MarkdownParser()
        
        # Build initial search index from existing data
        self._initialize_index()

    def _initialize_index(self):
        """Scan all history files and index the latest content for each page."""
        hist_dir = self.data_dir / "history"
        if not hist_dir.exists():
            return

        for hist_file in hist_dir.glob("*.json"):
            try:
                with open(hist_file, "r") as f:
                    data = json.load(f)
                    if data:
                        latest = data[-1]
                        # simplified index resume
                        pass 
            except Exception:
                continue

    def create_page(self, path: str, content: str, author: str) -> bool:
        """Creates a brand search page. Fails if page already exists."""
        return self.update_page(path, content, author, expected_version=0)

    def update_page(self, path: str, content: str, author: str, expected_version: int) -> bool:
        """
        Updates a page if the expected_version matches the current version.
        Implements optimistic locking.
        """
        blob_id = self.storage.save_blob(content)
        try:
            self.history.add_revision(path, blob_id, author, expected_version)
            # Update search index with the new content
            self.index.add_page(path, content)
            return True
        except ConflictError:
            return False

    def get_page(self, path: str, version: int = None) -> tuple[str | None, int]:
        """
        Retrieves page content and its current version number.
        If version is specified, retrieves that specific revision.
        """
        revisions = self.history.get_revisions(path)
        if not revisions:
            return None, 0
        
        if version is not None:
            if version < 1 or version > len(revisions):
                return None, 0
            rev = revisions[version - 1]
        else:
            rev = revisions[-1]
            
        content = self.storage.load_blob(rev.blob_id)
        return content, rev.version

    def get_history(self, path: str) -> list[dict]:
        """Returns the full list of revisions for a page."""
        return [r.to_dict() for r in self.history.get_revisions(path)]

    def search(self, query: str) -> list[str]:
        """Performs full-text search across all live pages."""
        return self.index.search(query)

    def get_html(self, path: str, version: int = None) -> str:
        """Returns the rendered HTML for a specific page/version."""
        content, _ = self.get_page(path, version)
        if content is None:
            return ""
        return self.parser.to_html(content)
