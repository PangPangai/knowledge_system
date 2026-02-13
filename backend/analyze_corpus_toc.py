import fitz
import statistics
import os
import glob
from pathlib import Path
import tiktoken

def get_token_count(text, encoding_name="cl100k_base"):
    try:
        encoding = tiktoken.get_encoding(encoding_name)
    except:
        # Fallback if tiktoken fails
        return len(text) // 4
    num_tokens = len(encoding.encode(text))
    return num_tokens

def analyze_pdf_toc(pdf_path):
    filename = os.path.basename(pdf_path)
    try:
        doc = fitz.open(pdf_path)
        toc = doc.get_toc()
    except Exception:
        return None

    if not toc:
        return None

    level_stats = {} 
    
    for i, entry in enumerate(toc):
        level, title, page = entry[0], entry[1], entry[2]
        start_page_idx = page - 1
        
        if i + 1 < len(toc):
            end_page_idx = toc[i+1][2] - 1
        else:
            end_page_idx = len(doc) - 1
            
        if start_page_idx > end_page_idx:
            continue
            
        full_text = ""
        try:
            if end_page_idx - start_page_idx > 50:
                 end_page_idx = start_page_idx + 50
                 
            for p_idx in range(start_page_idx, end_page_idx + 1):
                page_obj = doc.load_page(p_idx)
                full_text += page_obj.get_text()
        except Exception:
            continue
            
        char_count = len(full_text)
        token_count = get_token_count(full_text)
        
        if level not in level_stats:
            level_stats[level] = {"chars": [], "tokens": []}
        
        level_stats[level]["chars"].append(char_count)
        level_stats[level]["tokens"].append(token_count)
        
    return level_sizes_to_summary(level_stats, filename)

def level_sizes_to_summary(level_stats, filename):
    summary = {}
    for lvl, data in level_stats.items():
        if not data["chars"]:
            continue
            
        summary[lvl] = {
            "count": len(data["chars"]),
            "avg_chars": statistics.mean(data["chars"]),
            "max_chars": max(data["chars"]),
            "avg_tokens": statistics.mean(data["tokens"]),
            "max_tokens": max(data["tokens"])
        }
    return {"filename": filename, "stats": summary}

def analyze_corpus(directory_path, output_file="corpus_toc_stats.md"):
    print(f"Analyzing Corpus in: {directory_path}")
    
    pdf_files = glob.glob(os.path.join(directory_path, "*.pdf"))
    if not pdf_files:
        print("No PDF files found")
        return

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Corpus TOC Statistics\n\n")
        f.write("| Data Source | Level | Count | Avg Chars | Max Chars | Avg Tokens | Max Tokens |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n")

        for pdf_path in pdf_files:
            filename = os.path.basename(pdf_path)
            print(f"Processing: {filename}")
            report = analyze_pdf_toc(pdf_path)
            
            if report and report["stats"]:
                stats = report["stats"]
                for lvl in sorted(stats.keys()):
                    s = stats[lvl]
                    line = f"| {filename} | H{lvl} | {s['count']} | {s['avg_chars']:.0f} | {s['max_chars']} | **{s['avg_tokens']:.0f}** | **{s['max_tokens']}** |\n"
                    f.write(line)
            else:
                f.write(f"| {filename} | - | 0 | - | - | - | - |\n")
    
    print(f"Report written to {output_file}")

if __name__ == "__main__":
    target_dir = r"c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/input_data"
    analyze_corpus(target_dir)
