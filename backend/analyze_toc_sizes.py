import fitz
import statistics
import os

def analyze_toc_sizes(pdf_path):
    print(f"📊 Analyzing TOC Section Sizes: {os.path.basename(pdf_path)}")
    
    try:
        doc = fitz.open(pdf_path)
        toc = doc.get_toc()
    except Exception as e:
        print(f"❌ Failed to open PDF: {e}")
        return

    section_lengths = []
    level_stats = {1: [], 2: [], 3: [], 4: [], 5: []}
    
    print("\n--- Processing Sections ---")
    
    for i, entry in enumerate(toc):
        level, title, page = entry[0], entry[1], entry[2]
        start_page_idx = page - 1
        
        # Determine End Page
        if i + 1 < len(toc):
            end_page_idx = toc[i+1][2] - 1
        else:
            end_page_idx = len(doc) - 1
            
        if start_page_idx > end_page_idx:
            continue
            
        # Extract Text
        full_text = ""
        # iterate pages
        # range(start, end+1) includes end page?
        # Logic from before: we want up to (but not including?) next start?
        # If next starts at pg 5 (idx 4), end_page_idx is 3. range(0, 4) -> 0,1,2,3. Correct.
        try:
            for p_idx in range(start_page_idx, end_page_idx + 1):
                page_obj = doc.load_page(p_idx)
                full_text += page_obj.get_text()
        except Exception as e:
            print(f"⚠️ Error reading pages {start_page_idx}-{end_page_idx}: {e}")
            continue
            
        char_count = len(full_text)
        section_lengths.append(char_count)
        if level in level_stats:
            level_stats[level].append(char_count)
            
        # Print a few samples (e.g. huge ones or specific ones)
        if "report_constraint" in title:
            print(f"📍 [Target] '{title}' (L{level}): {char_count} chars ({char_count/4000:.1f} tokens est.)")
        elif char_count > 10000:
            print(f"⚠️ [Large] '{title}' (L{level}): {char_count} chars")
            
    if not section_lengths:
        print("❌ No sections found or empty PDF.")
        return

    print("\n--- Summary Statistics ---")
    print(f"Total Sections: {len(section_lengths)}")
    print(f"Min Size: {min(section_lengths)} chars")
    print(f"Max Size: {max(section_lengths)} chars")
    print(f"Avg Size: {statistics.mean(section_lengths):.0f} chars")
    print(f"Median Size: {statistics.median(section_lengths):.0f} chars")
    
    print("\n--- By Level ---")
    for lvl in sorted(level_stats.keys()):
        data = level_stats[lvl]
        if data:
            avg = statistics.mean(data)
            med = statistics.median(data)
            print(f"H{lvl}: Avg={avg:.0f}, Median={med:.0f}, Max={max(data)} (Count: {len(data)})")

if __name__ == "__main__":
    # Use relative path assuming running from backend dir
    pdf_path = "../input_data/ptug+.pdf"
    if not os.path.exists(pdf_path):
        # Try absolute path if relative fails (based on previous context)
        pdf_path = "c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/input_data/ptug+.pdf"
    
    analyze_toc_sizes(pdf_path)
