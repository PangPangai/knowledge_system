"""
RAG Index Rebuilder - API Mode
Rebuilds the knowledge base by uploading all PDFs from input_data/
via the running backend API (same path as admin_cli upload).

Requirements:
    - Backend service must be running before executing this script.
    - All PDFs to index must be placed in the input_data/ directory.
"""

import os
import re
import sys
import time
import shutil
import requests
from typing import Tuple
from dotenv import load_dotenv
import fitz

# Load environment variables
load_dotenv()

# Paths
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "input_data")

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


class PDFScanner:
    """Utility to detect garbled PDF extraction (Identity-H issues)."""

    @staticmethod
    def is_garbled(pdf_path: str) -> Tuple[bool, str]:
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            sample_indices = [0]
            if total_pages > 50:
                sample_indices.append(50)
            if total_pages > 100:
                sample_indices.append(102)

            sample_text = ""
            for idx in sample_indices:
                if idx < total_pages:
                    sample_text += doc[idx].get_text()
            doc.close()

            if not sample_text.strip():
                return False, "Empty or Scanned PDF"

            corruption_patterns = ["Chu<", "<untdilbtm", "u<<", "<uti", "ut<<", "utu ", "tu eim<"]
            if any(p in sample_text for p in corruption_patterns):
                return True, "Identity-H Font Mapping Failure"

            clean_chars = len(re.findall(r'[a-zA-Z0-9\s\.,;:!?\(\)\-\*/%#_\[\]\{\}]', sample_text))
            total_chars = len(sample_text)
            clean_ratio = clean_chars / max(1, total_chars)

            if clean_ratio < 0.7:
                return True, f"Low text density ({clean_ratio:.2f}) - likely garbled"

            return False, f"Clean (Density: {clean_ratio:.2f})"
        except Exception as e:
            return False, f"Scan Error: {e}"


def check_health(api_base: str) -> bool:
    """Verify backend service is up and ready."""
    try:
        r = requests.get(f"{api_base}/health", timeout=10)
        return r.status_code == 200
    except Exception:
        return False





def upload_file(api_base: str, file_path: str, poll_interval: int = 3) -> dict:
    """
    Upload a single file via async upload API and poll until complete.

    Returns:
        dict with filename, chunks_created, processing_duration
    """
    file_ext = os.path.splitext(file_path)[1].lower()
    content_type = "application/pdf" if file_ext == ".pdf" else "text/markdown"

    with open(file_path, "rb") as f:
        response = requests.post(
            f"{api_base}/upload",
            files={"file": (os.path.basename(file_path), f, content_type)},
            timeout=300,
        )

    if response.status_code != 200:
        raise Exception(f"Upload failed ({response.status_code}): {response.text}")

    task_id = response.json()["task_id"]

    # Poll until completed or failed, printing new log lines incrementally
    last_log_count = 0
    last_was_transient = False
    transient_icons = ["⏳", "⚙️", "🔢"]

    while True:
        sr = requests.get(f"{api_base}/tasks/{task_id}", timeout=30)
        if sr.status_code != 200:
            raise Exception(f"Failed to get task status: {sr.text}")
        status = sr.json()
        state = status["status"]

        # Print any new log lines since last poll
        logs = status.get("logs", [])
        for line in logs[last_log_count:]:
            line = line.strip()
            if not line:
                continue
            
            # Check if this line is a "transient" progress update
            is_transient = any(line.startswith(icon) for icon in transient_icons)
            
            if is_transient and last_was_transient:
                # Move up 1 line and clear it
                print("\033[F\033[K", end="")
                print(f"   {line}")
            else:
                print(f"   {line}")
            
            last_was_transient = is_transient

        last_log_count = len(logs)

        if state == "completed":
            return {
                "filename": status["filename"],
                "chunks_created": status["chunks_created"],
                "processing_duration": status.get("processing_duration"),
            }
        elif state == "failed":
            raise Exception(f"Processing failed: {status.get('error', 'unknown')}")

        if last_log_count == 0:
            print(f"   ⏳ {state}...", end="\r")
        time.sleep(poll_interval)


def rebuild():
    print("===================================================")
    print("      RAG Index Rebuilder (API Mode)")
    print("===================================================")
    print(f"   Backend: {API_BASE_URL}")
    print(f"   Input:   {INPUT_DIR}")

    # Step 1: Check backend is running
    # Note: chroma_db is already cleared by rebuild.bat before backend started
    print("\n🔍 Checking backend health...")
    if not check_health(API_BASE_URL):
        print(f"❌ Backend not reachable at {API_BASE_URL}")
        print("   Please run rebuild.bat which handles starting the backend automatically.")
        sys.exit(1)
    print("   ✅ Backend is ready")

    # Step 2: Collect PDF files
    if not os.path.exists(INPUT_DIR):
        print(f"❌ Input directory not found: {INPUT_DIR}")
        sys.exit(1)

    pdf_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".pdf")]
    files = sorted(pdf_files, key=lambda f: os.path.getsize(os.path.join(INPUT_DIR, f)))
    print(f"\n📂 Found {len(files)} PDFs in {INPUT_DIR} (sorted by size, ascending)")

    # Step 4: Pre-scan all PDFs
    print(f"\n🔍 [Phase 1/2] Scanning PDFs for quality issues...")
    bad_files = set()
    for filename in files:
        file_path = os.path.join(INPUT_DIR, filename)
        is_bad, reason = PDFScanner.is_garbled(file_path)
        if is_bad:
            bad_files.add(filename)
            print(f"   ❌ {filename:<60} | {reason}")
        else:
            print(f"   ✅ {filename:<60} | {reason}")

    clean_files = [f for f in files if f not in bad_files]
    print(f"\n📊 Scan Results: {len(clean_files)} Clean, {len(bad_files)} Garbled (skipped)")

    # Step 5: Upload clean files via API
    print(f"\n🚀 [Phase 2/2] Uploading {len(clean_files)} clean document(s) via API...")

    success_count = 0
    fail_count = 0

    for i, filename in enumerate(clean_files):
        file_path = os.path.join(INPUT_DIR, filename)
        print(f"\n[{i+1}/{len(clean_files)}] Uploading: {filename}")
        try:
            t0 = time.time()
            result = upload_file(API_BASE_URL, file_path)
            elapsed = time.time() - t0
            chunks = result.get("chunks_created", "?")
            print(f"   ✅ Done! {chunks} chunks in {elapsed:.1f}s")
            success_count += 1
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            fail_count += 1

    print(f"\n===================================================")
    print(f"✅ Rebuild Complete!")
    print(f"   Success: {success_count}  |  Failed: {fail_count}")
    print(f"===================================================")


if __name__ == "__main__":
    rebuild()
