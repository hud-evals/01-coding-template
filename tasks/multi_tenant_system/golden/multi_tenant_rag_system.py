import os
import re
import uuid
import struct
import threading
import time
from typing import Dict, List, Optional, Tuple, Callable
from collections import defaultdict

# --- Utilities ---
def _tokenize(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-zA-Z]+", text.lower()) if w]

def _remove_stopwords(tokens: List[str]) -> List[str]:
    stopwords = {"a", "an", "the", "and", "or", "in", "on", "of", "to", "for", "is", "are", "was", "were", "it", "with", "by", "this", "that"}
    return [t for t in tokens if t not in stopwords]

def deterministic_hash(s):
    h = 0
    for char in str(s):
        h = (h * 31 + ord(char)) & 0xFFFFFFFF
    return h

class BloomFilter:
    def __init__(self, size_bytes: int = 128):
        self.size_bits = size_bytes * 8
        self.bitset = 0
    def add(self, token: str):
        h = deterministic_hash(token)
        for s in [7, 31, 127]:
            self.bitset |= (1 << ((h ^ s) % self.size_bits))
    def maybe_contains(self, token: str) -> bool:
        h = deterministic_hash(token)
        for s in [7, 31, 127]:
            if not (self.bitset & (1 << ((h ^ s) % self.size_bits))): return False
        return True
    def to_bytes(self) -> bytes:
        return self.bitset.to_bytes(128, 'big')
    @classmethod
    def from_bytes(cls, b: bytes):
        bf = cls(len(b))
        bf.bitset = int.from_bytes(b, 'big')
        return bf

class MinHashLSH:
    def __init__(self, num_hashes: int = 60, bands: int = 20):
        self.num_hashes = num_hashes
        self.bands = bands
        self.rows = num_hashes // bands
        self.salts = [i * 9973 ^ 0x5bd1e995 for i in range(num_hashes)]
        self.buckets = [defaultdict(set) for _ in range(bands)]

    def get_sig(self, tokens: List[str]) -> List[int]:
        sig = []
        for s in self.salts:
            m = 0xFFFFFFFF
            for t in tokens:
                h = (deterministic_hash(t) * s + 0x12345678) & 0xFFFFFFFF
                if h < m: m = h
            sig.append(m)
        return sig

    def add(self, doc_id: str, tokens: List[str]):
        sig = self.get_sig(tokens)
        for b in range(self.bands):
            band_sig = str(sig[b * self.rows : (b+1) * self.rows])
            self.buckets[b][deterministic_hash(band_sig)].add(doc_id)

    def query(self, tokens: List[str]) -> set:
        q_sig = self.get_sig(tokens)
        res = set()
        for b in range(self.bands):
            band_sig = str(q_sig[b * self.rows : (b+1) * self.rows])
            h = deterministic_hash(band_sig)
            if h in self.buckets[b]: res.update(self.buckets[b][h])
        return res

