from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
import json
from dotenv import load_dotenv

from rag_engine import RAGEngine
from task_manager import TaskManager

# Load environment variables
load_dotenv(override=True)

from contextlib import asynccontextmanager

# Global instances
rag_engine = None
task_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_engine, task_manager
    # Initialize on startup
    print("🚀 Starting up RAG Engine...")
    rag_engine = RAGEngine()
    task_manager = TaskManager()
    yield
    # Cleanup on shutdown
    print("🛑 Shutting down RAG Engine...")

app = FastAPI(
    title="Knowledge Base API",
    description="AI-powered knowledge base with RAG capabilities",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    sources: List[dict]
    conversation_id: str

class UploadResponse(BaseModel):
    filename: str
    status: str
    chunks_created: int

class AsyncUploadResponse(BaseModel):
    task_id: str
    filename: str
    status: str

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "vector_db_status": "connected" if rag_engine.is_ready() else "initializing"
    }


def _validate_upload_file(filename: str) -> str:
    """Validate file extension and return it. Raises HTTPException on invalid."""
    allowed_extensions = ['.pdf', '.md', '.markdown']
    file_ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Only PDF and Markdown files are supported. Got: {file_ext}"
        )
    return file_ext


async def _save_upload_to_temp(file: UploadFile) -> str:
    """Save uploaded file to a temp path using chunked streaming."""
    temp_path = f"./temp_{file.filename}"
    CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB per chunk
    with open(temp_path, "wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)
    return temp_path


@app.post("/upload", response_model=AsyncUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    Async upload: save file and return task_id immediately.
    Document processing runs in background.
    Poll GET /tasks/{task_id} for progress.
    """
    _validate_upload_file(file.filename)

    try:
        temp_path = await _save_upload_to_temp(file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Submit to background task manager
    task_id = task_manager.submit(
        filename=file.filename,
        file_path=temp_path,
        ingest_fn=rag_engine.ingest_document,
    )

    return AsyncUploadResponse(
        task_id=task_id,
        filename=file.filename,
        status="pending",
    )


@app.post("/upload/sync", response_model=UploadResponse)
async def upload_document_sync(file: UploadFile = File(...)):
    """
    Sync upload: wait for processing to complete before responding.
    Use for small files or debugging.
    """
    _validate_upload_file(file.filename)

    try:
        temp_path = await _save_upload_to_temp(file)
        chunks_created = await rag_engine.ingest_document(temp_path, file.filename)
        os.remove(temp_path)

        return UploadResponse(
            filename=file.filename,
            status="success",
            chunks_created=chunks_created,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Query background task status by id"""
    result = task_manager.get_status(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@app.get("/tasks")
async def list_tasks():
    """List all background tasks"""
    return {"tasks": task_manager.list_tasks()}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Ask a question to the knowledge base
    """
    try:
        result = await rag_engine.query(
            question=request.question,
            conversation_id=request.conversation_id
        )
        
        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            conversation_id=result["conversation_id"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream answer from knowledge base
    """
    async def event_generator():
        try:
            async for chunk in rag_engine.query_stream(request.question, request.conversation_id):
                # Send as SSE data
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            error_msg = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_msg)}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/chat/agentic", response_model=ChatResponse)
async def chat_agentic(request: ChatRequest):
    """
    Ask a question using Agentic RAG (LangGraph-based)
    LLM decides when to retrieve and iteratively improves results
    """
    try:
        result = await rag_engine.query_agentic(
            question=request.question,
            conversation_id=request.conversation_id
        )
        
        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            conversation_id=result["conversation_id"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agentic query failed: {str(e)}")

@app.post("/chat/agentic/stream")
async def chat_agentic_stream(request: ChatRequest):
    """
    Stream answer from Agentic RAG
    SSE-compatible streaming with router → retrieve → grade → generate workflow
    """
    async def event_generator():
        try:
            async for chunk in rag_engine.query_agentic_stream(request.question, request.conversation_id):
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            error_msg = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_msg)}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/history")
async def get_history(limit: int = 50):
    """Get chat history list"""
    try:
        return rag_engine.get_history(limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")

@app.get("/history/{conversation_id}")
async def get_conversation_messages(conversation_id: str):
    """Get messages for a conversation"""
    try:
        return rag_engine.get_conversation_messages(conversation_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch messages: {str(e)}")

@app.delete("/history/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation"""
    try:
        rag_engine.delete_conversation(conversation_id)
        return {"status": "success", "id": conversation_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete conversation: {str(e)}")

@app.delete("/documents/{filename}")
async def delete_document(filename: str):
    """
    Delete a document from the knowledge base
    """
    try:
        success = await rag_engine.delete_document(filename)
        if success:
            return {"status": "deleted", "filename": filename}
        else:
            raise HTTPException(status_code=404, detail="Document not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")

@app.get("/documents")
async def list_documents():
    """
    List all documents in the knowledge base
    """
    try:
        documents = await rag_engine.list_documents()
        return {"documents": documents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")

@app.post("/tools/discover")
async def discover_tools():
    """
    Trigger automated tool discovery from existing documents.
    Updates tools_config.json if new tools are found.
    """
    try:
        new_tools = rag_engine._auto_discover_tools(scan_all=True)
        return {
            "status": "success",
            "new_tools": new_tools,
            "count": len(new_tools)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )
