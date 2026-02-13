"""
Agentic RAG using LangGraph
Implements: Router → Retrieve → Grade → Rewrite → Generate workflow
"""

from typing import TypedDict, List, Literal
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END
from prompts import (
    ROUTER_PROMPT,
    GRADE_PROMPT,
    REWRITE_PROMPT,
    GENERATION_SYSTEM_PROMPT
)


class AgentState(TypedDict):
    """State for Agentic RAG workflow"""
    question: str                # Original user question
    current_query: str           # Current query (may be rewritten)
    documents: List[Document]    # Retrieved documents
    generation: str              # Generated answer
    iteration: int               # Iteration count (prevent infinite loops)
    route_decision: str          # Router decision: "retrieve" or "generate"
    grade_decision: str          # Grade decision: "relevant" or "not_relevant"
    conversation_id: str         # Conversation ID for history
    skip_generate: bool          # Flag to skip generation (for external streaming)


class AgenticRAGGraph:
    """
    LangGraph-based Agentic RAG workflow
    
    Workflow:
        START → Router → [Retrieve → Grade → (Rewrite)?] → Generate → END
    """
    
    def __init__(self, rag_engine):
        """
        Args:
            rag_engine: AdvancedRAGEngine instance with existing retrieval logic
        """
        self.rag_engine = rag_engine
        self.max_iterations = 3  # Prevent infinite retrieval loops
        
    # ========================================
    # Node Functions
    # ========================================
    
    async def router_node(self, state: AgentState) -> AgentState:
        """
        Router: Decide if retrieval is needed
        
        Simple queries (greetings, chit-chat) → direct generation
        Technical queries → retrieval
        """
        question = state["question"]
        
        # Use LLM to classify the query type
        router_prompt = ROUTER_PROMPT.format(question=question)
        
        response = await self.rag_engine.llm.ainvoke(router_prompt)
        decision = response.content.strip().lower()
        
        if "retrieve" in decision:
            state["route_decision"] = "retrieve"
        else:
            state["route_decision"] = "generate"
        
        print(f"🔀 Router Decision: {state['route_decision']}")
        return state
    
    async def retrieve_node(self, state: AgentState) -> AgentState:
        """
        Retrieve: Use existing hybrid search + rerank with Query Expansion
        """
        query = state["current_query"]
        
        # 1. Generate Multiple Queries (Query Expansion)
        queries = await self.rag_engine.generate_queries(query)
        
        print(f"🔍 Retrieving for {len(queries)} queries...")
        
        all_documents = []
        seen_contents = set()
        
        # 2. Retrieve for each query
        for q in queries:
            # Use configured retrieval limit (divided by num queries to act as a pool or just strict top-k)
            # For expansion, we usually want roughly top-k per query or a fraction. 
            # Given we have 100 top-k, let's use it directly or slightly reduced if many queries.
            # Using full configured top-k ensures finding the needle.
            docs = self.rag_engine._hybrid_search(q, top_k=self.rag_engine.retrieval_top_k)
            for doc in docs:
                if doc.page_content not in seen_contents:
                    all_documents.append(doc)
                    seen_contents.add(doc.page_content)
        
        # 3. Filter by source priority if applicable (using original query for intent)
        all_documents = self.rag_engine._filter_by_source_priority(query, all_documents)
        
        # 4. Rerank (Global Rerank)
        if self.rag_engine.rerank_enabled and len(all_documents) > 0:
            # Rerank candidates to get configured top-n
            documents = self.rag_engine._rerank_documents(query, all_documents, top_n=self.rag_engine.rerank_top_n)
        else:
            documents = all_documents[:self.rag_engine.rerank_top_n]
        
        # Parent Expansion moved to Generate phase to ensure Grading sees focused child chunks
        
        state["documents"] = documents
        state["iteration"] += 1
        
        print(f"   Retrieved {len(documents)} relevant documents after expansion & rerank")
        return state
    
    async def grade_node(self, state: AgentState) -> AgentState:
        """
        Grade: Evaluate relevance of retrieved documents
        """
        documents = state["documents"]
        question = state["current_query"]
        
        if not documents:
            state["grade_decision"] = "not_relevant"
            print("⚠️  No documents retrieved")
            return state
        
        # Robust Multi-Document Grading
        relevant_docs = []
        print(f"📝 Grading {len(documents)} documents...")
        
        for i, doc in enumerate(documents):
            # Limit content to first 1000 chars for grading to save tokens
            doc_snippet = doc.page_content[:1000]
            
            grade_msg = GRADE_PROMPT.format(question=question, document_snippet=doc_snippet)
            
            response = await self.rag_engine.llm.ainvoke(grade_msg)
            import json
            try:
                # Basic cleanup for JSON parsing (remove markdown fences if present)
                content = response.content.replace('```json', '').replace('```', '').strip()
                grade_data = json.loads(content)
                score = grade_data.get("score", "no").lower()
                reason = grade_data.get("reason", "No reason provided")
                
                if "yes" in score:
                    print(f"   ✅ Doc {i+1} is relevant. Reason: {reason}")
                    relevant_docs.append(doc)
                else:
                    print(f"   ❌ Doc {i+1} is NOT relevant. Reason: {reason}")
            except Exception as e:
                print(f"   ⚠️ Grading JSON parse error: {e}. Raw content: {response.content}")
                # Fallback: if yes is in content, assume relevant
                if "yes" in response.content.lower():
                    print(f"   ✅ (Fallback) Doc {i+1} is relevant")
                    relevant_docs.append(doc)
                else:
                    print(f"   ❌ (Fallback) Doc {i+1} is NOT relevant")
        
        if relevant_docs:
            # key fix: Do NOT filter out documents. Keep original context for generation to avoid false negatives.
            # We only use grading to decide whether to Rewrite or Generate.
            # state["documents"] = relevant_docs  <-- DISABLED FILTERING
            state["grade_decision"] = "relevant"
            print(f"🎯 Grading passed: found {len(relevant_docs)} relevant docs (process all)")
        else:
            state["grade_decision"] = "not_relevant"
            print("❌ No relevant documents found after grading")
        
        return state
    
    async def rewrite_node(self, state: AgentState) -> AgentState:
        """
        Rewrite: Reformulate query to improve retrieval
        """
        original_question = state["question"]
        current_query = state["current_query"]
        
        rewrite_prompt = REWRITE_PROMPT.format(original_question=original_question, current_query=current_query)
        
        response = await self.rag_engine.llm.ainvoke(rewrite_prompt)
        rewritten = response.content.strip()
        
        state["current_query"] = rewritten
        print(f"✏️  Rewritten query: {rewritten}")
        
        return state
    
    async def generate_node(self, state: AgentState) -> AgentState:
        """
        Generate: Produce final answer
        """
        question = state["question"]
        documents = state["documents"]
        route_decision = state["route_decision"]
        
        # Check if we should skip generation (for streaming)
        if state.get("skip_generate", False):
            print("⏩ Skipping generation (will stream externally)")
            state["generation"] = ""
            return state
        
        # If no retrieval was needed, answer directly
        if route_decision == "generate" or not documents:
            context = "No specific context needed."
        else:
            # Enrich context with parent documents for better generation quality
            # Expand child chunks to parent chunks HERE, just before generation
            parent_docs = self.rag_engine._expand_to_parent(documents)
            context_docs = parent_docs if parent_docs else documents
            
            # Enrich context with surrounding chunks
            context = self._format_context(context_docs)
        
        # Use detailed system prompt matching traditional RAG quality
        system_prompt = GENERATION_SYSTEM_PROMPT
        
        user_prompt = question
        
        # Generate answer using formatted prompt
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=system_prompt.format(context=context)),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.rag_engine.llm.ainvoke(messages)
        answer = response.content
        
        state["generation"] = answer
        print(f"💬 Generated answer ({len(answer)} chars)")
        
        return state
    
    async def generate_stream(self, question: str, documents: List[Document]):
        """
        Stream generate answer for Agentic RAG
        
        Yields:
            str: Chunks of the generated answer
        """
        if not documents:
            context = "No specific context needed."
        else:
            # Expand child chunks to parent chunks for streaming generation too
            parent_docs = self.rag_engine._expand_to_parent(documents)
            context_docs = parent_docs if parent_docs else documents
            
            context = self._format_context(context_docs)
        
        system_prompt = GENERATION_SYSTEM_PROMPT
        
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=system_prompt.format(context=context)),
            HumanMessage(content=question)
        ]
        
        async for chunk in self.rag_engine.llm.astream(messages):
            if chunk.content:
                yield chunk.content
    
    def _format_context(self, documents: List[Document]) -> str:
        """Format documents into context string"""
        if not documents:
            return "无相关上下文"
        
        context_parts = []
        # Use all documents passed (they should already be filtered/reranked top-n)
        # Limit just in case to avoid context overflow if top-n is huge
        for i, doc in enumerate(documents[:self.rag_engine.rerank_top_n], 1):
            source = doc.metadata.get("source", "Unknown")
            tool_label = self.rag_engine._get_tool_label(source)
            role = doc.metadata.get("source_role", "primary")
            role_tag = "主要来源" if role == "primary" else "⚠️ 补充参考(来自其他工具)"
            
            content = doc.page_content
            context_parts.append(f"[{i}] 工具: {tool_label} | 来源: {source} | {role_tag}\n{content}\n")
        
        return "\n".join(context_parts)
    
    # ========================================
    # Routing Functions
    # ========================================
    
    def route_after_router(self, state: AgentState) -> Literal["retrieve", "generate"]:
        """Route after Router node"""
        if state["route_decision"] == "retrieve":
            return "retrieve"
        else:
            return "generate"
    
    def route_after_grade(self, state: AgentState) -> Literal["generate", "rewrite", "END"]:
        """Route after Grade node"""
        # If already iterated too many times, stop
        if state["iteration"] >= self.max_iterations:
            print(f"⚠️  Max iterations ({self.max_iterations}) reached, generating with current docs")
            return "generate"
        
        # If documents are relevant, generate
        if state["grade_decision"] == "relevant":
            return "generate"
        else:
            # Not relevant, rewrite and retry
            return "rewrite"
    
    # ========================================
    # Build Graph
    # ========================================
    
    def build_graph(self) -> StateGraph:
        """
        Build and compile the LangGraph StateGraph
        
        Graph structure:
            START → router → [retrieve → grade → (rewrite)?] → generate → END
        """
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("router", self.router_node)
        workflow.add_node("retrieve", self.retrieve_node)
        workflow.add_node("grade", self.grade_node)
        workflow.add_node("rewrite", self.rewrite_node)
        workflow.add_node("generate", self.generate_node)
        
        # Set entry point
        workflow.set_entry_point("router")
        
        # Add conditional edges
        workflow.add_conditional_edges(
            "router",
            self.route_after_router,
            {
                "retrieve": "retrieve",
                "generate": "generate"
            }
        )
        
        # After retrieve, always grade
        workflow.add_edge("retrieve", "grade")
        
        # After grade, decide
        workflow.add_conditional_edges(
            "grade",
            self.route_after_grade,
            {
                "generate": "generate",
                "rewrite": "rewrite",
                "END": END
            }
        )
        
        # After rewrite, retrieve again
        workflow.add_edge("rewrite", "retrieve")
        
        # After generate, end
        workflow.add_edge("generate", END)
        
        return workflow.compile()
