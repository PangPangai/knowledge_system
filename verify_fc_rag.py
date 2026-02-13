import sys
import os
import asyncio

# Fix for Windows asyncio loop policy if needed
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Force UTF-8 stdout
    sys.stdout.reconfigure(encoding='utf-8')

# Add backend to path
current_dir = os.getcwd()
backend_dir = os.path.join(current_dir, "backend")
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

print(f"Working dir: {current_dir}")
print(f"Backend dir: {backend_dir}")

try:
    from rag_engine import AdvancedRAGEngine
except ImportError as e:
    print(f"Import failed: {e}")
    # Try alternate path if running from root vs backend
    sys.path.append(current_dir)
    from backend.rag_engine import AdvancedRAGEngine

async def verify():
    print("Initializing RAG Engine (this may take a moment)...")
    try:
        engine = AdvancedRAGEngine()
    except Exception as e:
        print(f"Failed to initialize engine: {e}")
        return

    question = "FC中关于constant propagation和case propagation有哪些设置，区别是什么"
    print(f"\n❓ Testing Question: {question}\n")
    
    print("Expected Behavior:")
    print("1. Sources should be primarily FC (Fusion Compiler).")
    print("2. PT (PrimeTime) sources should be limited (max 1) and tagged as supplementary.")
    print("3. Answer should focus on FC, or clearly distinguish PT info.\n")
    
    print("-" * 50)
    print("Running Query Stream...")
    
    full_answer = ""
    sources = []
    
    try:
        async for chunk in engine.query_stream(question):
            if chunk["type"] == "metadata":
                sources = chunk["sources"]
                print(f"\n📚 Retrieved {len(sources)} sources:")
                for i, src in enumerate(sources):
                    print(f"   [{i+1}] {src['source']} (Chunk {src['chunk_id']})")

            elif chunk["type"] == "content":
                print(chunk["content"], end="", flush=True)
                full_answer += chunk["content"]
            
            elif chunk["type"] == "error":
                print(f"\n❌ Error in stream: {chunk['content']}")
    except Exception as e:
        print(f"\n❌ Exception during query: {e}")
        import traceback
        traceback.print_exc()

            
    print("\n\n" + "-" * 50)
    print("Verification Results:")
    
    # Analyze Sources
    fc_count = sum(1 for s in sources if 'fc' in s['source'].lower() or 'fusion' in s['source'].lower())
    pt_count = sum(1 for s in sources if 'pt' in s['source'].lower() or 'prime' in s['source'].lower())
    
    print(f"\nDOCS DISTRIBUTION: FC={fc_count}, PT={pt_count}")
    
    if pt_count <= 1:
        print("✅ PASS: PT documents limited to 1 or 0.")
    else:
        print(f"❌ FAIL: Too many PT documents ({pt_count})!")

    # Analyze Answer Content
    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(verify())
