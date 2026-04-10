import sys
import os
import shutil
import pytest
import threading
import time
import struct
import uuid
sys.path.insert(0, "/home/ubuntu/workspace")

# The agent must implement these symbols
from multi_tenant_rag_system import (
    MultiTenantRAGSystem, 
    AccessManager,
    VectorStore
)

class TestVectorDBEnterprise:
    def setup_method(self):
        self.test_dir = "/tmp/rag_enterprise_test"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)

    def teardown_method(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_lsm_flushing_and_persistence(self):
        am = AccessManager()
        am.add_user("admin", "T1", "admin")
        sys = MultiTenantRAGSystem(self.test_dir, am, lambda x: "Mock")
        
        # Limit is 50. Ingest 110 documents to force 2 flushes + some in MemTable.
        for i in range(110):
            sys.ingest("admin", "T1", f"This is document number {i} containing unique content to avoid deduplication.")
            
        # Check files. There should be at least two .sst files for T1.
        files = [f for f in os.listdir(self.test_dir) if f.startswith("T1") and f.endswith(".sst")]
        assert len(files) >= 2, f"Expected at least 2 SSTables, found {len(files)}"
        
        # Verify binary header
        with open(os.path.join(self.test_dir, files[0]), "rb") as f:
            magic = f.read(4)
            assert magic == b"VDB1", "SSTable MAGIC header 0x56444231 (VDB1) missing"

    def test_compaction_consistency(self):
        am = AccessManager()
        am.add_user("admin", "T1", "admin")
        sys = MultiTenantRAGSystem(self.test_dir, am, lambda x: "Mock")
        
        # Ingest documents spanning multiple flushes
        for i in range(120):
            sys.ingest("admin", "T1", f"Data piece {i}")
            
        # Verify search works before compaction
        res = sys.query("admin", "T1", "sess", "Data piece 10")
        assert "Data piece 10" in res or "Mock" in res # Depending on echo or mock llm
        
        # Trigger compaction
        if hasattr(sys.store, 'compact'):
            sys.store.compact("T1")
        
        # After compaction, there should be exactly one .sst file
        files = [f for f in os.listdir(self.test_dir) if f.startswith("T1") and f.endswith(".sst")]
        assert len(files) == 1, f"Expected 1 SSTable after compaction, found {len(files)}"
        
        # Verify no data was lost using a mock that returns the context
        def capture_context(p):
            if "Context:" in p:
                return p.split("Context:")[1].split("User:")[0].strip()
            return "(no context)"
        sys.llm_fn = capture_context
        
        ans = sys.query("admin", "T1", "sess", "Data piece 119")
        assert "Data piece 119" in ans, f"Data piece 119 lost after compaction. Context was: {ans}"

    def test_lsh_banding_efficiency(self):
        am = AccessManager()
        am.add_user("admin", "T1", "admin")
        sys = MultiTenantRAGSystem(self.test_dir, am, lambda x: x)
        
        # Ingest a large number of unrelated docs
        for i in range(200):
            sys.ingest("admin", "T1", f"Random noise document with unrelated tokens {i} {uuid.uuid4()}")
            
        # Ingest target doc
        target_text = "The quick brown fox jumps over the lazy dog in the sunny meadow"
        sys.ingest("admin", "T1", target_text)
        
        # Ingest more noise
        for i in range(100):
            sys.ingest("admin", "T1", f"More noise {i} {uuid.uuid4()}")

        # Search for target
        def capture_context(p):
            if "Context:" in p:
                return p.split("Context:")[1].split("User:")[0].strip()
            return ""
            
        sys.llm_fn = capture_context
        start = time.time()
        result = sys.query("admin", "T1", "sess", "quick brown fox meadow")
        duration = time.time() - start
        
        assert "quick brown fox" in result, "LSH retrieval failed to find target document"
        # Efficiency check: searching 300 docs with Banded LSH should be 
        # significantly faster than a full linear scan if implemented correctly.
        # In pure Python it's hard to time exactly, but let's check it's not glacial.
        assert duration < 1.0, f"Search too slow: {duration}s"

    def test_isolation_enforcement(self):
        am = AccessManager()
        am.add_user("joe", "tenantJoe", "member")
        am.add_user("jane", "tenantJane", "member")
        sys = MultiTenantRAGSystem(self.test_dir, am, lambda x: x)
        
        sys.ingest("joe", "tenantJoe", "Joe's private bank account password is 12345")
        
        # Jane tries to see Joe's data
        with pytest.raises(PermissionError):
            sys.query("jane", "tenantJoe", "sess", "bank account")
            
        # Jane searches her own empty tenant
        def capture_context(p):
             if "Context:" in p:
                return p.split("Context:")[1].split("User:")[0].strip()
             return ""
        sys.llm_fn = capture_context
        res = sys.query("jane", "tenantJane", "sess", "bank account")
        assert "(no context)" in res, "Isolation leak: Jane saw data she shouldn't"

    def test_lru_cache_behavior(self):
        # This test checks if the system is actually using the cache 
        # by checking disk read frequency if possible, or just behavior.
        # Since we can't easily mock 'open', we'll rely on the agent's code.
        # But we can verify it doesn't crash with many concurrent reads.
        am = AccessManager()
        am.add_user("admin", "T1", "admin")
        sys = MultiTenantRAGSystem(self.test_dir, am, lambda x: "done")
        
        for i in range(100):
            sys.ingest("admin", "T1", f"Cache test doc {i}")
            
        # Repeatedly query the same thing
        for _ in range(50):
            sys.query("admin", "T1", "sess", "Cache test doc 50")
            
        # No crash occurs, data consistent.
        assert True

if __name__ == "__main__":
    pytest.main([__file__])
