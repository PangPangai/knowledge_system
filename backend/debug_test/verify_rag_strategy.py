import asyncio
import os
import sys
from rag_engine import AdvancedRAGEngine
from dotenv import load_dotenv

load_dotenv()

# Add project root to sys.path if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Ensure persistence matches rebuild script
start_dir = os.getcwd()
if os.path.basename(start_dir) == "backend":
    os.environ["CHROMA_PERSIST_DIR"] = os.path.join(start_dir, "chroma_db")

async def verify_strategy():
    print("===================================================")
    print("      Verification: Strict Slicing & Parent Expansion")
    print("===================================================")
    
    # 1. Initialize Engine (Use existing DB)
    engine = AdvancedRAGEngine()
    
    if not engine.is_ready():
        print("❌ Engine not ready. Please rebuild index first.")
        return

    # 2. Test Query
    query = "guide" 
    # Use a query likely to appear in PT/FC docs (e.g. "User Guide")
    print(f"\n🔍 Querying: '{query}'")
    
    # 3. Retrieve Children (Vector + BM25 + Rerank)
    # We access internal methods to inspect intermediate steps
    retrieved_docs = engine._hybrid_search(query, top_k=5)
    
    print(f"\n--- 1. Child Chunk Inspection ({len(retrieved_docs)} docs) ---")
    for i, doc in enumerate(retrieved_docs):
        parent_id = doc.metadata.get("parent_id", "MISSING")
        context = doc.metadata.get("context", "MISSING")
        source = doc.metadata.get("source", "UNKNOWN")
        
        print(f"\n[Child {i+1}] Source: {source}")
        print(f"   Ref Parent ID: {parent_id}")
        print(f"   Context Path : {context}")
        print(f"   Content Start: {doc.page_content[:100].replace(chr(10), ' ')}...")
        
        if parent_id == "MISSING":
             print("   ❌ FAILED: Missing parent_id!")
        else:
             print("   ✅ Valid parent reference")

    # 4. Test Parent Expansion
    print(f"\n--- 2. Parent Expansion Test ---")
    expanded_docs = engine._expand_to_parent(retrieved_docs)
    
    print(f"   Input Children: {len(retrieved_docs)}")
    print(f"   Output Parents: {len(expanded_docs)}")
    
    if len(expanded_docs) == 0:
        print("   ⚠️ No parents expanded. Check parent_docs persistence.")
    
    seen_ids = set()
    for i, doc in enumerate(expanded_docs):
        pid = doc.metadata.get("parent_id")
        is_windowed = doc.metadata.get("is_windowed", False)
        length = len(doc.page_content)
        
        if pid in seen_ids:
            print(f"   ❌ DUPLICATE DETECTED: {pid}")
        seen_ids.add(pid)
        
        print(f"\n[Parent {i+1}] ID: {pid}")
        print(f"   Size: {length} chars")
        print(f"   Windowed: {is_windowed}")
        print(f"   Preview: {doc.page_content[:100].replace(chr(10), ' ')}...")
        
    print("\n✅ Verification Complete")

if __name__ == "__main__":
    asyncio.run(verify_strategy())
