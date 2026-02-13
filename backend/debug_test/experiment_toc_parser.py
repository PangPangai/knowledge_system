import re

def parse_toc(file_path):
    toc_map = {}
    print(f"Reading {file_path} for TOC analysis...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        # Only read the first 1000 lines where TOC resides
        lines = f.readlines()[:1000]
        
    toc_start_idx = -1
    for i, line in enumerate(lines):
        if "### **Contents**" in line:
            toc_start_idx = i
            break
            
    if toc_start_idx == -1:
        print("TOC Start not found!")
        return

    print("Found TOC start. Analyzing indentation...")
    
    # Regex for TOC entry: "   Title . . . . 123"
    # Capture group 1: indent, group 2: title
    toc_pattern = re.compile(r"^(\s*)(.*?) \. \. \. \. (\. )*\d+$")
    
    current_path = []
    
    for line in lines[toc_start_idx+1:]:
        if "###" in line and "Contents" not in line: # End of TOC maybe?
            pass
            
        match = toc_pattern.match(line)
        if match:
            indent = match.group(1)
            raw_title = match.group(2).strip()
            
            # Simple header cleaning
            title = raw_title.replace("**", "").replace("_", "").strip()
            # Remove leading numbers like "4. "
            title = re.sub(r"^\d+\.\s*", "", title)
            
            # Determine level by indent length
            indent_len = len(indent)
            if indent_len == 0: level = 1
            elif indent_len <= 2: level = 2
            elif indent_len <= 4: level = 3
            else: level = 4
            
            print(f"{'  '*(level-1)}[H{level}] {title}")
            
            if "report_constraint" in title:
                print(f"   --> FOUND TARGET: '{title}' is verified as H{level}")
                
if __name__ == "__main__":
    parse_toc("c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/backend/latest_converted.md")
