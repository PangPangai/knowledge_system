import os
import shutil
import asyncio
from rag_engine import AdvancedRAGEngine as RAGEngine
from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "input_data")
CHROMA_DIR = os.path.join(BACKEND_DIR, "chroma_db")
BM25_DIR = os.path.join(BACKEND_DIR, "bm25_index")
PARENT_DOCS_PATH = os.path.join(BACKEND_DIR, "parent_docs.json")

async def quick_rebuild():
    print("===================================================")
    print("      Quick Rebuild (Single File: ptug+.pdf)")
    print("===================================================")
    
    os.environ["CHROMA_PERSIST_DIR"] = CHROMA_DIR
    
    print(f"\n🧹 Clearing existing index...")
    if os.path.exists(CHROMA_DIR): shutil.rmtree(CHROMA_DIR)
    if os.path.exists(BM25_DIR): shutil.rmtree(BM25_DIR)
    if os.path.exists(PARENT_DOCS_PATH): os.remove(PARENT_DOCS_PATH)

    print(f"\n🚀 Initializing RAG Engine...")
    engine = RAGEngine()
    
    target_file = "ptug+.pdf"
    file_path = os.path.join(INPUT_DIR, target_file)
    
    if not os.path.exists(file_path):
        print(f"❌ Target file not found: {file_path}")
        return

    print(f"\n📥 Ingesting: {target_file}")
    try:
        count = await engine.ingest_document(file_path, target_file)
        print(f"   ✅ Done! {count} chunks ingested.")
    except Exception as e:
        print(f"   ❌ Error ingesting {target_file}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(quick_rebuild())
