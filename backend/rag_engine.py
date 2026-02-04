"""
Advanced RAG Engine for Knowledge Base
Implements: Hybrid Search (Vector + BM25), Rerank, Semantic Chunking
"""

import os
import re
import uuid
import json
import httpx
from typing import List, Dict, Optional, Tuple
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi
import fitz  # PyMuPDF

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter
)
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
# ConversationalRetrievalChain removed - using direct LLM calls instead
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.documents import Document
from database import ChatHistoryDB


class SiliconFlowReranker:
    """
    True Cross-Encoder Reranker using SiliconFlow /v1/rerank API
    Uses BAAI/bge-reranker-v2-m3 model for precise document relevance scoring
    """
    
    def __init__(self, api_key: str, api_base: str, model: str = "BAAI/bge-reranker-v2-m3"):
        self.api_key = api_key
        self.api_base = api_base.rstrip('/')
        self.model = model
    
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
    """BM25 keyword search index with Chinese tokenization"""
    
    def __init__(self):
        self.documents: List[str] = []
        self.doc_ids: List[str] = []
        self.metadatas: List[Dict] = []
        self.bm25: Optional[BM25Okapi] = None
    
    def add_documents(self, documents: List[Document]):
        """Add documents to BM25 index"""
        for doc in documents:
            self.documents.append(doc.page_content)
            self.doc_ids.append(doc.metadata.get("id", str(len(self.doc_ids))))
            self.metadatas.append(doc.metadata)
        self._rebuild_index()
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text using jieba for Chinese"""
        # Use jieba for Chinese word segmentation
        return list(jieba.cut(text))
    
    def _rebuild_index(self):
        """Rebuild BM25 index"""
        if not self.documents:
            self.bm25 = None
            return
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
        """Clear the index"""
        self.documents = []
        self.doc_ids = []
        self.bm25 = None


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
        # Load configuration from environment
        self.persist_directory = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
        
        # ---------------------------------------------------------
        # 1. Chat Provider Configuration
        # ---------------------------------------------------------
        self.chat_provider = os.getenv("CHAT_PROVIDER", "zhipu").lower()
        print(f"🚀 Initializing Chat Engine (Provider: {self.chat_provider})")
        
        if self.chat_provider == "deepseek":
            self.chat_api_key = os.getenv("DEEPSEEK_API_KEY")
            self.chat_api_base = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
            self.chat_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            
        elif self.chat_provider == "openai":
            self.chat_api_key = os.getenv("OPENAI_API_KEY")
            self.chat_api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
            self.chat_model = os.getenv("OPENAI_MODEL", "gpt-4-turbo")

        elif self.chat_provider == "siliconflow":
            self.chat_api_key = os.getenv("SILICONFLOW_API_KEY")
            self.chat_api_base = os.getenv("SILICONFLOW_API_BASE", "https://api.siliconflow.cn/v1")
            self.chat_model = os.getenv("SILICONFLOW_CHAT_MODEL", "deepseek-ai/DeepSeek-V3")
            
        else: # Default to zhipu
            self.chat_api_key = os.getenv("ZHIPU_API_KEY")
            self.chat_api_base = os.getenv("ZHIPU_API_BASE", "https://open.bigmodel.cn/api/paas/v4/")
            self.chat_model = os.getenv("ZHIPU_CHAT_MODEL", "glm-4-flash")

        # ---------------------------------------------------------
        # 2. Embedding/Rerank Provider Configuration
        # ---------------------------------------------------------
        self.embedding_provider = os.getenv("EMBEDDING_PROVIDER", "zhipu").lower()
        print(f"🚀 Initializing Embedding Engine (Provider: {self.embedding_provider})")

        if self.embedding_provider == "siliconflow":
            self.embedding_api_key = os.getenv("SILICONFLOW_API_KEY")
            self.embedding_api_base = os.getenv("SILICONFLOW_API_BASE", "https://api.siliconflow.cn/v1")
            self.embedding_model = os.getenv("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3")
        else:
            # Default to Zhipu
            self.embedding_api_key = os.getenv("ZHIPU_API_KEY")
            self.embedding_api_base = os.getenv("ZHIPU_API_BASE", "https://open.bigmodel.cn/api/paas/v4/")
            self.embedding_model = os.getenv("ZHIPU_EMBEDDING_MODEL", "embedding-2")
        
        # Advanced RAG settings
        self.rerank_enabled = os.getenv("RERANK_ENABLED", "true").lower() == "true"
        # Rerank model selection based on provider
        if self.embedding_provider == "siliconflow":
            self.rerank_model = os.getenv("SILICONFLOW_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
        else:
            self.rerank_model = os.getenv("RERANK_MODEL", "embedding-rank")
        self.retrieval_top_k = int(os.getenv("RETRIEVAL_TOP_K", "20"))
        self.rerank_top_n = int(os.getenv("RERANK_TOP_N", "5"))
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "500"))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "100"))
        
        print(f"🚀 Initializing Advanced RAG Engine (Multi-Provider)")
        print(f"   📝 Chat: {self.chat_api_base} / {self.chat_model}")
        print(f"   🔢 Embedding: {self.embedding_api_base} / {self.embedding_model}")
        print(f"   Rerank Enabled: {self.rerank_enabled}")
        print(f"   Retrieval Top-K: {self.retrieval_top_k}")
        print(f"   Rerank Top-N: {self.rerank_top_n}")
        print(f"   Chunk Size: {self.chunk_size}")

        # Initialize database
        self.db = ChatHistoryDB()
        
        # Initialize embeddings (using Embedding provider, e.g., Zhipu)
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=self.embedding_api_key,
            openai_api_base=self.embedding_api_base,
            model=self.embedding_model,
            chunk_size=16  # API batch limit
        )
        
        # Initialize vector store
        self.vectorstore = self._init_vectorstore()
        
        # Initialize BM25 index
        self.bm25_index = BM25Index()
        self._load_bm25_index()
        
        # Initialize reranker based on provider
        if self.rerank_enabled:
            if self.embedding_provider == "siliconflow":
                self.reranker = SiliconFlowReranker(
                    api_key=self.embedding_api_key,
                    api_base=self.embedding_api_base,
                    model=self.rerank_model
                )
                print(f"   🎯 Reranker: SiliconFlow / {self.rerank_model}")
            else:
                self.reranker = ZhipuReranker(
                    api_key=self.embedding_api_key,
                    api_base=self.embedding_api_base,
                    model=self.rerank_model
                )
                print(f"   🎯 Reranker: Zhipu / {self.rerank_model}")
        else:
            self.reranker = None
        
        # Initialize LLM (using Chat provider, e.g., DeepSeek)
        self.llm = ChatOpenAI(
            openai_api_key=self.chat_api_key,
            openai_api_base=self.chat_api_base,
            model_name=self.chat_model,
            temperature=0.3,
            streaming=False
        )
        
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
        
        # Parent document storage (filename -> full content by section)
        self.parent_docs: Dict[str, Dict[str, str]] = {}
    
    def _init_vectorstore(self) -> Chroma:
        """Initialize or load existing ChromaDB vector store"""
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        
        return Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
            collection_name="knowledge_base"
        )
    
    def _load_bm25_index(self):
        """Load existing documents into BM25 index"""
        try:
            collection = self.vectorstore._collection
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
                self.bm25_index.add_documents(docs)
                print(f"   BM25 Index loaded: {len(docs)} documents")
        except Exception as e:
            print(f"   BM25 Index loading failed: {e}")
    
    def is_ready(self) -> bool:
        """Check if RAG engine is ready"""
        return self.vectorstore is not None and self.llm is not None
    
    async def ingest_document(self, file_path: str, filename: str) -> int:
        """
        Ingest a document into the knowledge base with semantic chunking
        
        Args:
            file_path: Path to the document file
            filename: Original filename for metadata
            
        Returns:
            Number of chunks created
        """
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext == '.pdf':
            full_text = self._extract_pdf_text(file_path)
            chunks = self._chunk_pdf(full_text)
        elif file_ext in ['.md', '.markdown']:
            full_text = self._extract_markdown_text(file_path)
            chunks = self._chunk_markdown(full_text, filename)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")
        
        # Store parent document for context enrichment
        self.parent_docs[filename] = {"full_text": full_text}
        
        # Create Document objects with rich metadata
        documents = []
        for idx, chunk in enumerate(chunks):
            doc = Document(
                page_content=chunk["content"],
                metadata={
                    "source": filename,
                    "chunk_id": idx,
                    "total_chunks": len(chunks),
                    "section": chunk.get("section", ""),
                    "parent_section": chunk.get("parent_section", "")
                }
            )
            documents.append(doc)
        
        # Add to vector store in batches (Chroma limit is 5461)
        BATCH_SIZE = 4000
        for i in range(0, len(documents), BATCH_SIZE):
            batch = documents[i:i + BATCH_SIZE]
            self.vectorstore.add_documents(batch)
            print(f"   Added batch {i//BATCH_SIZE + 1}/{(len(documents)-1)//BATCH_SIZE + 1} to vector store")
        
        # Add to BM25 index
        self.bm25_index.add_documents(documents)
        
        return len(chunks)
    
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
        """Chunk Markdown with header-based semantic splitting"""
        chunks = []
        
        # First, split by headers
        try:
            md_chunks = self.md_splitter.split_text(text)
            
            for md_chunk in md_chunks:
                # Extract section info from metadata
                section = md_chunk.metadata.get("h2", "") or md_chunk.metadata.get("h1", "")
                parent = md_chunk.metadata.get("h1", "")
                
                # Further split if chunk is too large
                if len(md_chunk.page_content) > self.chunk_size * 2:
                    sub_chunks = self.text_splitter.split_text(md_chunk.page_content)
                    for sub_chunk in sub_chunks:
                        chunks.append({
                            "content": sub_chunk,
                            "section": section,
                            "parent_section": parent
                        })
                else:
                    chunks.append({
                        "content": md_chunk.page_content,
                        "section": section,
                        "parent_section": parent
                    })
        except Exception as e:
            print(f"Markdown semantic split failed, using fallback: {e}")
            # Fallback to simple chunking
            raw_chunks = self.text_splitter.split_text(text)
            for chunk in raw_chunks:
                chunks.append({
                    "content": chunk,
                    "section": "",
                    "parent_section": ""
                })
        
        return chunks
    
    def _hybrid_search(self, query: str, top_k: int) -> List[Document]:
        """
        Perform hybrid search combining vector and BM25 results
        
        Args:
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of Document objects
        """
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
            rrf_score = 1.0 / (60 + rank)  # RRF formula with k=60
            doc_scores[doc_key] = doc_scores.get(doc_key, 0) + rrf_score
            doc_map[doc_key] = doc
        
        # Add BM25 results
        if self.bm25_index.documents:
            for rank, (doc_idx, bm25_score) in enumerate(bm25_results):
                if doc_idx < len(self.bm25_index.documents):
                    content = self.bm25_index.documents[doc_idx]
                    # Create a simple key (this is imperfect but workable)
                    doc_key = f"bm25_{doc_idx}"
                    rrf_score = 1.0 / (60 + rank)
                    
                    # If we don't have this doc from vector search, add it
                    if doc_key not in doc_scores:
                        doc_scores[doc_key] = rrf_score
                        # Create Document from BM25 result
                        doc_map[doc_key] = Document(
                            page_content=content,
                            metadata=self.bm25_index.metadatas[doc_idx]
                        )
                    else:
                        doc_scores[doc_key] += rrf_score
        
        # Sort by RRF score
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Return top documents
        result = []
        for doc_key, score in sorted_docs[:top_k]:
            if doc_key in doc_map:
                result.append(doc_map[doc_key])
        
        return result
    
    def _rerank_documents(self, query: str, documents: List[Document], top_n: int) -> List[Document]:
        """
        Rerank documents using the reranker
        
        Args:
            query: Original query
            documents: Documents to rerank
            top_n: Number of top results to return
            
        Returns:
            Reranked list of documents
        """
        if not self.reranker or not documents:
            return documents[:top_n]
        
        # Extract document contents
        doc_contents = [doc.page_content for doc in documents]
        
        # Get reranked indices
        reranked = self.reranker.rerank(query, doc_contents, top_n=top_n)
        
        # Return reranked documents
        result = []
        for idx, score in reranked:
            if idx < len(documents):
                result.append(documents[idx])
        
        return result
    
    def _filter_by_source_priority(self, question: str, documents: List[Document]) -> List[Document]:
        """
        Filter and prioritize documents based on tool/source mentioned in the question.
        
        If user asks about a specific tool (FC, PT, ICC2, etc.), prioritize documents
        from that tool's documentation.
        
        Args:
            question: User question
            documents: Retrieved documents
            
        Returns:
            Filtered/prioritized list of documents
        """
        # Tool name patterns to source file patterns mapping
        tool_patterns = {
            # Fusion Compiler patterns
            r'\bfc\b|\bfusion\s*compiler\b': ['fc', 'fusion', 'FC'],
            # PrimeTime patterns  
            r'\bpt\b|\bprimetime\b|\bprime\s*time\b': ['pt', 'primetime', 'PT'],
            # ICC2 patterns
            r'\bicc2\b|\bic\s*compiler\s*2?\b': ['icc2', 'icc', 'ICC'],
            # Design Compiler patterns
            r'\bdc\b|\bdesign\s*compiler\b': ['dc', 'design_compiler', 'DC'],
        }
        
        import re
        question_lower = question.lower()
        
        # Find which tool is mentioned in the question
        target_tool_keywords = []
        for pattern, keywords in tool_patterns.items():
            if re.search(pattern, question_lower):
                target_tool_keywords = keywords
                break
        
        # If no specific tool mentioned, return all documents
        if not target_tool_keywords:
            return documents
        
        print(f"   📌 Source filter: prioritizing documents from {target_tool_keywords}")
        
        # Separate matching and non-matching documents
        matching_docs = []
        other_docs = []
        
        for doc in documents:
            source = doc.metadata.get("source", "").lower()
            # Check if source contains any of the target keywords
            if any(kw.lower() in source for kw in target_tool_keywords):
                matching_docs.append(doc)
            else:
                other_docs.append(doc)
        
        print(f"   📊 Found {len(matching_docs)} matching docs, {len(other_docs)} other docs")
        
        # Return matching first, then others (keeps semantic order within each group)
        return matching_docs + other_docs
    
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
            header = f"[参考{idx + 1} | 来源: {source}"
            if section:
                header += f" | 章节: {section}"
            header += "]"
            
            context_parts.append(f"{header}\n{content}")
        
        return "\n\n---\n\n".join(context_parts)
    
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
        print(f"🧠 Multi-Query: generating diverse search queries...")
        multi_query_prompt = """你是EDA/芯片后端设计领域的查询优化专家。请从3个不同角度改写用户问题，用于检索：

