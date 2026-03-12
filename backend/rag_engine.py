"""
Advanced RAG Engine for Knowledge Base
Implements: Hybrid Search (Vector + BM25), Rerank, Semantic Chunking
"""

import os
import re
import uuid
import json
import httpx

from typing import List, Dict, Any, Optional, Tuple, Generator
from pathlib import Path
import shutil
import pickle
import asyncio
import hashlib
import time

import jieba
from rank_bm25 import BM25Okapi
import fitz  # PyMuPDF

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter
)
import fitz  # PyMuPDF
import pymupdf4llm
import pathlib
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
# ConversationalRetrievalChain removed - using direct LLM calls instead
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.documents import Document
from database import ChatHistoryDB
from pdf_processor import PDFProcessor


class SiliconFlowReranker:
    """
    True Cross-Encoder Reranker using SiliconFlow /v1/rerank API
    Uses BAAI/bge-reranker-v2-m3 model for precise document relevance scoring
    """
    
    def __init__(self, api_key: str, api_base: str, model: str = "BAAI/bge-reranker-v2-m3"):
        self.api_key = api_key
        self.api_base = api_base.rstrip('/')
        self.model = model
        self.timeout_seconds = float(os.getenv("RERANK_TIMEOUT_SECONDS", "12"))
        self.max_doc_chars = int(os.getenv("RERANK_MAX_DOC_CHARS", "4000"))
    
    def rerank(self, query: str, documents: List[str], top_n: int = 5) -> List[Tuple[int, float]]:
        """
        Rerank documents using true Cross-Encoder model via SiliconFlow API
        
        Args:
            query: User query
            documents: List of document texts
            top_n: Number of top results to return
            
        Returns:
            List of (original_index, score) tuples, sorted by relevance
        """
        if not documents:
            return []
        
        # SiliconFlow Rerank API endpoint
        url = f"{self.api_base}/rerank"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = httpx.post(
                url,
                headers=headers,
                json={
                    "model": self.model,
                    "query": query,
                    "documents": documents,
                    "top_n": top_n,
                    "return_documents": False,
                    "max_chunks_per_doc": 1024
                },
                timeout=60.0
            )
            response.raise_for_status()
            
            result = response.json()
            # Response format: {"results": [{"index": 0, "relevance_score": 0.95}, ...]}
            scores = []
            for item in result.get("results", []):
                scores.append((item["index"], item["relevance_score"]))
            
            scores.sort(key=lambda x: x[1], reverse=True)
            if scores:
                print(f"   ✅ Rerank completed: {len(scores)} results, top score: {scores[0][1]:.4f}")
            return scores[:top_n]
            
        except Exception as e:
            print(f"   ⚠️ SiliconFlow Rerank error: {e}, falling back to original order")
            return [(i, 1.0 - i * 0.01) for i in range(min(top_n, len(documents)))]

    def _tokenize_for_fallback(self, text: str) -> List[str]:
        return re.findall(r"[\w\u4e00-\u9fff]+", text.lower())

    def _keyword_fallback(self, query: str, documents: List[str], top_n: int) -> List[Tuple[int, float]]:
        query_tokens = set(self._tokenize_for_fallback(query))
        if not query_tokens:
            return []

        scored: List[Tuple[int, float]] = []
        for idx, doc in enumerate(documents):
            doc_tokens = set(self._tokenize_for_fallback(doc))
            overlap = len(query_tokens & doc_tokens)
            if overlap <= 0:
                continue
            score = overlap / max(1, len(query_tokens))
            scored.append((idx, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_n]

    async def rerank_async(self, query: str, documents: List[str], top_n: int = 5) -> List[Tuple[int, float]]:
        """
        Async rerank with layered fallback:
        1) Remote rerank API (strict timeout)
        2) Local keyword-overlap scoring
        3) Original retrieval order
        """
        if not documents:
            return []

        capped_docs = [d[:self.max_doc_chars] for d in documents] if self.max_doc_chars > 0 else documents
        url = f"{self.api_base}/rerank"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json={
                        "model": self.model,
                        "query": query,
                        "documents": capped_docs,
                        "top_n": top_n,
                        "return_documents": False,
                        "max_chunks_per_doc": 1024
                    },
                )
                response.raise_for_status()

            result = response.json()
            scores = []
            for item in result.get("results", []):
                scores.append((item["index"], item["relevance_score"]))
            scores.sort(key=lambda x: x[1], reverse=True)
            if scores:
                print(f"   ✅ Async rerank completed: {len(scores)} results, top score: {scores[0][1]:.4f}")
            return scores[:top_n]

        except (httpx.TimeoutException, httpx.RequestError) as e:
            print(f"   ⚠️ Async rerank timeout/request error: {e}. Falling back to keyword overlap.")
        except Exception as e:
            print(f"   ⚠️ Async rerank API error: {e}. Falling back to keyword overlap.")

        keyword_scores = self._keyword_fallback(query, capped_docs, top_n)
        if keyword_scores:
            print(f"   ℹ️ Async rerank fallback: keyword overlap ({len(keyword_scores)} results)")
            return keyword_scores

        print("   ℹ️ Async rerank fallback: original retrieval order")
        return [(i, 1.0 - i * 0.01) for i in range(min(top_n, len(capped_docs)))]


class ZhipuReranker:
    """Reranker using Zhipu AI embedding-rank model"""

    
    def __init__(self, api_key: str, api_base: str, model: str = "embedding-rank"):
        self.api_key = api_key
        self.api_base = api_base.rstrip('/')
        self.model = model
    
    def rerank(self, query: str, documents: List[str], top_n: int = 5) -> List[Tuple[int, float]]:
        """
        Rerank documents by relevance to query
        
        Args:
            query: User query
            documents: List of document texts
            top_n: Number of top results to return
            
        Returns:
            List of (original_index, score) tuples, sorted by relevance
        """
        if not documents:
            return []
        
        # Zhipu API endpoint for rerank (using chat format with ranking)
        url = f"{self.api_base}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # For reranking, we compute embeddings and calculate similarity
        # This is a fallback since Zhipu may not have a dedicated rerank endpoint
        try:
            # Get query embedding
            query_resp = httpx.post(
                url,
                headers=headers,
                json={"model": "embedding-2", "input": [query]},
                timeout=30.0
            )
            query_resp.raise_for_status()
            query_embedding = query_resp.json()["data"][0]["embedding"]
            
            # Get document embeddings (in batches of 16 due to API limits)
            doc_embeddings = []
            for i in range(0, len(documents), 16):
                batch = documents[i:i+16]
                doc_resp = httpx.post(
                    url,
                    headers=headers,
                    json={"model": "embedding-2", "input": batch},
                    timeout=60.0
                )
                doc_resp.raise_for_status()
                for item in doc_resp.json()["data"]:
                    doc_embeddings.append(item["embedding"])
            
            # Calculate cosine similarity
            scores = []
            for idx, doc_emb in enumerate(doc_embeddings):
                # Cosine similarity
                dot_product = sum(a * b for a, b in zip(query_embedding, doc_emb))
                query_norm = sum(a * a for a in query_embedding) ** 0.5
                doc_norm = sum(b * b for b in doc_emb) ** 0.5
                similarity = dot_product / (query_norm * doc_norm) if query_norm * doc_norm > 0 else 0
                scores.append((idx, similarity))
            
            # Sort by score descending
            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[:top_n]
            
        except Exception as e:
            print(f"Rerank API error: {e}")
            # Fallback: return original order
            return [(i, 1.0 - i * 0.01) for i in range(min(top_n, len(documents)))]


