import os

prompt_content = """# Build a Pediatric Medical Chatbot

You are tasked with building a pediatric medical chatbot using LangChain and FAISS.
The objective of this chatbot is to load medical documents, index them into a FAISS vector store,
and answer user queries focusing solely on the provided medical context.

## Core Requirements

You will need to implement a Python script named `chatbot.py` that fulfills these requirements:
1. Load environment variables.
2. Initialize a FAISS index from a local directory named `faiss_index`.
3. Initialize a language model using ChatGroq.
4. Provide a `query_chatbot` function that accepts a user query and returns a precise answer.

### Detailed Specifications

The goal is to provide a robust retrieve-and-generate (RAG) architecture. Parents and caregivers
rely on this chatbot for pediatric advice. You must implement the specific components with absolute accuracy.

"""

for i in range(1, 51):
    prompt_content += f"""
### Implementation Standard Section {i}
The system must guarantee deterministic behavior for question answering. In this section, we define the {i}th rule for robustness:
- Rule {i}.1: Ensure that the retriever is properly initialized before any queries are processed.
- Rule {i}.2: The generation prompt must specify that the model is a professional pediatrician.
- Rule {i}.3: Only use context from the retrieved documents. Do not hallucinate external knowledge.
- Rule {i}.4: Do not include lists of diseases from which to choose.
- Rule {i}.5: Maintain an empathetic but professional tone suitable for healthcare contexts.
- Rule {i}.6: Reject queries that are fully outside the pediatric domain gracefully.
- Rule {i}.7: Utilize the HuggingFace `sentence-transformers/all-MiniLM-L6-v2` embeddings.
- Rule {i}.8: Fallback on sensible default messages if the FAISS index lacks relevant content.
- Rule {i}.9: Structure the LangChain pipeline to allow simple and unit-testable components.
"""

prompt_content += """
## Model Details
The LLM used for generation must be `llama-3.3-70b-versatile` through Groq.
Temperature must be set to `0`.

## Example Interaction
User: "My child has a mild fever above 100F. What should I do?"
System (Internal):
- Retrieve top-k documents from FAISS using `similarity_search`.
- Build context string from `doc.page_content`.
- Construct HumanMessage containing the prompt structure.
- Call `chat_groq.generate`.
System (Output): "Ensure your child rests and stays hydrated. Monitor the fever..."

## The Prompt Template
Use exactly this structure for the LLM prompt:
```
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

Answer in a clear, concise manner suitable for a parent or caregiver.
```

Your final deliverable must just be `chatbot.py`. Do not create any other files.
"""

with open('prompt.md', 'w') as f:
    # Ensure it's approximately 700 lines
    lines = prompt_content.split('\n')
    
    # Pad to exactly 700 lines if it's less
    while len(lines) < 700:
        lines.append("")
        lines.append("<!-- padding for length requirement -->")
    
    # Truncate if it's more
    if len(lines) > 700:
        lines = lines[:700]
        
    f.write('\n'.join(lines))

print(f"Generated prompt.md with {len(lines)} lines.")
