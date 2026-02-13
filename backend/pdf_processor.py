import fitz  # PyMuPDF
import pymupdf4llm
import re
import os
import urllib.parse
import statistics
from typing import List, Dict, Tuple, Set
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

class PDFProcessor:
    def __init__(self):
        self.cleaning_rules = {
            "default": [r"\[Feedback\]\(mailto:[^)]+\)"]
        }

    def process_pdf(self, pdf_path: str) -> Tuple[List[Document], Dict[str, str]]:
        """
        Process PDF using TOC-based slicing with strict boundary enforcement.
        
        Args:
            pdf_path: Absolute path to the PDF file
            
        Returns:
            Tuple containing:
            - List[Document]: Child chunks for vector indexing
            - Dict[str, str]: Parent map {parent_id: full_section_text} for persistence
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
            
        doc = fitz.open(pdf_path)
        toc = doc.get_toc()  # [[lvl, title, page_num], ...]
        filename = os.path.basename(pdf_path)
        
        # Auto-detect noise patterns (header/footer)
        noise_patterns = self._auto_detect_noise(doc)
        print(f"   🔍 Auto-detected {len(noise_patterns)} noise patterns for {filename}")
        
        # ---------------------------------------------------------
        # BATCH CONVERSION OPTIMIZATION
        # ---------------------------------------------------------
        # Instead of calling to_markdown() for every section (which is slow),
        # we convert in chunks of 500 pages to show progress.
        total_pages = len(doc)
        print(f"   🚀 Starting batch Markdown conversion for {total_pages} pages...")
        print(f"   ℹ️  This may take 2-5 minutes for large docs. Converting in chunks...")
        
        import time
        t_start = time.time()
        
        all_pages_md = []
        batch_size = 200 # Process 200 pages at a time for feedback
        
        try:
            for start_idx in range(0, total_pages, batch_size):
                end_idx = min(start_idx + batch_size, total_pages)
                current_batch_pages = list(range(start_idx, end_idx))
                
                print(f"      ⏳ Converting pages {start_idx}-{end_idx} / {total_pages}...", end="\r")
                
                # Convert this batch
                batch_data = pymupdf4llm.to_markdown(doc, pages=current_batch_pages, page_chunks=True, write_images=False)
                
                # Append text to master list
                if batch_data:
                    all_pages_md.extend([urllib.parse.unquote(p["text"]) for p in batch_data])
                else:
                    # Handle empty/error pages gracefully
                    all_pages_md.extend([""] * len(current_batch_pages))
            
            print() # Newline after progress bar
            t_end = time.time()
            print(f"   ✅ Batch conversion complete in {t_end - t_start:.2f}s (Avg {(t_end - t_start)/total_pages:.2f}s/page)")
            
            # --- DEBUG: Dump latest converted markdown ---
            try:
                debug_md_path = "latest_converted.md"
                with open(debug_md_path, "w", encoding="utf-8") as f:
                    f.write("\n\n".join(all_pages_md))
                print(f"   📝 Debug: Full markdown dumped to '{debug_md_path}'")
            except Exception as e:
                print(f"   ⚠️ Failed to dump debug markdown: {e}")
            # ---------------------------------------------
            
        except Exception as e:
            print(f"\n   ❌ Batch conversion failed at index {len(all_pages_md)}: {e}. Falling back to per-section extraction.")
            all_pages_md = None

        chunks: List[Document] = []
        parent_map: Dict[str, str] = {}
        
        # Track hierarchy for context injection
        # hierarchy[level] = title
        hierarchy = {}
        
        for i, entry in enumerate(toc):

            level, title, page = entry[0], entry[1], entry[2]
            start_page_idx = page - 1
            
            # Update hierarchy
            hierarchy[level] = title
            # Clear deeper levels
            keys_to_remove = [k for k in hierarchy if k > level]
            for k in keys_to_remove:
                del hierarchy[k]
                
            # Build context string
            # [Source: filename] > H1 > H2 ...
            context_path = f"[Source: {filename}]"
            sorted_levels = sorted(hierarchy.keys())
            for lvl in sorted_levels:
                context_path += f" > {hierarchy[lvl]}"
            
            # Determine end page
            if i + 1 < len(toc):
                end_page_idx = toc[i+1][2] - 1
            else:
                end_page_idx = len(doc) - 1
                
            # Handle edge case where section is empty (start > end)
            if start_page_idx > end_page_idx:
                continue
                
            # Extract raw markdown for this section range
            # page_indices = list(range(start_page_idx, end_page_idx + 1))
            # print(f"      [DEBUG] Processing Section '{title}' (Pages {start_page_idx}-{end_page_idx}, Total: {len(page_indices)})")
            
            try:
                # OPTIMIZED: Get from cache if available
                if all_pages_md:
                    # Validate indices
                    safe_start = max(0, start_page_idx)
                    safe_end = min(len(all_pages_md) - 1, end_page_idx)
                    
                    if safe_start > safe_end:
                         raw_md = ""
                    else:
                         selected_pages = all_pages_md[safe_start : safe_end + 1]
                         raw_md = "\n\n".join(selected_pages)
                else:
                    # Fallback (Slow)
                    page_indices = list(range(start_page_idx, end_page_idx + 1))
                    raw_md = urllib.parse.unquote(pymupdf4llm.to_markdown(doc, pages=page_indices, write_images=False))

            except Exception as e:
                print(f"   ⚠️ Error converting pages {start_page_idx}-{end_page_idx}: {e}")
                continue
            
            # ---------------------------------------------------------
            # STRICT TRUNCATION LOGIC
            # ---------------------------------------------------------
            if i + 1 < len(toc):
                next_title = toc[i+1][1]
                # Robustly find the next title in MD format
                # We look for: \n + (#+) + space + title + space* + \n
                
                # Escape title for regex, but allow whitespace diffs
                # Replace space with \s+ to be flexible
                escaped_title = re.escape(next_title).replace(r'\ ', r'\s+')
                
                # Pattern: 
                # \n        : Start of line (implied)
                # #{1,6}    : Markdown header markers
                # \s+       : Space
                # next_title: The title text
                # \s*       : Optional trailing space
                # (?:\n|$)  : End of line or string
                pattern = re.compile(r'\n#{1,6}\s+' + escaped_title + r'\s*(?:\n|$)', re.IGNORECASE)
                
                match = pattern.search(raw_md)
                if match:
                    # Found the next header! Truncate everything from match start.
                    truncate_pos = match.start()
                    raw_md = raw_md[:truncate_pos].strip()
                else:
                    pass 
            
            # ---------------------------------------------------------
            # NOISE CLEANING
            # ---------------------------------------------------------
            cleaned_text = self._apply_cleaning(raw_md, noise_patterns)
            
            if not cleaned_text.strip():
                continue

            # ---------------------------------------------------------
            # PARENT ID & STORAGE
            # ---------------------------------------------------------
            # Generate unique stable parent_id
            safe_title = re.sub(r'[^a-zA-Z0-9]', '_', title)[:50]
            parent_id = f"{filename}_sec_{i:03d}_{safe_title}"
            
            # Store full Cleaned Parent Text
            parent_map[parent_id] = cleaned_text
            
            # ---------------------------------------------------------
            # CHUNKING (Child Chunks)
            # ---------------------------------------------------------
            MAX_CHUNK_SIZE = 1000
            
            if len(cleaned_text) <= MAX_CHUNK_SIZE * 1.5:
                # Small enough to be one chunk
                chunk_docs = [Document(
                    page_content=f"{context_path}\n\n{cleaned_text}",
                    metadata={
                        "source": filename,
                        "parent_id": parent_id,
                        "section": title,
                        "context": context_path,
                        "chunk_id": f"{parent_id}_0",
                        "source_role": "primary"
                    }
                )]
            else:
                # Use RecursiveCharacterTextSplitter for robust breaking
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=MAX_CHUNK_SIZE,
                    chunk_overlap=100,
                    separators=["\n\n", "\n", " ", ""]
                )
                
                # Split the CLEANED text
                split_texts = text_splitter.split_text(cleaned_text)
                
                chunk_docs = []
                for idx, chunk_text in enumerate(split_texts):
                    # Re-inject context header for each chunk
                    chunk_content = f"{context_path}\n\n{chunk_text}"
                    
                    chunk_docs.append(Document(
                        page_content=chunk_content,
                        metadata={
                            "source": filename,
                            "parent_id": parent_id,
                            "section": title,
                            "context": context_path,
                            "chunk_id": f"{parent_id}_{idx}",
                            "source_role": "primary"
                        }
                    ))
            
            chunks.extend(chunk_docs)
            
        doc.close()
        return chunks, parent_map

    def _auto_detect_noise(self, doc: fitz.Document) -> List[str]:
        """
        Analyze start/end pages to find repetitive header/footer patterns.
        Strategy:
        1. Sample first 3 and last 3 pages.
        2. Split into lines.
        3. Count frequency of exact line matches.
        4. Lines appearing in >50% of sampled pages are noise.
        """
        sample_pages = []
        page_count = len(doc)
        
        # Select sample indices
        indices = list(range(min(3, page_count)))
        if page_count > 3:
            indices.extend(range(max(3, page_count - 3), page_count))
        
        indices = sorted(list(set(indices))) # Dedup
        if not indices: return []

        line_counts = {}
        for idx in indices:
            try:
                page_text = doc[idx].get_text()
            except:
                continue
            lines = [l.strip() for l in page_text.split('\n') if l.strip()]
            
            # Use set to count only once per page (avoid counting repeated lines within a page)
            unique_lines = set(lines)
            
            for line in unique_lines:
                if len(line) < 4: continue # Skip very short noise
                if len(line) > 100: continue # Skip actual content paragraphs
                
                line_counts[line] = line_counts.get(line, 0) + 1
        
        noise_patterns = []
        threshold = len(indices) * 0.5 # Appear in more than 50% of sampled pages
        
        for line, count in line_counts.items():
            if count > threshold:
                # Escape for regex and add to patterns
                # Handle potential special chars in headers
                escaped = re.escape(line)
                # Match strict full line behavior to avoid partial replacement of valid text
                # We can replace the line entirely.
                noise_patterns.append(escaped)
                
        return noise_patterns

    def _apply_cleaning(self, text: str, patterns: List[str]) -> str:
        """
        Apply regex rules to clean text.
        """
        # Basic feedback removal as per plan
        text = re.sub(r'\[Feedback\]\(mailto:[^)]+\)', '', text)
        
        # Apply detected patterns
        for pat in patterns:
            # We assume these patterns are full lines or significant parts of lines
            # Replace with empty string
            text = re.sub(pat, '', text)
            
        return text