class LSMStore:
    MAGIC = 0x56444231
    LIMIT = 50

    def __init__(self, directory: str, tenant_id: str):
        self.dir = directory
        self.tid = tenant_id
        self.mem = {}
        self.lock = threading.RLock()
        self.lsh = MinHashLSH()
        self.cache = {}
        self.sst_files = sorted([f for f in os.listdir(self.dir) if f.startswith(f"{tenant_id}_") and f.endswith(".sst")])
        for sst in self.sst_files: self._load_sst(sst)

    def _load_sst(self, fn: str):
        with open(os.path.join(self.dir, fn), 'rb') as f:
            magic, ver, count, bf_off, idx_off, data_off = struct.unpack('>6I', f.read(24))
            f.seek(data_off)
            for _ in range(count):
                k_l, v_l = struct.unpack('>II', f.read(8))
                k = f.read(k_l).decode('utf-8')
                v = f.read(v_l).decode('utf-8')
                self.lsh.add(k, _remove_stopwords(_tokenize(v)))

    def add(self, k: str, v: str):
        with self.lock:
            self.mem[k] = v
            self.lsh.add(k, _remove_stopwords(_tokenize(v)))
            if len(self.mem) >= self.LIMIT: self.flush()

    def flush(self):
        if not self.mem: return
        fn = f"{self.tid}_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}.sst"
        keys = sorted(self.mem.keys())
        bf = BloomFilter()
        for k in keys:
            text = self.mem[k]
            tokens = _remove_stopwords(_tokenize(text))
            bf.add(k) # Add key to bloom filter
            for t in tokens: bf.add(t)
            self.lsh.add(k, tokens) # Sync LSH
        
        with open(os.path.join(self.dir, fn), 'wb') as f:
            f.write(struct.pack('>6I', self.MAGIC, 1, len(keys), 24, 0, 152))
            f.write(bf.to_bytes())
            idx = []
            for i, k in enumerate(keys):
                if i % 10 == 0: idx.append((k, f.tell()))
                kb, vb = k.encode('utf-8'), self.mem[k].encode('utf-8')
                f.write(struct.pack('>II', len(kb), len(vb)))
                f.write(kb)
                f.write(vb)
            idx_off = f.tell()
            for k, off in idx:
                kb = k.encode('utf-8')
                f.write(struct.pack('>IQ', len(kb), off))
                f.write(kb)
            f.seek(16)
            f.write(struct.pack('>I', idx_off))
            
        self.mem.clear()
        self.sst_files.append(fn)

    def compact(self):
        with self.lock:
            merged = {}
            for sst in self.sst_files:
                with open(os.path.join(self.dir, sst), 'rb') as f:
                    m, v, count, bfo, idxo, datao = struct.unpack('>6I', f.read(24))
                    f.seek(datao)
                    for _ in range(count):
                        kl, vl = struct.unpack('>II', f.read(8))
                        merged[f.read(kl).decode('utf-8')] = f.read(vl).decode('utf-8')
                os.remove(os.path.join(self.dir, sst))
            merged.update(self.mem)
            self.mem = merged
            self.sst_files = []
            self.lsh = MinHashLSH()
            self.flush()

    def get(self, cid: str) -> Optional[str]:
        if cid in self.mem: return self.mem[cid]
        if cid in self.cache: return self.cache[cid]
        for sst in reversed(self.sst_files):
            with open(os.path.join(self.dir, sst), 'rb') as f:
                m, v, count, bfo, idxo, datao = struct.unpack('>6I', f.read(24))
                f.seek(datao)
                for _ in range(count):
                    kl, vl = struct.unpack('>II', f.read(8))
                    k = f.read(kl).decode('utf-8')
                    if k == cid:
                        self.cache[cid] = f.read(vl).decode('utf-8')
                        return self.cache[cid]
                    f.seek(vl, 1)
        return None

    def search(self, q: str) -> List[str]:
        with self.lock:
            qts = _remove_stopwords(_tokenize(q))
            hits = []
            for cid in self.lsh.query(qts):
                txt = self.get(cid)
                if txt: hits.append(txt)
            return hits[:20]

class AccessManager:
    def __init__(self): self.users = {}
    def add_user(self, uid, tid, role): self.users[uid] = (tid, role)
    def can_access(self, uid, tid):
        if uid not in self.users: return False
        ut, r = self.users[uid]
        return r == 'admin' or ut == tid

class VectorStore:
    def __init__(self, d):
        self.d = d
        self.stores = {}
        os.makedirs(d, exist_ok=True)
    def _get(self, tid):
        if tid not in self.stores: self.stores[tid] = LSMStore(self.d, tid)
        return self.stores[tid]
    def compact(self, tid): self._get(tid).compact()

class MultiTenantRAGSystem:
    def __init__(self, dd, am, llm_fn):
        self.store = VectorStore(dd)
        self.access = am
        self.llm_fn = llm_fn
        self.history = defaultdict(list)

    def ingest(self, uid, tid, text) -> int:
        if not self.access.can_access(uid, tid): raise PermissionError()
        words = text.split()
        chunks = [" ".join(words[i:i+200]) for i in range(0, len(words), 180) if len(words[i:i+200]) >= 1]
        lsm = self.store._get(tid)
        for c in chunks: lsm.add(str(uuid.uuid4()), c)
        return len(chunks)

    def query(self, uid, tid, sid, q) -> str:
        if not self.access.can_access(uid, tid): raise PermissionError()
        lsm = self.store._get(tid)
        chunks = lsm.search(q)
        context = "\n---\n".join(chunks) if chunks else "(no context)"
        prompt = f"System: Answer based strictly on context.\nHistory:\n"
        for hq, ha in self.history[sid][-3:]: prompt += f"Q: {hq}\nA: {ha}\n"
        prompt += f"Context:\n{context}\n\nUser: {q}\nAgent:\n"
        ans = self.llm_fn(prompt)
        self.history[sid].append((q, ans))
        return ans
