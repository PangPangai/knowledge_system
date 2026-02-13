import os
import re
import jieba
from collections import Counter
import fitz  # PyMuPDF
from pathlib import Path

# Configuration
DATA_DIR = "../input_data"
OUTPUT_FILE = "eda_terms_candidates.txt"
MIN_FREQUENCY = 5
MIN_LENGTH = 4

def extract_text_from_pdf(filepath):
    """Extract text from PDF using PyMuPDF"""
    try:
        doc = fitz.open(filepath)
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return ""

def extract_text_from_md(filepath):
    """Extract text from Markdown file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return ""

def scan_documents(data_dir):
    """Scan all documents and extract text"""
    all_text = ""
    files = []
    
    # Walk through directory
    for root, dirs, filenames in os.walk(data_dir):
        for filename in filenames:
            ext = Path(filename).suffix.lower()
            filepath = os.path.join(root, filename)
            
            if ext == '.pdf':
                print(f"Reading PDF: {filename}...")
                all_text += extract_text_from_pdf(filepath) + "\n"
                files.append(filename)
            elif ext in ['.md', '.markdown', '.txt']:
                print(f"Reading Text: {filename}...")
                all_text += extract_text_from_md(filepath) + "\n"
                files.append(filename)
                
    return all_text, files

def extract_candidates(text):
    """Extract potential EDA terms using regex"""
    # Pattern 1: snake_case words (most EDA commands)
    # e.g. set_placement_status, check_design
    snake_case_pattern = r'\b[a-zA-Z]+(?:_[a-zA-Z0-9]+)+\b'
    
    # Pattern 2: CamelCase or specific acronyms (optional, but snake_case is key for EDA)
    # e.g. FusionCompiler, PrimeTime (often appearing as normal words, harder to filter)
    
    # Find all matches
    matches = re.findall(snake_case_pattern, text)
    
    # Filter by length
    candidates = [m.lower() for m in matches if len(m) >= MIN_LENGTH]
    
    return candidates

def main():
    print(f"📂 Scanning documents in {DATA_DIR}...")
    full_text, files = scan_documents(DATA_DIR)
    
    if not full_text:
        print("⚠️ No documents found or empty text.")
        return

    print(f"🔍 Extracting terms from {len(files)} files...")
    candidates = extract_candidates(full_text)
    
    # Count frequencies
    counter = Counter(candidates)
    
    # Filter by minimum frequency
    valid_terms = {term: count for term, count in counter.items() if count >= MIN_FREQUENCY}
    
    # Sort by frequency desc
    sorted_terms = sorted(valid_terms.items(), key=lambda x: x[1], reverse=True)
    
    print(f"✅ Found {len(sorted_terms)} valid terms (freq >= {MIN_FREQUENCY})")
    
    # Write to file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"# Auto-generated EDA terms candidates (Min Freq: {MIN_FREQUENCY})\n")
        f.write(f"# Format: term frequency nz\n")
        for term, count in sorted_terms:
            f.write(f"{term} {count} nz\n")
            
    print(f"💾 Candidates saved to {OUTPUT_FILE}")
    print("👉 improved: You can verify this list and append content to 'eda_terms.txt'.")

if __name__ == "__main__":
    main()