【领域术语】
- FC = Fusion Compiler, ICC2 = IC Compiler 2, PNR = Place and Route
- CTS = Clock Tree Synthesis, DRC = Design Rule Check, LVS = Layout vs Schematic
- congestion = 布线拥塞, timing = 时序, setup/hold = 建立/保持时间

【改写要求】
1. 技术术语角度：扩展缩写、同义词、相关工具名
2. 问题类型角度：转换为How-to/What-is/Why形式
3. 上下文角度：补充可能的前提条件或场景

输出格式（每行一个查询，共3行）：
QUERY1: [技术术语扩展版本]
QUERY2: [问题类型转换版本]
QUERY3: [上下文补充版本]

用户问题: {question}"""
        
        from langchain_core.messages import SystemMessage, HumanMessage
        
        queries = [question]  # Always include original query
        try:
            rewrite_response = await self.llm.ainvoke([
                HumanMessage(content=multi_query_prompt.format(question=question))
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
            top_docs = self._rerank_documents(question, candidates, self.rerank_top_n)  # Use original question for rerank
        else:
            top_docs = candidates[:self.rerank_top_n]
        
        # Step 3: Enrich context with question for relevance optimization
        context = self._enrich_context(top_docs, question)
        
        # Format sources
        sources = [
            {
                "content": doc.page_content[:300] + "..." if len(doc.page_content) > 300 else doc.page_content,
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

2. **自然表达**
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
        
        if results and results.get("ids"):
            self.vectorstore.delete(ids=results["ids"])
        
        # Remove from parent docs
        if filename in self.parent_docs:
            del self.parent_docs[filename]
        
        # Rebuild BM25 index (simpler than selective removal)
        self._load_bm25_index()
        
        return True
    
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
        
        print("🗑️ All data cleared from knowledge base")

    def get_history(self, limit: int = 50) -> List[Dict]:
        """Get conversation history list"""
        return self.db.get_conversations(limit)

    def get_conversation_messages(self, conversation_id: str) -> List[Dict]:
        """Get messages for a conversation"""
        return self.db.get_messages(conversation_id)

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation"""
        self.db.delete_conversation(conversation_id)
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
        return True


# Alias for backward compatibility
RAGEngine = AdvancedRAGEngine