class BM25Index:
    """BM25 keyword search index with Chinese tokenization and persistence"""
    _dict_loaded = False  # Class-level flag to load dict only once
    
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.documents: List[str] = []
        self.doc_ids: List[str] = []
        # Store a simple hash of all doc_ids to quickly check integrity
        self.ids_hash: str = "" 
        self.metadatas: List[Dict] = []
        self.bm25: Optional[BM25Okapi] = None
        
        # Persistence settings
        self.persist_directory = persist_directory
        self.cache_path = os.path.join(persist_directory, "bm25_index.pkl")
        
        # Load EDA domain dictionary (once per process)
        if not BM25Index._dict_loaded:
            dict_path = os.path.join(os.path.dirname(__file__), "eda_terms.txt")
            if os.path.exists(dict_path):
                jieba.load_userdict(dict_path)
                print(f"📖 Loaded EDA dictionary: {dict_path}")
            BM25Index._dict_loaded = True
            
    def save(self):
        """Save BM25 index and data to disk"""
        if not self.documents:
            return
            
        try:
            start_time = time.time()
            data = {
                "documents": self.documents,
                "doc_ids": self.doc_ids,
                "metadatas": self.metadatas,
                "ids_hash": self.ids_hash,
                "bm25": self.bm25
            }
            with open(self.cache_path, 'wb') as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
            print(f"   💾 BM25 Index saved to {self.cache_path} ({len(self.documents)} docs, {time.time()-start_time:.2f}s)")
        except Exception as e:
            print(f"   ⚠️ Failed to save BM25 index: {e}")

    @staticmethod
    def compute_ids_hash(doc_ids: List[str]) -> str:
        """Compute order-insensitive fingerprint from ids/keys."""
        if not doc_ids:
            return ""
        hasher = hashlib.md5()
        for doc_id in sorted(str(x) for x in doc_ids):
            hasher.update(doc_id.encode("utf-8", errors="ignore"))
            hasher.update(b"\n")
        return hasher.hexdigest()

    @staticmethod
    def build_stable_keys(metadatas: List[Dict], fallback_ids: Optional[List[str]] = None) -> List[str]:
        """
        Build stable per-document keys from metadata.
        Falls back to ids/index when metadata fields are missing.
        """
        keys: List[str] = []
        fallback_ids = fallback_ids or []
        for idx, meta in enumerate(metadatas):
            m = meta if isinstance(meta, dict) else {}
            source = str(m.get("source", ""))
            chunk_id = str(m.get("chunk_id", ""))
            parent_id = str(m.get("parent_id", ""))

            if source or chunk_id or parent_id:
                keys.append(f"{source}::{chunk_id}::{parent_id}")
            elif idx < len(fallback_ids):
                keys.append(str(fallback_ids[idx]))
            else:
                keys.append(str(idx))
        return keys

    def load(self, expected_count: int = -1, expected_ids_hash: str = "") -> bool:
        """
        Load BM25 index from disk.
        
        Args:
            expected_count: If >= 0, verify that cached doc count matches this number.
            
        Returns:
            True if loaded successfully and passed integrity checks, False otherwise.
        """
        if not os.path.exists(self.cache_path):
            return False
            
        try:
            start_time = time.time()
            with open(self.cache_path, 'rb') as f:
                data = pickle.load(f)
            
            # Integrity Checks
            cached_len = len(data.get("documents", []))
            
            # 1. Count check (Fastest)
            if expected_count >= 0 and cached_len != expected_count:
                print(f"   ⚠️ BM25 Cache mismatch: Cache={cached_len}, DB={expected_count}. Rebuilding...")
                return False

            # 2. Fingerprint check (detect stale cache with same count)
            cached_hash = data.get("ids_hash", "")
            needs_hash_migration_save = False
            if expected_ids_hash and cached_hash and cached_hash != expected_ids_hash:
                # Backward-compatible migration for legacy cache hash algorithm.
                migrated_hash = self.compute_ids_hash(
                    self.build_stable_keys(
                        data.get("metadatas", []),
                        data.get("doc_ids", [])
                    )
                )
                if migrated_hash == expected_ids_hash:
                    data["ids_hash"] = migrated_hash
                    needs_hash_migration_save = True
                    print("   ℹ️ BM25 Cache hash migrated to stable format.")
                else:
                    print("   ⚠️ BM25 Cache id hash mismatch. Rebuilding...")
                    return False
                
            # restore state
            self.documents = data["documents"]
            self.doc_ids = data["doc_ids"]
            self.metadatas = data["metadatas"]
            self.ids_hash = data.get("ids_hash", "")
            self.bm25 = data["bm25"]

            if needs_hash_migration_save:
                # Persist migrated hash so next startup can hit cache directly.
                self.save()
            
            print(f"   ⚡ BM25 Index loaded from cache ({cached_len} docs, {time.time()-start_time:.2f}s)")
            return True
            
        except Exception as e:
            print(f"   ⚠️ Failed to load BM25 cache: {e}. Rebuilding...")
            return False
    
    def add_documents(self, documents: List[Document]):
        """Add documents to BM25 index and persist"""
        if not documents:
            return
            
        for doc in documents:
            self.documents.append(doc.page_content)
            self.doc_ids.append(doc.metadata.get("id", str(len(self.doc_ids))))
            self.metadatas.append(doc.metadata)
        
        self._rebuild_index()
        self.save() # Auto-save after modification

    def replace_documents(self, documents: List[Document]):
        """Replace all documents in BM25 index and persist."""
        self.documents = []
        self.doc_ids = []
        self.metadatas = []
        self.bm25 = None
        self.ids_hash = ""

        if not documents:
            self.save()
            return

        for doc in documents:
            self.documents.append(doc.page_content)
            self.doc_ids.append(doc.metadata.get("id", str(len(self.doc_ids))))
            self.metadatas.append(doc.metadata)

        self._rebuild_index()
        self.save()
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text using jieba with EDA domain dictionary"""
        tokens = list(jieba.cut(text))
        # Filter out whitespace and single-char punctuation
        return [t for t in tokens if t.strip() and len(t.strip()) > 0]
    
    def _rebuild_index(self):
        """Rebuild BM25 index"""
        if not self.documents:
            self.bm25 = None
            self.ids_hash = ""
            return
        
        # Update hash for integrity check (metadata-based, order-insensitive)
        if self.metadatas:
            stable_keys = self.build_stable_keys(self.metadatas, self.doc_ids)
            self.ids_hash = self.compute_ids_hash(stable_keys)
        else:
            self.ids_hash = self.compute_ids_hash(self.doc_ids)
            
        tokenized_docs = [self._tokenize(doc) for doc in self.documents]
        self.bm25 = BM25Okapi(tokenized_docs)
    
    def search(self, query: str, top_k: int = 20) -> List[Tuple[int, float]]:
        """
        Search for documents matching query
        
        Returns:
            List of (doc_index, score) tuples
        """
        if self.bm25 is None or not self.documents:
            return []
        
        tokenized_query = self._tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)
        
        # Get top-k indices
        indexed_scores = [(i, score) for i, score in enumerate(scores)]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        return indexed_scores[:top_k]
    
    def clear(self):
        """Clear the index and delete cache"""
        self.documents = []
        self.doc_ids = []
        self.metadatas = []
        self.bm25 = None
        self.ids_hash = ""
        
        if os.path.exists(self.cache_path):
            try:
                os.remove(self.cache_path)
                print("   🗑️ BM25 Cache deleted.")
            except Exception:
                pass


class AdvancedRAGEngine:
    """
    Advanced RAG Engine with:
    - Hybrid Search (Vector + BM25)
    - Reranking
    - Configurable chunking
    - Parent document retrieval
    - Persistent Chat History (SQLite)
    """
    
    def __init__(self):
        # Load configuration from environment
        self.persist_directory = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
        
        # ---------------------------------------------------------
        # 1. Unified Model Configuration (OpenAI-compatible)
        # ---------------------------------------------------------
        
        # Chat Model
        self.chat_api_key = os.getenv("CHAT_API_KEY")
        self.chat_api_base = os.getenv("CHAT_API_BASE", "https://api.deepseek.com/v1")
        self.chat_model = os.getenv("CHAT_MODEL", "deepseek-chat")
        self.chat_thinking_model = os.getenv("CHAT_THINKING_MODEL", "")

        # Embedding Model
        self.embedding_api_key = os.getenv("EMBEDDING_API_KEY")
        self.embedding_api_base = os.getenv("EMBEDDING_API_BASE", "https://api.siliconflow.cn/v1")
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

        # Rerank Settings
        self.rerank_enabled = os.getenv("RERANK_ENABLED", "true").lower() == "true"
        self.rerank_api_key = os.getenv("RERANK_API_KEY", self.embedding_api_key)
        self.rerank_api_base = os.getenv("RERANK_API_BASE", self.embedding_api_base)
        self.rerank_model = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
        
        # RAG Parameters
        self.retrieval_top_k = int(os.getenv("RETRIEVAL_TOP_K", "100"))
        self.rerank_top_n = int(os.getenv("RERANK_TOP_N", "20"))
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "1500"))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "200"))
        
        print(f"🚀 Initializing Advanced RAG Engine (Unified Config)")
        print(f"   📝 Chat: {self.chat_api_base} / {self.chat_model}")
        if self.chat_thinking_model:
            print(f"   🧠 Thinking: {self.chat_thinking_model}")
        print(f"   🔢 Embedding: {self.embedding_api_base} / {self.embedding_model}")
        if self.rerank_enabled:
            print(f"   🎯 Rerank: {self.rerank_api_base} / {self.rerank_model}")
        print(f"   Parameters: top_k={self.retrieval_top_k}, top_n={self.rerank_top_n}, chunk={self.chunk_size}")

        # Initialize database
        self.db = ChatHistoryDB()
        
        # Initialize embeddings (Standard OpenAI-compatible)
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=self.embedding_api_key,
            openai_api_base=self.embedding_api_base,
            model=self.embedding_model,
            chunk_size=16
        )
        
        # Initialize vector store
        self.vectorstore = self._init_vectorstore()
        
        # Initialize BM25 index
        self.bm25_index = BM25Index(persist_directory=self.persist_directory)
        self._load_bm25_index()
        
        # Initialize PDF Processor
        self.pdf_processor = PDFProcessor()
        
        # Load parent documents from persistence
        self.parent_docs: Dict[str, Dict[str, str]] = self._load_parent_docs()
        
        # Load Tool Configuration
        self.tool_config_path = os.path.join(os.path.dirname(__file__), "tools_config.json")
        self.tool_config = self._load_tool_config()
        
        # Initialize reranker (Unified implementation)
        if self.rerank_enabled:
            # We can use a single Reranker class that handles OpenAI-compatible Rerank APIs
            # For now, let's stick to SiliconFlow style if base is siliconflow, else Fallback
            if "siliconflow" in self.rerank_api_base.lower():
                self.reranker = SiliconFlowReranker(
                    api_key=self.rerank_api_key,
                    api_base=self.rerank_api_base,
                    model=self.rerank_model
                )
            else:
                # Fallback to a general reranker or existing ZhipuReranker logic 
                # tweaked for unified base/url
                self.reranker = SiliconFlowReranker( # Reusing SiliconFlowReranker as it's standard OpenAI-like
                    api_key=self.rerank_api_key,
                    api_base=self.rerank_api_base,
                    model=self.rerank_model
                )
        else:
            self.reranker = None
        
        # Initialize LLM instances
        # 1. Standard LLM
        self.llm = ChatOpenAI(
            openai_api_key=self.chat_api_key,
            openai_api_base=self.chat_api_base,
            model_name=self.chat_model,
            temperature=0.3,
            streaming=False
        )
        # 2. Thinking LLM (Optional)
        if self.chat_thinking_model:
            self.llm_thinking = ChatOpenAI(
                openai_api_key=self.chat_api_key,
                openai_api_base=self.chat_api_base,
                model_name=self.chat_thinking_model,
                temperature=0.3, # Thinking models usually ignore temp or need it low
                streaming=False
            )
        else:
            self.llm_thinking = None
        
        # Text splitter for chunking
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", "；", ",", " ", ""]
        )
        
        # Markdown header splitter for semantic chunking
        self.md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "h1"),
                ("##", "h2"),
                ("###", "h3"),
            ]
        )
        
        # Conversation memory storage (In-memory cache for speed during session)
        self.conversations: Dict[str, ChatMessageHistory] = {}
        
        # Initialize Agentic RAG Graph
        from agentic_rag import AgenticRAGGraph
        self.agentic_graph_builder = AgenticRAGGraph(self)
        self.agentic_app = self.agentic_graph_builder.build_graph()
        print("   🤖 Agentic RAG Graph initialized")
    
    def _init_vectorstore(self) -> Chroma:
        """Initialize or load existing ChromaDB vector store"""
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        
        return Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
            collection_name="knowledge_base"
        )
    
    def _load_parent_docs(self) -> Dict[str, Any]:
        """Load parent documents from JSON file"""
        parent_docs_path = os.path.join(self.persist_directory, "parent_docs.json")
        if os.path.exists(parent_docs_path):
            try:
                with open(parent_docs_path, 'r', encoding='utf-8') as f:
                    print(f"📖 Loading parent docs from {parent_docs_path}...")
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Error loading parent docs: {e}")
                return {}
        return {}

    def _save_parent_docs(self):
        """Save parent documents to JSON file"""
        parent_docs_path = os.path.join(self.persist_directory, "parent_docs.json")
        try:
            # Atomic write pattern to prevent corruption
            temp_path = parent_docs_path + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self.parent_docs, f, ensure_ascii=False, indent=2)
            
            if os.path.exists(parent_docs_path):
                os.replace(temp_path, parent_docs_path)
            else:
                os.rename(temp_path, parent_docs_path)
                
            print(f"💾 Saved parent docs to {parent_docs_path}")
        except Exception as e:
            print(f"⚠️ Error saving parent docs: {e}")

    def _load_tool_config(self) -> Dict:
        """Load tool configuration from JSON or create default"""
        default_config = {
            "tools": [
                {
                  "id": "fc",
                  "name": "Fusion Compiler (FC)",
                  "filename_patterns": ["fc", "fusion"],
                  "query_keywords": ["fc", "fusion compiler"]
                },
                {
                  "id": "pt",
                  "name": "PrimeTime (PT)",
                  "filename_patterns": ["pt", "primetime"],
                  "query_keywords": ["pt", "primetime", "prime time"]
                },
                {
                  "id": "icc2",
                  "name": "IC Compiler 2 (ICC2)",
                  "filename_patterns": ["icc2", "ic_compiler", "icc"],
                  "query_keywords": ["icc2", "ic compiler", "icc"]
                },
                {
                  "id": "dc",
                  "name": "Design Compiler (DC)",
                  "filename_patterns": ["dc", "design_compiler"],
                  "query_keywords": ["dc", "design compiler"]
                }
            ]
        }
        
        try:
            if os.path.exists(self.tool_config_path):
                with open(self.tool_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    print(f"   🔧 Loaded distributed tool config: {len(config.get('tools', []))} tools")
                    return config
            else:
                # Self-healing: create default config
                print(f"   ⚠️ Tool config not found. Creating default at {self.tool_config_path}")
                with open(self.tool_config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=2, ensure_ascii=False)
                return default_config
        except Exception as e:
            print(f"   ❌ Failed to load tool config: {e}. Using default.")
            return default_config
            
    def _auto_discover_tools(self, scan_all: bool = False) -> List[str]:
        """
        Scan documents to discover new tools and update config.
        
        Args:
            scan_all: If True, scan all parent_docs. If False, this method is 
                     typically called with specific filenames in a different context.
                     NOTE: Currently, this method scans ALL parent_docs keys if scan_all is True.
                     For incremental updates, manual logic is preferred.
        
        Returns:
            List of newly discovered tool names.
        """
        discovered = []
        existing_ids = set(t['id'] for t in self.tool_config.get('tools', []))
        
        print(f"   🔍 Auto-discovering tools from {len(self.parent_docs)} documents...")
        
        # Helper to guess tool from filename
        def guess_tool(filename):
            name = filename.lower().replace('.pdf', '').replace('.md', '')
            # Strategy 1: Partition by underscore or hyphen (e.g., starrc_ug -> starrc)
            parts = re.split(r'[_\-\s]', name)
            if parts and len(parts[0]) > 2: # Avoid tiny prefixes
                return parts[0]
            return None

        candidates = {} # tool_id -> {name, evidence_count}
        
        for filename in self.parent_docs.keys():
            # Check if already covered by existing config
            is_covered = False
            for tool in self.tool_config['tools']:
                 for pattern in tool['filename_patterns']:
                     if pattern in filename.lower():
                         is_covered = True
                         break
                 if is_covered: break
            
            if is_covered:
                continue
                
            # Not covered? Try to guess
            candidate_id = guess_tool(filename)
            if candidate_id:
                if candidate_id not in existing_ids:
                    if candidate_id not in candidates:
                         # Try to extract a nicer name from H1 if available
                         nice_name = candidate_id.title()
                         # Check first parent chunk for H1
                         for chunk_id, content in self.parent_docs[filename].items():
                             # Heuristic: look at the first chunk key which usually contains title
                             # or check content. For now, simple filename based.
                             pass
                             
                         candidates[candidate_id] = candidates.get(candidate_id, 0) + 1

        # Threshold: if a tool ID appears in valid docs, add it
        new_tools = []
        for tool_id, count in candidates.items():
            # Simple heuristic: trust the extraction
            print(f"      🆕 Found potential tool: {tool_id} (from {count} docs)")
            new_tool = {
                "id": tool_id,
                "name": tool_id.title(), # e.g. Starrc
                "filename_patterns": [tool_id],
                "query_keywords": [tool_id]
            }
            self.tool_config['tools'].append(new_tool)
            new_tools.append(tool_id)
            
        if new_tools:
            # Save updated config
            try:
                with open(self.tool_config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.tool_config, f, indent=2, ensure_ascii=False)
                print(f"   💾 Updated tool config with {len(new_tools)} new tools: {new_tools}")
            except Exception as e:
                print(f"   ❌ Failed to save updated tool config: {e}")
                
        return new_tools
    
    def _load_bm25_index(self):
        """Load existing documents into BM25 index (from Cache or DB)"""
        try:
            collection = self.vectorstore._collection
            id_payload = collection.get(include=["metadatas"])
            db_ids = id_payload.get("ids", []) if id_payload else []
            db_metadatas = id_payload.get("metadatas", []) if id_payload else []
            db_doc_count = len(db_ids) if db_ids else len(db_metadatas)
            stable_db_keys = BM25Index.build_stable_keys(db_metadatas, db_ids)
            expected_ids_hash = BM25Index.compute_ids_hash(stable_db_keys)
            
            # Try loading from cache first
            if self.bm25_index.load(
                expected_count=db_doc_count,
                expected_ids_hash=expected_ids_hash
            ):
                return
                
            # Fallback: Full Rebuild from DB
            print(f"   ⚠️ Cache miss or stale. Rebuilding BM25 Index from DB ({db_doc_count} docs)...")
            all_docs = collection.get(include=["documents", "metadatas"])
            
            if all_docs and all_docs.get("documents"):
                docs = [
                    Document(
                        page_content=content,
                        metadata=meta
                    )
                    for content, meta in zip(
                        all_docs["documents"],
                        all_docs.get("metadatas", [{}] * len(all_docs["documents"]))
                    )
                ]
                self.bm25_index.replace_documents(docs)
                print(f"   BM25 Index rebuilt: {len(docs)} documents")
            else:
                self.bm25_index.clear()
                print("   BM25 Index cleared (no documents in vector store)")
        except Exception as e:
            print(f"   BM25 Index loading failed: {e}")
    
    def is_ready(self) -> bool:
        """Check if RAG engine is ready"""
        return self.vectorstore is not None and self.llm is not None
    
    async def ingest_document(self, file_path: str, filename: str) -> int:
        """
        Ingest a document into the knowledge base with semantic chunking
        """
        # Fix: use the caller-provided filename (original name without temp_ prefix).
        # Only fall back to basename if filename is empty/missing.
        if not filename:
            filename = os.path.basename(file_path)

        print(f"📥 Ingesting: {filename}")

        documents = []
        file_ext = Path(file_path).suffix.lower()

        if file_ext == '.pdf':
            # New Strategy: Modular PDF Processor
            # Returns: List[Document], Dict[parent_id, text]
            documents, parent_map = self.pdf_processor.process_pdf(file_path, display_name=filename)

            # Fix source metadata: replace temp filename with original filename
            for doc in documents:
                if doc.metadata.get("source", "") != filename:
                    doc.metadata["source"] = filename

            # Merge into memory and prep for persistence
            if filename not in self.parent_docs:
                self.parent_docs[filename] = {}
            self.parent_docs[filename].update(parent_map)

        elif file_ext in ['.md', '.markdown']:
            # Fallback for MD/TXT (Old Logic)
            if filename not in self.parent_docs:
                 self.parent_docs[filename] = {}

            full_text = self._extract_markdown_text(file_path)
            # Store full text
            self.parent_docs[filename]["full_text"] = full_text

            # Chunk (returns List[Dict])
            chunk_dicts = self._chunk_markdown(full_text, filename)

            # Convert to Documents
            for idx, chunk in enumerate(chunk_dicts):
                doc = Document(
                    page_content=chunk["content"],
                    metadata={
                        "source": filename,
                        "chunk_id": idx,
                        "section": chunk.get("section", ""),
                        "parent_section": chunk.get("parent_section", ""),
                        "parent_id": chunk.get("parent_id", ""),
                        "child_index": chunk.get("child_index", 0),
                        "source_role": "primary"
                    }
                )
                documents.append(doc)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")

        if not documents:
            print(f"   ⚠️ No chunks created for {filename}")
            return 0

        print(f"   📊 Total chunks to index: {len(documents)}")

        # Add to vector store in batches
        import time
        BATCH_SIZE = 4000
        total_batches = (len(documents) - 1) // BATCH_SIZE + 1
        t_vec_start = time.time()
        for i in range(0, len(documents), BATCH_SIZE):
            batch = documents[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            self.vectorstore.add_documents(batch)
            elapsed_total = time.time() - t_vec_start
            print(f"   🔢 Vector indexing: {min(i + BATCH_SIZE, len(documents))}/{len(documents)} chunks "
                  f"(Batch {batch_num}/{total_batches}, Elapsed: {elapsed_total:.1f}s)")
        vec_total = time.time() - t_vec_start
        print(f"   ✅ Vector store done: {len(documents)} chunks in {vec_total:.1f}s")

        # Add to BM25 index
        bm25_count_before = len(self.bm25_index.documents)
        t_bm25 = time.time()
        self.bm25_index.add_documents(documents)
        bm25_elapsed = time.time() - t_bm25
        vocab_size = len(self.bm25_index.bm25.idf) if self.bm25_index.bm25 else 0
        print(f"   📝 BM25 updated: {bm25_count_before} → {len(self.bm25_index.documents)} docs  "
              f"|  vocab={vocab_size}  |  {bm25_elapsed:.1f}s")

        # Persist parent docs
        self._save_parent_docs()
        print(f"   💾 parent_docs.json saved  ({len(self.parent_docs.get(filename, {}))} sections for {filename})")

        return len(documents)

    
    def _extract_pdf_text(self, file_path: str) -> str:
        """Extract text from PDF with page markers"""
        doc = fitz.open(file_path)
        full_text = ""
        
        for page_num, page in enumerate(doc):
            text = page.get_text()
            full_text += f"\n\n## Page {page_num + 1}\n\n{text}"
        
        doc.close()
        return full_text
    
    def _extract_markdown_text(self, file_path: str) -> str:
        """Extract text from Markdown file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def _chunk_pdf(self, text: str) -> List[Dict]:
        """Chunk PDF text with section awareness"""
        chunks = []
        raw_chunks = self.text_splitter.split_text(text)
        
        current_page = "Unknown"
        for chunk in raw_chunks:
            # Try to extract page number from chunk
            page_match = re.search(r'## Page (\d+)', chunk)
            if page_match:
                current_page = f"Page {page_match.group(1)}"
            
            chunks.append({
                "content": chunk,
                "section": current_page,
                "parent_section": ""
            })
        
        return chunks
    
    def _chunk_markdown(self, text: str, filename: str) -> List[Dict]:
        """
        Chunk Markdown with Parent-Child strategy:
        - Each section is stored as a 'parent' chunk (full content)
        - Each section is further split into 'child' chunks for indexing
        - Child chunks carry parent_id for context expansion during retrieval
        """
        child_chunks = []
        
        # Initialize parent storage for this file
        if filename not in self.parent_docs:
            self.parent_docs[filename] = {}
        
        try:
            # Split by headers (MarkdownHeaderTextSplitter)
            md_chunks = self.md_splitter.split_text(text)
            
            for idx, md_chunk in enumerate(md_chunks):
                # Extract section info from metadata
                h1 = md_chunk.metadata.get("h1", "")
                h2 = md_chunk.metadata.get("h2", "")
                h3 = md_chunk.metadata.get("h3", "")
                
                # Generate unique parent_id based on section hierarchy
                section_parts = [p for p in [h1, h2, h3] if p]
                section_name = " > ".join(section_parts) if section_parts else f"Section_{idx}"
                parent_id = f"{filename}::{section_name}"
                
                # Store full section content as parent chunk
                full_content = md_chunk.page_content
                self.parent_docs[filename][parent_id] = full_content
                
                # Split into smaller child chunks for indexing
                # Use smaller chunk size (256) for precise retrieval
                child_chunk_size = min(self.chunk_size, 500)
                
                if len(full_content) > child_chunk_size:
                    # Need to split into smaller chunks
                    sub_chunks = self.text_splitter.split_text(full_content)
                    for sub_idx, sub_chunk in enumerate(sub_chunks):
                        child_chunks.append({
                            "content": sub_chunk,
                            "section": section_name,
                            "parent_section": h1,
                            "parent_id": parent_id,  # Link to parent
                            "child_index": sub_idx
                        })
                else:
                    # Small enough, keep as single child chunk
                    child_chunks.append({
                        "content": full_content,
                        "section": section_name,
                        "parent_section": h1,
                        "parent_id": parent_id,
                        "child_index": 0
                    })
                    
        except Exception as e:
            print(f"Markdown semantic split failed, using fallback: {e}")
            # Fallback to simple chunking without parent tracking
            raw_chunks = self.text_splitter.split_text(text)
            for idx, chunk in enumerate(raw_chunks):
                parent_id = f"{filename}::fallback_{idx}"
                self.parent_docs[filename][parent_id] = chunk
                child_chunks.append({
                    "content": chunk,
                    "section": "",
                    "parent_section": "",
                    "parent_id": parent_id,
                    "child_index": 0
                })
        
        print(f"   📦 Parent-Child: {len(self.parent_docs[filename])} parent sections, {len(child_chunks)} child chunks")
        return child_chunks
    
    def _hybrid_search(self, query: str, top_k: int) -> List[Document]:
        """
        Perform hybrid search combining vector and BM25 results
        
        Args:
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of Document objects
        """
        # Dynamic weight based on query characteristics
        vector_weight, bm25_weight = self._compute_search_weights(query)
        print(f"⚖️  Hybrid Weights: Vector={vector_weight}, BM25={bm25_weight}")
        
        # Vector search
        vector_results = self.vectorstore.similarity_search_with_score(
            query, k=top_k
        )
        
        # BM25 search
        bm25_results = self.bm25_index.search(query, top_k=top_k)
        
        # Merge results using Reciprocal Rank Fusion (RRF)
        doc_scores: Dict[str, float] = {}
        doc_map: Dict[str, Document] = {}
        
        # Add vector results
        for rank, (doc, score) in enumerate(vector_results):
            doc_key = f"{doc.metadata.get('source', '')}_{doc.metadata.get('chunk_id', '')}"
            rrf_score = vector_weight / (60 + rank)  # Weighted RRF
            doc_scores[doc_key] = doc_scores.get(doc_key, 0) + rrf_score
            doc_map[doc_key] = doc
        
        # Add BM25 results
        if self.bm25_index.documents:
            for rank, (doc_idx, bm25_score) in enumerate(bm25_results):
                if doc_idx < len(self.bm25_index.documents):
                    content = self.bm25_index.documents[doc_idx]
                    # FIXED: Use consistent key format with Vector Search
                    metadata = self.bm25_index.metadatas[doc_idx]
                    doc_key = f"{metadata.get('source', '')}_{metadata.get('chunk_id', '')}"
                    rrf_score = bm25_weight / (60 + rank) # Weighted RRF
                    
                    # If we don't have this doc from vector search, add it
                    if doc_key not in doc_scores:
                        doc_scores[doc_key] = rrf_score
                        # Create Document from BM25 result
                        doc_map[doc_key] = Document(
                            page_content=content,
                            metadata=metadata
                        )
                    else:
                        doc_scores[doc_key] += rrf_score
        
        # Sort by RRF score
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Calculate and log fusion statistics
        vector_keys = set(f"{d.metadata.get('source', '')}_{d.metadata.get('chunk_id', '')}" for d, _ in vector_results)
        bm25_keys = set()
        if self.bm25_index.documents:
             for idx, _ in bm25_results:
                 if idx < len(self.bm25_index.metadatas):
                     m = self.bm25_index.metadatas[idx]
                     bm25_keys.add(f"{m.get('source', '')}_{m.get('chunk_id', '')}")
        
        vector_only = size_v = len(vector_keys)
        bm25_only = size_b = len(bm25_keys)
        cross_hits = 0
        
        for key in doc_scores:
            in_v = key in vector_keys
            in_b = key in bm25_keys
            if in_v and in_b:
                cross_hits += 1
                vector_only -= 1
                bm25_only -= 1
        
        print(f"   🔀 RRF Fusion Stats: Vector={size_v}, BM25={size_b} -> Cross-Hits={cross_hits} (Unique: V={vector_only}, B={bm25_only})")
        
        # Return top documents
        result = []
        for doc_key, score in sorted_docs[:top_k]:
            if doc_key in doc_map:
                result.append(doc_map[doc_key])
        
        return result

    def _compute_search_weights(self, query: str) -> Tuple[float, float]:
        """
        Return configurable hybrid search weights from environment variables.
        Defaults to (0.5, 0.5) if not set. Precision is handled by the Reranker.
        """
        try:
            v_w = float(os.getenv("VECTOR_WEIGHT", "0.5"))
            b_w = float(os.getenv("BM25_WEIGHT", "0.5"))
            total = v_w + b_w
            if total <= 0:
                return (0.5, 0.5)
            return (v_w / total, b_w / total)
        except (ValueError, TypeError):
            return (0.5, 0.5)
    
    async def _rerank_documents(self, query: str, documents: List[Document], top_n: int) -> List[Document]:
        """
        Rerank documents using the reranker.
        Stores rerank_score in doc.metadata for downstream confidence thresholding.
        """
        if not self.reranker or not documents:
            return documents[:top_n]
        
        doc_contents = [doc.page_content for doc in documents]
        if hasattr(self.reranker, "rerank_async"):
            reranked = await self.reranker.rerank_async(query, doc_contents, top_n=top_n)
        else:
            # Compatibility path for synchronous reranker implementations
            reranked = await asyncio.to_thread(self.reranker.rerank, query, doc_contents, top_n)
        
        result = []
        for idx, score in reranked:
            if idx < len(documents):
                doc = documents[idx]
                # Store rerank score for downstream use (e.g., confidence thresholding)
                doc.metadata["rerank_score"] = score
                result.append(doc)
        
        return result
    
    def _expand_to_parent(self, child_docs: List[Document]) -> List[Document]:
        """
        Expand child chunks to their full parent section content.
        
        New Strategy (v2):
        - Deduplication by parent_id (Critical for PDF context quality)
        - Max parent count limit (MAX_PARENT_COUNT=8) to control Token cost
        - Sliding Window regression for very large parents (>8000 chars)
        
        Args:
            child_docs: List of retrieved child Document objects
            
        Returns:
            List of parent Document objects with full (or windowed) section content
        """
        MAX_PARENT_COUNT = 8
        MAX_PARENT_SIZE = 8000  # Regression threshold
        WINDOW_SIZE = 2000      # Fallback window size
        
        seen_parent_ids = set()
        parent_docs = []
        
        print(f"   🔄 Expanding {len(child_docs)} child docs to parents...")
        
        for doc in child_docs:
            if len(parent_docs) >= MAX_PARENT_COUNT:
                print(f"   ⚠️ Reached MAX_PARENT_COUNT ({MAX_PARENT_COUNT}). Stopping expansion.")
                break
                
            parent_id = doc.metadata.get("parent_id", "")
            source = doc.metadata.get("source", "")
            
            if not parent_id:
                continue
                
            if parent_id in seen_parent_ids:
                continue
            
            # Look up parent content
            full_parent_content = None
            if source in self.parent_docs:
                full_parent_content = self.parent_docs[source].get(parent_id)
            
            if not full_parent_content:
                # Debug info
                # print(f"   ⚠️ Parent content not found for {parent_id} in {source}")
                continue
                
            seen_parent_ids.add(parent_id)
            
            # Check size for Sliding Window fallback
            final_content = full_parent_content
            is_windowed = False
            
            if len(full_parent_content) > MAX_PARENT_SIZE:
                print(f"   ✂️ Parent {parent_id} too large ({len(full_parent_content)} chars). Applying Sliding Window.")
                # Use Sliding Window around child content
                # Note: valid child_content includes context header, so we strip it to find in parent
                # Actually, our parent content stored in parent_docs usually is just the text (cleaned).
                # But child doc page_content has context header prepended.
                # So we try to match the raw text part.
                
                # Simple extraction of raw text part from child doc
                child_text = doc.page_content.split("\n\n")[-1] # Heuristic: last part after header
                
                start_pos = full_parent_content.find(child_text[:200]) # Try first 200 chars of child
                
                if start_pos != -1:
                    center_pos = start_pos + (len(child_text) // 2)
                    half_window = WINDOW_SIZE // 2
                    start = max(0, center_pos - half_window)
                    end = min(len(full_parent_content), center_pos + half_window)
                    final_content = full_parent_content[start:end]
                    
                    # Add ellipsis
                    if start > 0: final_content = "..." + final_content
                    if end < len(full_parent_content): final_content = final_content + "..."
                    
                    is_windowed = True
                else:
                    # Fallback: take first WINDOW_SIZE
                    final_content = full_parent_content[:WINDOW_SIZE] + "..."
                    is_windowed = True
            
            # Reconstruct Document
            # We preserve the context path from original metadata if available
            parent_doc = Document(
                page_content=final_content,
                metadata={
                    "source": source,
                    "section": doc.metadata.get("section", ""),
                    "parent_id": parent_id,
                    "context": doc.metadata.get("context", ""),
                    "is_parent": True,
                    "is_windowed": is_windowed,
                    "original_child_id": doc.metadata.get("chunk_id", "")
                }
            )
            parent_docs.append(parent_doc)
        return parent_docs

    
    def _get_tool_label(self, filename: str) -> str:
        """Map filename to tool label using loaded config"""
        filename = filename.lower()
        
        # Iterate through configured tools
        for tool in self.tool_config.get("tools", []):
            for pattern in tool.get("filename_patterns", []):
                if pattern in filename:
                    return tool.get("name", filename)
                    
        # Fallback to filename if no match
        return filename

    def _filter_by_source_priority(self, question: str, documents: List[Document]) -> List[Document]:
        """
        Filter and prioritize documents based on tool/source mentioned in the question.
        Uses configurable patterns from tools_config.json.
        """
        import re
        question_lower = question.lower()
        
        # 1. Collect all tools mentioned in the question (support multi-tool queries)
        mentioned_tools = []
        for tool in self.tool_config.get("tools", []):
            keywords = tool.get("query_keywords", [])
            escaped_kws = [re.escape(k) for k in keywords]
            pattern = r'\b(' + '|'.join(escaped_kws) + r')\b'
            if re.search(pattern, question_lower):
                mentioned_tools.append(tool)
        
        # If no specific tool mentioned, return all docs as-is
        if not mentioned_tools:
            return documents
        
        # Collect all filename patterns for mentioned tools
        target_patterns = []
        for tool in mentioned_tools:
            target_patterns.extend(tool.get("filename_patterns", []))
        
        tool_names = [t['name'] for t in mentioned_tools]
        print(f"   📌 Source tagging: targeting {tool_names}")
        
        # 2. Tag docs with source_role — NO TRUNCATION
        # Reranker and Grade will decide relevance.
        primary = []
        supplementary = []
        for doc in documents:
            source = doc.metadata.get("source", "").lower()
            is_match = any(p in source for p in target_patterns)
            if is_match:
                doc.metadata["source_role"] = "primary"
                primary.append(doc)
            else:
                doc.metadata["source_role"] = "supplementary"
                supplementary.append(doc)
        
        print(f"   📊 Source tagging: {len(primary)} primary, {len(supplementary)} supplementary")
        
        # Return primary first, then supplementary — all preserved
        return primary + supplementary
    
    def _enrich_context(self, documents: List[Document], question: str = "") -> str:
        """
        Enrich context with source info and relevance indicators
        
        Args:
            documents: Retrieved documents
            question: Original user question for context optimization
            
        Returns:
            Enriched context string with source attribution
        """
        context_parts = []
        max_content_length = 2500  # Increased for richer context (was 1500)
        
        for idx, doc in enumerate(documents):
            source = doc.metadata.get("source", "Unknown")
            section = doc.metadata.get("section", "")
            content = doc.page_content
            
            # Truncate very long chunks while preserving complete sentences
            if len(content) > max_content_length:
                # Find last sentence boundary
                truncated = content[:max_content_length]
                last_period = max(truncated.rfind('。'), truncated.rfind('.'), truncated.rfind('\n'))
                if last_period > max_content_length // 2:
                    content = truncated[:last_period + 1] + "\n[...truncated]"
                else:
                    content = truncated + "..."
            
            # Build context with source info and rank indicator
            tool_label = self._get_tool_label(source)
            role = doc.metadata.get("source_role", "primary")
            role_tag = "主要来源" if role == "primary" else "⚠️ 补充参考(来自其他工具)"
            
            header = f"[参考{idx + 1} | 工具: {tool_label} | 来源: {source} | {role_tag}"
            if section:
                header += f" | 章节: {section}"
            header += "]"
            
            context_parts.append(f"{header}\n{content}")
        
        return "\n\n---\n\n".join(context_parts)




    async def generate_queries(self, question: str) -> List[str]:
        """
        Generate multiple search queries from the user question
        """
        from prompts import MULTI_QUERY_PROMPT
        from langchain_core.messages import HumanMessage
        
        print(f"🧠 Multi-Query: generating diverse search queries...")
        queries = [question]  # Always include original query
        
        try:
            rewrite_response = await self.llm.ainvoke([
                HumanMessage(content=MULTI_QUERY_PROMPT.format(question=question))
            ])
            response_text = rewrite_response.content.strip()
            
            # Parse multi-query response
            for line in response_text.split('\n'):
                line = line.strip()
                if line.startswith('QUERY') and ':' in line:
                    query = line.split(':', 1)[1].strip()
                    if query and query != question:
                        queries.append(query)
            
            print(f"   📝 Generated {len(queries)} queries:")
            for i, q in enumerate(queries):
                print(f"      [{i+1}] {q[:80]}{'...' if len(q) > 80 else ''}")
                
        except Exception as e:
            print(f"   ⚠️ Multi-Query generation failed: {e}, using original query only")
            
        return queries
    
    async def query_stream(
        self,
        question: str,
        conversation_id: Optional[str] = None
    ):
        """
        Stream query response from the knowledge base
        
        Yields:
            Dictionary with type ('metadata', 'content', 'error', 'done') and data
        """
        # Create or retrieve conversation memory
        if conversation_id is None:
            conversation_id = self.db.create_conversation("New Chat")
        
        # Save USER message to DB
        self.db.add_message(conversation_id, "user", question)
        
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = ChatMessageHistory()
        
        history = self.conversations[conversation_id]
        
        # Step 0: Multi-Query Generation - Generate multiple queries from different perspectives
        # Step 0: Multi-Query Generation
        queries = await self.generate_queries(question)
        
        # Step 1: Hybrid Search with all queries and merge results
        print(f"🔍 Hybrid Search: retrieving candidates from {len(queries)} queries...")
        all_candidates = {}  # doc_key -> Document (deduplicated)
        
        for query in queries:
            results = self._hybrid_search(query, self.retrieval_top_k // len(queries) + 5)
            for doc in results:
                doc_key = f"{doc.metadata.get('source', '')}_{doc.metadata.get('chunk_id', '')}"
                if doc_key not in all_candidates:
                    all_candidates[doc_key] = doc
        
        candidates = list(all_candidates.values())
        print(f"   📚 Retrieved {len(candidates)} unique candidates")
        
        # Step 1.5: Source Priority Filtering - prioritize docs from mentioned tool
        candidates = self._filter_by_source_priority(question, candidates)
        
        # Step 2: Rerank
        if self.rerank_enabled and self.reranker:
            print(f"🎯 Reranking to top {self.rerank_top_n}...")
            top_docs = await self._rerank_documents(question, candidates, self.rerank_top_n)  # Use original question for rerank
        else:
            top_docs = candidates[:self.rerank_top_n]
        
        # Step 2.5: Parent Expansion - Replace child chunks with parent sections for richer context
        parent_docs = self._expand_to_parent(top_docs)
        if parent_docs:
            # Use parent docs for context, but keep child docs for source attribution
            context_docs = parent_docs
        else:
            # Fallback to child chunks if parent expansion fails
            context_docs = top_docs
        
        # Step 3: Enrich context with question for relevance optimization
        context = self._enrich_context(context_docs, question)
        
        # Format sources
        sources = [
            {
                "content": doc.page_content[:300] + "..." if len(doc.page_content) > 300 else doc.page_content,
                "full_content": doc.page_content,
                "source": doc.metadata.get("source", "Unknown"),
                "chunk_id": doc.metadata.get("chunk_id", 0),
                "section": doc.metadata.get("section", "")
            }
            for doc in top_docs
        ]
        
        # Yield metadata first
        yield {
            "type": "metadata",
            "conversation_id": conversation_id,
            "sources": sources
        }
        
        # Step 4: Generate answer with Strict RAG System Prompt (Grounding-First)
        system_prompt = """你是一个专业的数字芯片后端专家。基于下方的参考资料，为用户提供详尽、结构化的专业回答。

## 核心规则

1. **信息准确**
   - 仅使用参考资料中的信息
   - 关键要点标注来源：`[N]`
   - 不编造未出现的命令或参数

2. **来源区分**
   - 参考资料中标注了每条内容所属的EDA工具（如FC、PT、ICC2等）
   - 当用户明确提问某工具时，**以该工具的文档为准**
   - 标注为"⚠️ 补充参考"的内容来自其他工具，**不要与主要来源混为一谈**
   - 若需引用补充参考，必须明确说明"在 XX 工具中，对应的概念是..."
   - 不同工具中的同名概念（如 constant propagation）可能有不同的含义和配置方式，务必区分

3. **自然表达**
   - **直接回答问题**，不要以"根据参考文档..."开头
   - 像专家同事一样自然对话
   - 信息不足时诚实说明

## 回答结构

### 1. 分类整理
- 按**阶段**或**类型**分组
- 使用层级标题组织

### 2. 详细说明
- **命令/方法名称**（代码格式）
- 作用说明 + 关键参数
- 来源引用 `[N]`

### 3. 总结（如适用）

## 参考资料

{context}

---
直接回答用户问题，保持专业且自然的语气。""".format(context=context)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=question)
        ]
        
        # Stream response
        full_answer = ""
        try:
            async for chunk in self.llm.astream(messages):
                content = chunk.content
                if content:
                    full_answer += content
                    yield {
                        "type": "content",
                        "content": content
                    }
        except Exception as e:
            print(f"Streaming error: {e}")
            yield {"type": "error", "content": str(e)}
        
        # Save ASSISTANT message to DB
        self.db.add_message(conversation_id, "assistant", full_answer, sources)
        
        # Save to in-memory cache
        from langchain_core.messages import HumanMessage as HM, AIMessage as AM
        history.add_message(HM(content=question))
        history.add_message(AM(content=full_answer))
        
        yield {"type": "done"}

    async def query(
        self,
        question: str,
        conversation_id: Optional[str] = None
    ) -> Dict:
        """Sequential query wrapper for backward compatibility"""
        result = {
            "answer": "",
            "sources": [],
            "conversation_id": ""
        }
        
        async for chunk in self.query_stream(question, conversation_id):
            if chunk["type"] == "metadata":
                result["sources"] = chunk["sources"]
                result["conversation_id"] = chunk["conversation_id"]
            elif chunk["type"] == "content":
                result["answer"] += chunk["content"]
        
        return result
    
    async def delete_document(self, filename: str) -> bool:
        """Delete all chunks of a document from all indices"""
        # Delete from vector store
        results = self.vectorstore.get(where={"source": filename})
        has_data = False
        
        if results and results.get("ids"):
            self.vectorstore.delete(ids=results["ids"])
            has_data = True
        
        # Remove from parent docs
        if filename in self.parent_docs:
            del self.parent_docs[filename]
            self._save_parent_docs()  # Sync to disk
            has_data = True
        
        # Rebuild BM25 index (simpler than selective removal)
        if has_data:
            self._load_bm25_index()
        
        return has_data
    
    async def list_documents(self) -> List[Dict]:
        """List all documents in the knowledge base"""
        collection = self.vectorstore._collection
        all_docs = collection.get()
        
        sources = {}
        for metadata in all_docs.get("metadatas", []):
            source = metadata.get("source")
            if source:
                if source not in sources:
                    sources[source] = {"filename": source, "chunks": 0}
                sources[source]["chunks"] += 1
        
        return list(sources.values())
    
    async def clear_all(self):
        """Clear all data from the knowledge base"""
        # Clear vector store
        collection = self.vectorstore._collection
        all_ids = collection.get()["ids"]
        if all_ids:
            collection.delete(ids=all_ids)
        
        # Clear BM25 index
        self.bm25_index.clear()
        
        # Clear parent docs
        self.parent_docs = {}
        self._save_parent_docs()
        
        print("🗑️ All data cleared from knowledge base")

    def get_history(self, limit: int = 50) -> List[Dict]:
        """Get conversation history list"""
        return self.db.get_conversations(limit)

    def get_conversation_messages(self, conversation_id: str) -> List[Dict]:
        """Get messages for a conversation"""
        return self.db.get_messages(conversation_id)
    
    async def query_agentic(self, question: str, conversation_id: Optional[str] = None) -> Dict:
        """
        Agentic RAG Query: LLM decides when and how to retrieve
        
        Uses LangGraph StateGraph to:
        1. Route: Decide if retrieval is needed
        2. Retrieve: Hybrid search if needed
        3. Grade: Evaluate relevance
        4. Rewrite & Retry: If not relevant
        5. Generate: Produce final answer
        
        Args:
            question: User question
            conversation_id: Optional conversation ID for history
            
        Returns:
            Dict with answer, sources, and conversation_id
        """
        # Setup conversation ID
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        print(f"\n{'='*60}")
        print(f"🤖 Agentic RAG Query (ID: {conversation_id[:8]}...)")
        print(f"❓ Question: {question}")
        print(f"{'='*60}\n")
        
        # Initialize state
        initial_state = {
            "question": question,
            "current_query": question,
            "documents": [],
            "generation": "",
            "iteration": 0,
            "route_decision": "",
            "grade_decision": "",
            "conversation_id": conversation_id
        }
        
        # Run LangGraph workflow
        result = await self.agentic_app.ainvoke(initial_state)
        
        # Format response
        answer = result["generation"]
        documents = result.get("documents", [])
        
        sources = [
            {
                "content": doc.page_content[:300] + "..." if len(doc.page_content) > 300 else doc.page_content,
                "source": doc.metadata.get("source", "Unknown"),
                "chunk_id": doc.metadata.get("chunk_id", 0),
                "section": doc.metadata.get("section", "")
            }
            for doc in documents
        ]
        
        # Save to conversation history
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = ChatMessageHistory()
        history = self.conversations[conversation_id]
        history.add_user_message(question)
        history.add_ai_message(answer)
        
        # Save to database
        self.db.add_message(conversation_id, "user", question)
        self.db.add_message(conversation_id, "assistant", answer)
        
        print(f"\n✅ Agentic RAG completed")
        print(f"   Iterations: {result['iteration']}")
        print(f"   Route: {result['route_decision']}")
        print(f"   Answer length: {len(answer)} chars\n")
        
        return {
            "answer": answer,
            "sources": sources,
            "conversation_id": conversation_id,
            "metadata": {
                "iterations": result["iteration"],
                "route": result["route_decision"],
                "grade": result.get("grade_decision", "")
            }
        }
    
    async def query_agentic_stream(self, question: str, conversation_id: Optional[str] = None):
        """
        Streaming Agentic RAG Query
        
        Runs router → retrieve → grade → rewrite loop first,
        then streams the final generation.
        
        Yields:
            dict: SSE-compatible chunks with type and content
        """
        # Setup conversation ID
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        print(f"\n{'='*60}")
        print(f"🤖 Agentic RAG Stream (ID: {conversation_id[:8]}...)")
        print(f"❓ Question: {question}")
        print(f"{'='*60}\n")
        
        # Save user message
        self.db.add_message(conversation_id, "user", question)
        
        # Initialize state for the workflow (without generate)
        initial_state = {
            "question": question,
            "current_query": question,
            "documents": [],
            "generation": "",
            "iteration": 0,
            "route_decision": "",
            "grade_decision": "",
            "conversation_id": conversation_id,
            "skip_generate": True
        }
        
        # Initial status before workflow starts
        yield {
            "type": "reasoning",
            "content": "🤔 **节点追踪** | 正在分析问题意图，准备执行智能路由...\n"
        }

        # Run LangGraph workflow step by step to stream reasoning status
        final_state = dict(initial_state)
        
        async for event in self.agentic_app.astream(initial_state, stream_mode="updates"):
            node_name = list(event.keys())[0]
            node_state = event[node_name]
            final_state.update(node_state)
            
            # Formulate reasoning text based on the node executed (predicting next step)
            reasoning_text = ""
            if node_name == "router":
                route = node_state.get("route_decision", "unknown")
                if route == "retrieve":
                    reasoning_text = "✅ 路由分析完毕：属于领域知识，触发资料查阅动作。\n🔍 **节点追踪** | 正在执行混合知识库检索 (BM25 + 向量检索)..."
                else:
                    reasoning_text = "✅ 路由分析完毕：属于通用问题，跳过检索流程。"
            elif node_name == "retrieve":
                docs = node_state.get("documents", [])
                reasoning_text = f"\n✅ 知识检索成功，共召回 {len(docs)} 个粗排阶段候选片段。\n⚖️ **节点追踪** | 正在调用推理模型对文本片段进行精准维度打分及筛选..."
            elif node_name == "grade":
                docs = node_state.get("documents", [])
                decision = node_state.get("grade_decision", "")
                if decision == "relevant":
                    reasoning_text = f"\n✅ 验证完成：剔除无用噪声，最终保留 {len(docs)} 个极高价值片段用作生成。"
                else:
                    reasoning_text = "\n❌ 验证完成：发现召回片段与原问题相关性过低。\n📝 **节点追踪** | 重写改述原始问题，准备扩大检索面..."
            elif node_name == "rewrite":
                new_query = node_state.get("current_query", "")
                reasoning_text = f"\n🔄 启发式搜索词已优化为: `{new_query}`\n🔍 **节点追踪** | 重新发起二次增强检索..."
                
            if reasoning_text:
                yield {
                    "type": "reasoning",
                    "content": reasoning_text + "\n"
                }

        documents = final_state.get("documents", [])
        route_decision = final_state.get("route_decision", "")
        
        # Format sources for metadata
        sources = [
            {
                "content": doc.page_content[:300] + "..." if len(doc.page_content) > 300 else doc.page_content,
                "full_content": doc.page_content,
                "source": doc.metadata.get("source", "Unknown"),
                "chunk_id": doc.metadata.get("chunk_id", 0),
                "section": doc.metadata.get("section", "")
            }
            for doc in documents
        ]
        
        # Yield metadata first
        yield {
            "type": "metadata",
            "conversation_id": conversation_id,
            "sources": sources,
            "route": route_decision
        }
        
        # If route is direct generate (no retrieval), stream without docs
        if route_decision == "generate":
            documents = []
        
        # Stream the generation
        full_answer = ""
        print("📡 Streaming generation...")
        
        async for chunk in self.agentic_graph_builder.generate_stream(question, documents):
            full_answer += chunk
            yield {
                "type": "content",
                "content": chunk
            }
        
        # Save assistant message
        self.db.add_message(conversation_id, "assistant", full_answer, sources)
        
        # Update conversation memory
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = ChatMessageHistory()
        history = self.conversations[conversation_id]
        history.add_user_message(question)
        history.add_ai_message(full_answer)
        
        print(f"\n✅ Agentic RAG Stream completed ({len(full_answer)} chars)\n")
        
        yield {"type": "done"}

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation"""
        self.db.delete_conversation(conversation_id)
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
        return True


# Alias for backward compatibility
RAGEngine = AdvancedRAGEngine
