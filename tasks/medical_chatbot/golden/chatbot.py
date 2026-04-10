import os
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

class PediatricChatbot:
    """ Structural definition for the primary bot engine. """
    
    def __init__(self, api_key: str, index_dir: str):
        # Load environment variables
        load_dotenv()
        self.api_key = api_key
        
        # Initialize Embeddings
        self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        
        # Load FAISS index with fallback
        try:
            self.faiss_index = FAISS.load_local(
                index_dir,
                self.embeddings,
                allow_dangerous_deserialization=True
            )
        except Exception:
            import faiss
            from langchain_community.docstore.in_memory import InMemoryDocstore
            index = faiss.IndexFlatL2(len(self.embeddings.embed_query("hello")))
            self.faiss_index = FAISS(
                embedding_function=self.embeddings,
                index=index,
                docstore=InMemoryDocstore(),
                index_to_docstore_id={},
            )
        
        # Initialize Groq LLM
        self.chat_groq = ChatGroq(
            api_key=self.api_key,
            model="llama-3.3-70b-versatile",
            temperature=0
        )

    def retrieve_context(self, query: str, top_k: int = 5) -> list[str]:
        """ Performs the dense vector retrieval. """
        docs = self.faiss_index.similarity_search(query, k=top_k)
        return [doc.page_content for doc in docs]

    def generate_response(self, context_list: list[str], user_query: str) -> str:
        """ Constructs the HumanMessage and invokes the Llama-3.3-70b model. """
        context_text = "\n\n".join(context_list)
        
        prompt = f"""
You are a professional pediatrician chatbot. Answer questions based only on the context below.
Follow these rules strictly:
1. Only use information from the provided context.
2. Answer concisely and clearly, suitable for a parent or caregiver.
3. Focus on the user's specific question.
4. Do not speculate or ask the user to rephrase their question.
5. Do not list diseases or suggest the user pick from a list.
6. Keep the answer professional, empathetic, and practical.

Context:
{context_text}

Question:
{user_query}
"""
        response = self.chat_groq.generate([[HumanMessage(content=prompt)]])
        return response.generations[0][0].text

def query_chatbot(user_query: str, k: int = 5) -> str:
    """ Top-level utility function for backward compatibility and simplified testing. """
    api_key = os.getenv("GROQ_API_KEY", "dummy_key")
    bot = PediatricChatbot(api_key=api_key, index_dir="faiss_index")
    context = bot.retrieve_context(user_query, top_k=k)
    return bot.generate_response(context, user_query)

if __name__ == "__main__":
    print("Pediatric Chatbot Engine (v2) Active")
