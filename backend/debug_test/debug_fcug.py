import asyncio
from rag_engine import RAGEngine
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv(override=True)

async def main():
    print("Initializing RAGEngine...")
    engine = RAGEngine()
    
    print("\nChecking documents (optimized)...")
    target_filenames = ["fcug.pdf", "input_data/fcug.pdf", "knowledge_system/input_data/fcug.pdf"]
    
    fcug_doc = None
    ids = []
    
    for fname in target_filenames:
        print(f"   Checking: {fname}")
        results = engine.vectorstore.get(where={"source": fname})
        if results and results['ids']:
            print(f"   [FOUND] Found chunks for: {fname} (Count: {len(results['ids'])})")
            fcug_doc = {'filename': fname}
            ids = results['ids']
            documents = results['documents']
            metadatas = results['metadatas']
            break
            
    if not fcug_doc:
         print("[MISS] 'fcug.pdf' NOT found in index (tried multiple paths)!")
         # Fallback to verify if any chunks exist
         # print("   Sampling 5 random chunks to see source format:")
         # peek = engine.vectorstore.get(limit=5)
         # for m in peek['metadatas']:
         #    print(f"   - {m.get('source')}")
         return
        
    target_chunk_id = "eb0e9641-6c86-4885-86a1-f7d720df430c"
    print(f"\nTracing Target Chunk ID: {target_chunk_id}")
    
    query = "compile_fusion 分哪些步骤"
    
    # 1. Check Hybrid Search candidates
    print(f"\n1.  Running Hybrid Search (Internal) for: '{query}'")
    # Accessing private method for debug (Sync method!)
    candidates = engine._hybrid_search(query, top_k=100)
    
    found_in_candidates = False
    candidate_rank = -1
    for i, doc in enumerate(candidates):
        # ID is in metadata? No, doc.id usually? 
        # Chroma docs don't always have ID in metadata dependent on how it was added.
        # But we saw 'ids' in get() result.
        # Let's check matching content or if ID is available on doc object
        # In this codebase, IDs might not be attached to Document object easily unless added.
        # Let's check metadata['chunk_id'] if it corresponds? 
        # Wait, the ID I found 'd9e...' is Chroma ID. 'chunk_id' in metadata is integer index (e.g. 6657).
        # Let's check metadata `chunk_id` for 6657.
        
        # From Dump: chunk_id is 6657.
        current_chunk_int_id = doc.metadata.get('chunk_id')
        if str(current_chunk_int_id) == "6657":
            found_in_candidates = True
            candidate_rank = i
            print(f"   [MATCH] Found in Hybrid Candidates at Rank {i}!")
            print(f"      Score: {getattr(doc, 'score', 'N/A')}")
            break
            
    if not found_in_candidates:
        print("   [MISS] Target Chunk NOT found in Top 100 Hybrid Search candidates.")
        
    # 2. Check Retrieval (Public API which includes rerank)
    print(f"\n2.  Running Full Retrieval (with Rerank)...")
    retrieved = await engine.query(query)
    
    found_in_final = False
    for i, src in enumerate(retrieved['sources']):
        if str(src['chunk_id']) == "6657":
            found_in_final = True
            print(f"   [MATCH] Found in Final Result at Rank {i}!")
            break
            
    if not found_in_final:
        print("   [MISS] Target Chunk NOT found in Final Results.")

if __name__ == "__main__":
    asyncio.run(main())
