import sys
import os
import pytest
from unittest.mock import MagicMock

# --- Comprehensive Global Patches to prevent network calls and ModuleNotFoundErrors ---

def patch_modules():
    # 1. Mock dotenv
    dotenv_mod = MagicMock()
    sys.modules['dotenv'] = dotenv_mod

    # 2. Mock langchain_huggingface
    hf_mod = MagicMock()
    class MockHuggingFaceEmbeddings:
        def __init__(self, *args, **kwargs): self.model_name = kwargs.get("model_name")
        def embed_query(self, query): return [0.0] * 384
    hf_mod.HuggingFaceEmbeddings = MockHuggingFaceEmbeddings
    sys.modules['langchain_huggingface'] = hf_mod

    # 3. Mock langchain_community
    vectorstores_mod = MagicMock()
    class MockFAISS:
        @classmethod
        def load_local(cls, *args, **kwargs):
            if args[0] == "non_existent_path":
                raise Exception("Index not found")
            return MagicMock()
    vectorstores_mod.FAISS = MockFAISS
    sys.modules['langchain_community.vectorstores'] = vectorstores_mod

    docstore_mod = MagicMock()
    sys.modules['langchain_community.docstore.in_memory'] = docstore_mod

    # 4. Mock langchain_groq
    groq_mod = MagicMock()
    class MockChatGroq:
        def __init__(self, *args, **kwargs):
            self.api_key = kwargs.get("api_key")
            self.model = kwargs.get("model")
            self.temperature = kwargs.get("temperature")
        def generate(self, messages):
            mock_resp = MagicMock()
            mock_resp.generations = [[MagicMock(text="Mocked pediatrician response.")]]
            return mock_resp
    groq_mod.ChatGroq = MockChatGroq
    sys.modules['langchain_groq'] = groq_mod

    # 5. Mock langchain_core
    core_mod = MagicMock()
    messages_mod = MagicMock()
    core_mod.messages = messages_mod
    sys.modules['langchain_core'] = core_mod
    sys.modules['langchain_core.messages'] = messages_mod

    # 6. Mock faiss
    sys.modules['faiss'] = MagicMock()

patch_modules()

# --- Environment Variables ---
os.environ["GROQ_API_KEY"] = "gsk_dummy_mock_key_12345"

def get_bot():
    import chatbot
    return chatbot.PediatricChatbot(api_key="gsk_real_key", index_dir="faiss_index")

def test_imports():
    """Check 1: Import integrity."""
    import chatbot
    assert chatbot.PediatricChatbot is not None

def test_env_vars():
    """Check 2: Property initialization."""
    bot = get_bot()
    assert bot.api_key == "gsk_real_key"

def test_faiss_init():
    """Check 3: FAISS initialization."""
    bot = get_bot()
    assert bot.faiss_index is not None

def test_llm_setup():
    """Check 4: LLM Configuration."""
    bot = get_bot()
    assert bot.chat_groq.model == "llama-3.3-70b-versatile"
    assert bot.chat_groq.temperature == 0

def test_prompt_persona():
    """Check 5: Interface verification."""
    bot = get_bot()
    assert hasattr(bot, 'generate_response')
    assert hasattr(bot, 'retrieve_context')

def test_query_execution():
    """Check 6: End-to-end execution via top-level function."""
    import chatbot
    res = chatbot.query_chatbot("Hello", k=1)
    assert isinstance(res, str)
    assert "Mocked" in res

def test_rag_integrity():
    """Check 7: RAG retrieval verification."""
    bot = get_bot()
    mock_index = MagicMock()
    bot.faiss_index = mock_index
    bot.retrieve_context("test", top_k=3)
    mock_index.similarity_search.assert_called()

def test_response_formatting():
    """Check 8: Response formatting."""
    bot = get_bot()
    res = bot.generate_response(["Context"], "Question")
    assert len(res) > 0
