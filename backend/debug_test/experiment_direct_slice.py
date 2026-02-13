import fitz
import pymupdf4llm
import sys
import os

def extract_section_with_source_context(pdf_path, target_title="report_constraint"):
    filename = os.path.basename(pdf_path)
    print(f"Opening PDF: {filename}")
    
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()
    
    target_idx = -1
    hierarchy_stack = []
    
    # 1. Find target and build hierarchy context
    # Simplified stack logic for demo (just current H1 > H2 > target)
    # Real implementation needs full stack tracking during iteration
    
    for i, entry in enumerate(toc):
        lvl, title, page = entry[0], entry[1], entry[2]
        
        # Very simple hierarchy tracking for demo purposes
        if lvl == 1: hierarchy_stack = [title]
        elif lvl == 2: hierarchy_stack = hierarchy_stack[:1] + [title]
        elif lvl == 3: hierarchy_stack = hierarchy_stack[:2] + [title]
        elif lvl == 4: hierarchy_stack = hierarchy_stack[:3] + [title]
            
        if target_title in title:
            target_idx = i
            break
            
    if target_idx == -1:
        print(f"Target '{target_title}' not found.")
        return

    # 2. Define Section Range
    start_entry = toc[target_idx]
    start_page = start_entry[2] - 1
    
    if target_idx + 1 < len(toc):
        end_page = toc[target_idx + 1][2] - 1
    else:
        end_page = len(doc) - 1
        
    # 3. Build Full Context Header
    # Context: [Source: ptug+.pdf] > Chapter 4... > report_constraint
    context_str = f"**[Source: {filename}]** > **{' > '.join(hierarchy_stack)}**"
    
    print(f"--- Section Header Constructed ---")
    print(context_str)
    
    # 4. Convert & Inject
    pages = list(range(start_page, end_page + 1)) # Inclusive? No, range is end-exclusive? wait, list(range(s, e+1)) is inclusive.
    # Logic check: if next section starts on page N, this section ends on N-1.
    # pymupdf pages are indices.
    # e.g. Start Pg 117 (idx 116). Next starts Pg 119 (idx 118).
    # Range should be [116, 117].
    # range(116, 118) -> [116, 117]. Correct.
    
    # If end_page is actual page index of next section start:
    real_end_idx = end_page 
    # Use range(start_page, real_end_idx) to exclude next section start page
    # But wait, logic above: `end_page = toc[target_idx+1][2] - 1`. 
    # If next starts at pg 119 (idx 118), end_page = 117 (idx).
    # We want indices [116, 117].
    # range(116, 117 + 1) -> [116, 117]. Correct.

    md_text = pymupdf4llm.to_markdown(pdf_path, pages=list(range(start_page, end_page + 1)))
    
    final_chunk = f"{context_str}\n\n{md_text}"
    
    print("\n--- Final Chunk Preview (What LLM Sees) ---")
    print(final_chunk[:600] + "...")

if __name__ == "__main__":
    extract_section_with_source_context("c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/input_data/ptug+.pdf")
