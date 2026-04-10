import sys
import os
import pytest
from unittest.mock import MagicMock

# --- Global Patches ---
sys.modules['dotenv'] = MagicMock()
hf_mod = MagicMock()
hf_mod.HuggingFaceEmbeddings = type('Mock', (), {'__init__': lambda s, *a, **k: None, 'embed_query': lambda s, q: [0.0]*384})
sys.modules['langchain_huggingface'] = hf_mod
faiss_mod = MagicMock()
faiss_mod.FAISS = type('Mock', (), {'load_local': classmethod(lambda c, *a, **k: MagicMock())})
sys.modules['langchain_community.vectorstores'] = faiss_mod
sys.modules['langchain_community.docstore.in_memory'] = MagicMock()
groq_mod = MagicMock()
groq_mod.ChatGroq = type('Mock', (), {'__init__': lambda s, *a, **k: None})
sys.modules['langchain_groq'] = groq_mod
sys.modules['langchain_core'] = MagicMock()
sys.modules['langchain_core.messages'] = MagicMock()
sys.modules['faiss'] = MagicMock()
os.environ["GROQ_API_KEY"] = "gsk_dummy_123"

def test_fallback():
    import chatbot
    # Since we mocked FAISS to succeed, we just verify the function handles execution
    assert chatbot.query_chatbot("emergency") is not None
