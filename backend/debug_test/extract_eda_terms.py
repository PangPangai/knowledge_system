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

def is_valid_eda_term(term):
    """Filter out garbage terms generated from PDF parsing."""
    if len(term) < MIN_LENGTH:
        return False
        
    parts = term.split('_')
    
    # Rule 1: No excessive underscores
    if len(parts) > 6:
        return False
        
    # Rule 2: Single-letter restrictions
    allowed_single = {'x', 'y', 'z', 'a', 'b', 'c', 'd', '1', '2', '3', '4', '7'}
    for part in parts:
        if len(part) == 1 and part not in allowed_single:
            return False
            
    # Rule 3: Vowel check for longer parts
    vowels = set('aeiouy')
    for part in parts:
        if part.isalpha() and len(part) >= 4:
            if not any(char in vowels for char in part):
                return False
                
    # Rule 4: Suspicious consecutive characters
    for part in parts:
        if part.startswith('ii') or part.startswith('uu'):
            return False
            
    # Rule 5: Pure gibberish patterns manually observed
    gibberish_patterns = [
        r'^tulauddni', r'niitdn', r'^inmi', r'^inuni', r'^eiouni', r'^nxea', r'^todt', r'^ualf', 
        r'^whnon', r'^inmia', r'^inuia'
    ]
    for p in gibberish_patterns:
        if re.search(p, term):
            return False
            
    return True

def extract_candidates(text):
    """Extract potential EDA terms using regex"""
    # Pattern 1: snake_case words (most EDA commands)
    snake_case_pattern = r'\b[a-zA-Z]+(?:_[a-zA-Z0-9]+)+\b'
    
    # Find all matches
    matches = re.findall(snake_case_pattern, text)
    
    candidates = []
    for m in matches:
        term = m.lower()
        if is_valid_eda_term(term):
            candidates.append(term)
            
    return candidates

def cleanup_existing_dict():
    """Clean up the existing eda_terms.txt file using the new validation rules."""
    dict_path = os.path.join(os.path.dirname(__file__), "..", "eda_terms.txt")
    if not os.path.exists(dict_path):
        print(f"⚠️ Existing dictionary not found at {dict_path}")
        return

    print(f"🧹 Cleaning up existing dictionary at {dict_path}...")
    
    with open(dict_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    valid_lines = []
    removed_count = 0
    
    for line in lines:
        if line.startswith('#'):
            valid_lines.append(line)
            continue
            
        parts = line.strip().split()
        if not parts:
            continue
            
        term = parts[0]
        if is_valid_eda_term(term):
            valid_lines.append(line)
        else:
            removed_count += 1
            
    if removed_count > 0:
        with open(dict_path, 'w', encoding='utf-8') as f:
            f.writelines(valid_lines)
        print(f"   ✅ Cleaned up {removed_count} garbage terms from existing dictionary.")
    else:
        print("   ✅ Existing dictionary is already clean.")

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
    
    # Also clean the existing dictionary
    cleanup_existing_dict()

if __name__ == "__main__":
    main()
