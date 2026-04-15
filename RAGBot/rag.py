"""
rag.py — RAG pipeline: ChromaDB tìm context → Ollama trả lời
"""

import chromadb
from chromadb.utils import embedding_functions
from langchain_community.llms import Ollama
from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"

from config import (
    OLLAMA_MODEL, OLLAMA_BASE_URL,
    CHROMA_DIR, CHROMA_COLLECTION, EMBED_MODEL,
    TOP_K, MAX_TOKENS, TEMPERATURE
)


PROMPT_TEMPLATE = PromptTemplate.from_template("""
You are a helpful medical assistant. Answer the user's question based on the context below.
If the context doesn't contain enough information, say so honestly.
Always recommend consulting a doctor for serious medical concerns.

Context:
{context}

Question: {question}

Answer (in the same language as the question):
""")


class RAGBot:
    def __init__(self):
        print(f"🚀 Loading RAGBot (model={OLLAMA_MODEL})...")

        # ChromaDB
        self._client = chromadb.PersistentClient(path=CHROMA_DIR)
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL
        )
        self._collection = self._client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"}
        )
        print(f"   ✅ ChromaDB: {self._collection.count():,} records")

        # Ollama LLM
        self._llm = Ollama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=TEMPERATURE,
            num_predict=MAX_TOKENS,
        )

        # Chain
        self._chain = (
            {"context": self._retrieve, "question": RunnablePassthrough()}
            | PROMPT_TEMPLATE
            | self._llm
            | StrOutputParser()
        )
        print(f"   ✅ Ollama: {OLLAMA_MODEL} @ {OLLAMA_BASE_URL}")
        print("   ✅ RAGBot sẵn sàng!\n")

    def _retrieve(self, question: str) -> str:
        results = self._collection.query(
            query_texts=[question],
            n_results=TOP_K
        )
        contexts = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            contexts.append(f"Q: {doc}\nA: {meta['answer']}")
        return "\n\n---\n\n".join(contexts)

    def ask(self, question: str) -> dict:
        """Trả lời câu hỏi, kèm context đã dùng."""
        context = self._retrieve(question)
        answer = self._chain.invoke(question)
        return {
            "question": question,
            "answer": answer,
            "context_used": context[:500] + "..." if len(context) > 500 else context
        }

    def stream(self, question: str):
        """Stream câu trả lời từng token."""
        context = self._retrieve(question)
        prompt = PROMPT_TEMPLATE.format(context=context, question=question)
        for chunk in self._llm.stream(prompt):
            yield chunk
