import sys
import os
import pytest
from unittest.mock import MagicMock

# --- Comprehensive Global Patches ---

def patch_modules():
    # Mocking all heavy dependencies
    sys.modules['dotenv'] = MagicMock()
    
    hf_mod = MagicMock()
    class MockEmbed:
        def __init__(self, *args, **kwargs): pass
        def embed_query(self, q): return [0.0]*384
    hf_mod.HuggingFaceEmbeddings = MockEmbed
    sys.modules['langchain_huggingface'] = hf_mod

    vectorstores_mod = MagicMock()
    class MockFAISS:
        @classmethod
        def load_local(cls, *args, **kwargs): return MagicMock()
    vectorstores_mod.FAISS = MockFAISS
    sys.modules['langchain_community.vectorstores'] = vectorstores_mod
    sys.modules['langchain_community.docstore.in_memory'] = MagicMock()

    groq_mod = MagicMock()
    class MockChat:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get('model')
            self.temperature = kwargs.get('temperature')
        def generate(self, m):
            r = MagicMock()
            r.generations = [[MagicMock(text="Mitigation: Block IP 1.2.3.4. Risk: 8/10")]]
            return r
    groq_mod.ChatGroq = MockChat
    sys.modules['langchain_groq'] = groq_mod
    
    sys.modules['langchain_core.messages'] = MagicMock()
    sys.modules['faiss'] = MagicMock()

patch_modules()
os.environ["GROQ_API_KEY"] = "gsk_cyber_mock_key"

def get_hunter():
    import threat_hunter
    return threat_hunter.ThreatHunter(api_key="mock_key")

def test_imports():
    """Check 1: Core imports."""
    import threat_hunter
    assert threat_hunter.ThreatHunter is not None

def test_bloom_filter():
    """Check 2: Custom Bloom Filter logic."""
    import threat_hunter
    bf = threat_hunter.BloomFilter(size=100)
    bf.add("1.2.3.4")
    assert bf.contains("1.2.3.4")
    assert not bf.contains("5.6.7.8")

def test_entropy_calc():
    """Check 3: Shannon Entropy calculation."""
    import threat_hunter
    e = threat_hunter.EntropyCalculator.shannon_entropy("normal")
    e_high = threat_hunter.EntropyCalculator.shannon_entropy("aGVsbG8gd29ybGQgdGhpcyBpcyBhIHRlc3Q=") # base64
    assert e_high > e

def test_log_parser():
    """Check 4: Artifact extraction."""
    import threat_hunter
    parser = threat_hunter.SIEMLogParser()
    res = parser.extract_artifacts("Connection from 192.168.1.1 to mal.com")
    assert isinstance(res, dict)
    assert any(key in res for key in ["ipv4", "domain", "file_hash", "artifacts"])

def test_faiss_config():
    """Check 5: FAISS Intelligence DB setup."""
    hunter = get_hunter()
    assert hunter.intelligence_db is not None

def test_llm_config():
    """Check 6: Groq LLM configuration."""
    hunter = get_hunter()
    # Structural check only: verify LLM object exists and has required config attributes
    assert hasattr(hunter, "llm")
    assert hasattr(hunter.llm, "model") or hasattr(hunter.llm, "model_name")

def test_analysis_pipeline():
    """Check 7: Full pipeline execution."""
    hunter = get_hunter()
    report = hunter.analyze_log("Suspicious activity on 10.0.0.5")
    assert isinstance(report, str)

def test_mitigation_content():
    """Check 8: Response content verification."""
    hunter = get_hunter()
    report = hunter.analyze_log("Root login from unknown IP")
    assert "Mitigation" in report or "Risk" in report

def test_internal_handlers():
    """Check 9: Advanced protocol logic."""
    import threat_hunter
    # Check if at least one handler exists to verify the 'Internal Logic' requirement
    handler_names = [attr for attr in dir(threat_hunter) if "logic_handler" in attr]
    assert len(handler_names) >= 1
    res = getattr(threat_hunter, handler_names[0])(b"test")
    assert isinstance(res, bool)

def test_top_level_entry():
    """Check 10: Standard query_threat_hunter entry point."""
    import threat_hunter
    res = threat_hunter.query_threat_hunter("test log")
    assert isinstance(res, str) and len(res) > 0
