# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A RAG (Retrieval-Augmented Generation) knowledge base system for digital backend EDA tools. Features admin document management via CLI and user chat interface via web.

## Architecture

### Tech Stack
- **Backend**: FastAPI + LangChain + ChromaDB + PyMuPDF
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind CSS
- **LLM Providers**: DeepSeek / Zhipu (GLM) / OpenAI
- **Storage**: ChromaDB (vectors), SQLite (chat history)

### Core Components

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app with endpoints for upload, chat, history |
| `backend/rag_engine.py` | Core RAG: hybrid search (vector + BM25), reranking, semantic chunking, parent document expansion |
| `backend/agentic_rag.py` | LangGraph-based Agentic RAG: Router → Retrieve → Grade → Generate workflow |
| `backend/pdf_processor.py` | PDF processing with TOC-based semantic slicing |
| `backend/admin_cli.py` | Admin CLI for document management |
| `backend/task_manager.py` | Async task management for document processing |
| `backend/database.py` | SQLite-based chat history storage |

### Key RAG Features
- **Hybrid Search**: Vector search + BM25 keyword search with RRF fusion
- **Reranking**: SiliconFlow bge-reranker-v2-m3 or Zhipu embedding-rank
- **Query Expansion**: Generate multiple queries for better retrieval
- **Parent Document Expansion**: Expand child chunks to parent docs with sliding window (max 8000 chars)
- **Strict Semantic Slicing**: TOC-based PDF chunking preserving document hierarchy

## Commands

### Start Backend
```powershell
cd backend
.\venv\Scripts\activate
py -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Or use: `.\start_backend.bat`

### Start Frontend
```powershell
cd frontend
npm run dev
```
Or use: `.\start_frontend.bat`

### Admin CLI (document management)
```powershell
cd backend
py admin_cli.py --help

# Upload document (async)
py admin_cli.py upload path/to/document.pdf

# Upload directory (auto-skip existing)
py admin_cli.py upload D:\EDA_Docs\Innovus

# List documents
py admin_cli.py list

# Delete document
py admin_cli.py delete document.pdf

# Clear knowledge base
py admin_cli.py clear --fast

# Tool discovery (scan filenames to update tools_config.json)
py admin_cli.py discover-tools

# Check status
py admin_cli.py status
```

### API Endpoints
- Health: `GET /health`
- Upload: `POST /upload` (async) or `POST /upload/sync`
- Chat: `POST /chat` or `POST /chat/stream` or `POST /chat/agentic/stream`
- History: `GET /history`, `DELETE /history/{conversation_id}`
- Documents: `GET /documents`, `DELETE /documents/{filename}`

## Configuration

Edit `backend/.env`:
```env
# LLM Provider: deepseek / zhipu / openai
LLM_PROVIDER=zhipu

# Zhipu AI (default)
ZHIPU_API_KEY=your_key
ZHIPU_CHAT_MODEL=glm-4-flash
ZHIPU_EMBEDDING_MODEL=embedding-2

# or DeepSeek
DEEPSEEK_API_KEY=your_key
DEEPSEEK_MODEL=deepseek-chat
```

## Environment Setup
```powershell
cd backend
py -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install requests -i https://pypi.tuna.tsinghua.edu.cn/simple
```
