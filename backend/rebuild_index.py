import os
import shutil
import asyncio
from typing import Tuple
from rag_engine import AdvancedRAGEngine as RAGEngine
from dotenv import load_dotenv
import re
import fitz

# Load env variables
load_dotenv()

# Paths
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "input_data")
CHROMA_DIR = os.path.join(BACKEND_DIR, "chroma_db")
BM25_DIR = os.path.join(BACKEND_DIR, "bm25_index")
PARENT_DOCS_PATH = os.path.join(BACKEND_DIR, "parent_docs.json")

class PDFScanner:
    """Utility to detect garbled PDF extraction (Identity-H issues)."""
    @staticmethod
    def is_garbled(pdf_path: str) -> Tuple[bool, str]:
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            # Sample start and middle
            sample_indices = [0]
            if total_pages > 50: sample_indices.append(50)
            if total_pages > 100: sample_indices.append(102) # Specifically check 102 as per finding
            
            sample_text = ""
            for idx in sample_indices:
                if idx < total_pages:
                    sample_text += doc[idx].get_text()
            
            doc.close()
            
            if not sample_text.strip():
                return False, "Empty or Scanned PDF" # Skip scanner logic for empty

            # 1. Look for known corruption patterns
            # Synopsys Identity-H map failure often results in specific character replacement sequences
            corruption_patterns = ["Chu<", "<untdilbtm", "u<<", "<uti", "ut<<", "utu ", "tu eim<"]
            if any(p in sample_text for p in corruption_patterns):
                return True, "Identity-H Font Mapping Failure (Detected specific garage patterns)"

            # 2. ASCII Density check (Heuristic)
            # Typical technical docs should be > 80% alphanumeric/common symbols
            clean_chars = len(re.findall(r'[a-zA-Z0-9\s\.,;:!?\(\)\-\*/%#_\[\]\{\}]', sample_text))
            total_chars = len(sample_text)
            clean_ratio = clean_chars / max(1, total_chars)
            
            if clean_ratio < 0.7:
                return True, f"Low text density ({clean_ratio:.2f}) - likely garbled"
            
            return False, f"Clean (Density: {clean_ratio:.2f})"
        except Exception as e:
            return False, f"Scan Error: {e}"

async def rebuild():
    print("===================================================")
    print("      RAG Index Rebuilder (Strict Slicing w/ Parents)")
    print("===================================================")
    
    # Set persistence directory env var for RAGEngine
    os.environ["CHROMA_PERSIST_DIR"] = CHROMA_DIR
    
    print(f"\n🧹 Clearing existing index...")
    if os.path.exists(CHROMA_DIR):
        try:
            shutil.rmtree(CHROMA_DIR)
            print(f"   - Deleted {CHROMA_DIR}")
        except Exception as e:
            print(f"   ⚠️ Could not delete {CHROMA_DIR}: {e}")
            
    if os.path.exists(BM25_DIR):
        try:
            shutil.rmtree(BM25_DIR)
            print(f"   - Deleted {BM25_DIR}")
        except Exception as e:
            print(f"   ⚠️ Could not delete {BM25_DIR}: {e}")
            
    if os.path.exists(PARENT_DOCS_PATH):
        try:
            os.remove(PARENT_DOCS_PATH)
            print(f"   - Deleted {PARENT_DOCS_PATH}")
        except Exception as e:
            print(f"   ⚠️ Could not delete {PARENT_DOCS_PATH}: {e}")

    print(f"\n🚀 Initializing RAG Engine...")
    # RAGEngine init will create empty DBs
    engine = RAGEngine()
    
    if not os.path.exists(INPUT_DIR):
        print(f"❌ Input directory not found: {INPUT_DIR}")
        return

    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.pdf')]
    print(f"📂 Found {len(files)} PDFs in {INPUT_DIR}")
    
    # --- PHASE 1: PRE-SCAN ALL DOCUMENTS ---
    print(f"\n🔍 [Phase 1/2] Scanning all PDFs for health...")
    status_report = {}
    bad_files = set()
    
    for filename in files:
        file_path = os.path.join(INPUT_DIR, filename)
        is_bad, reason = PDFScanner.is_garbled(file_path)
        status_report[filename] = (is_bad, reason)
        if is_bad:
            bad_files.add(filename)
            print(f"   ❌ {filename:<60} | {reason}")
        else:
            print(f"   ✅ {filename:<60} | {reason}")

    print(f"\n📊 Scan Results: {len(files) - len(bad_files)} Clean, {len(bad_files)} Garbled (to be skipped)")
    
    # --- PHASE 2: INGEST CLEAN DOCUMENTS ---
    print(f"\n🚀 [Phase 2/2] Ingesting clean documents...")
    
    clean_files = [f for f in files if f not in bad_files]
    
    for i, filename in enumerate(clean_files):
        print(f"\n[{i+1}/{len(clean_files)}] Ingesting {filename}...")
        file_path = os.path.join(INPUT_DIR, filename)
            
        try:
            start_time = asyncio.get_event_loop().time()
            count = await engine.ingest_document(file_path, filename)
            elapsed = asyncio.get_event_loop().time() - start_time
            print(f"   ✅ Done! {count} chunks in {elapsed:.2f}s")
        except Exception as e:
            print(f"   ❌ Error ingesting {filename}: {e}")
            import traceback
            traceback.print_exc()
            
    print(f"\n✅ Rebuild Complete!")

if __name__ == "__main__":
    asyncio.run(rebuild())
