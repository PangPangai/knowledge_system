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

    def process_pdf(self, pdf_path: str, display_name: str = "") -> Tuple[List[Document], Dict[str, str]]:
        """
        Process PDF using TOC-based slicing with strict boundary enforcement.

        Args:
            pdf_path: Absolute path to the PDF file (may be a temp path)
            display_name: Original filename to use in metadata/context instead of the temp path basename
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc = fitz.open(pdf_path)
        toc = doc.get_toc()  # [[lvl, title, page_num], ...]
        # Use display_name if provided to avoid exposing temp_ prefix in metadata
        filename = display_name if display_name else os.path.basename(pdf_path)
        print(f"   📄 PDF: {filename}  |  TOC sections: {len(toc)}  |  Pages: {len(doc)}")
        
        # 🟢 SMART BBOX DETECTION
        # Automatically detect header/footer boundaries
        top_margin, bottom_margin = self._detect_safe_margins(doc)
        print(f"   📐 Adaptive Margins Calculated: Top={top_margin:.1f}, Bottom={bottom_margin:.1f}")
        
        # Apply physical clipping to all pages BEFORE conversion
        page_rect = doc[0].rect
        safe_rect = fitz.Rect(page_rect.x0, top_margin, page_rect.x1, bottom_margin)
        for page in doc:
            page.set_cropbox(safe_rect)
        print(f"   ✂️  Cropbox applied to {len(doc)} pages  (Top={top_margin:.1f}, Bottom={bottom_margin:.1f})")


        # ---------------------------------------------------------
        # BATCH CONVERSION OPTIMIZATION
        # ---------------------------------------------------------
        total_pages = len(doc)
        print(f"   🚀 Starting batch Markdown conversion (Clipped) for {total_pages} pages...")
        print(f"   ℹ️  This may take 2-5 minutes for large docs. Converting in chunks...")
        
        import time
        t_start = time.time()

        all_pages_md = []
        batch_size = 200  # Process 200 pages at a time for feedback

        try:
            for start_idx in range(0, total_pages, batch_size):
                end_idx = min(start_idx + batch_size, total_pages)
                current_batch_pages = list(range(start_idx, end_idx))

                t_batch = time.time()
                # Convert this batch
                batch_data = pymupdf4llm.to_markdown(doc, pages=current_batch_pages, page_chunks=True, write_images=False)

                # Append text to master list
                if batch_data:
                    all_pages_md.extend([urllib.parse.unquote(p["text"]) for p in batch_data])
                else:
                    # Handle empty/error pages gracefully
                    all_pages_md.extend([""] * len(current_batch_pages))

                elapsed_total = time.time() - t_start
                print(f"   ⏳ Pages {end_idx}/{total_pages} converted  (Elapsed: {elapsed_total:.1f}s)")

            t_end = time.time()
            print(f"   ✅ Batch conversion complete in {t_end - t_start:.2f}s (Avg {(t_end - t_start)/total_pages:.2f}s/page)")
            
            # Dump latest converted markdown for debugging
            try:
                debug_md_path = "latest_converted.md"
                with open(debug_md_path, "w", encoding="utf-8") as f:
                    f.write("\n\n".join(all_pages_md))
                print(f"   📝 Debug: Full markdown dumped to '{debug_md_path}'")
            except Exception as e:
                print(f"   ⚠️ Failed to dump debug markdown: {e}")
            
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
                
            # Section progress: print every 50 sections to avoid log flood
            if i % 50 == 0 or i == len(toc) - 1:
                print(f"   ⚙️  Section [{i+1}/{len(toc)}] {title[:60]}  (p.{page})")

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
            
            def build_char_fuzzy_pattern(t: str) -> str:
                clean_t = re.sub(r'\s+', '', t)
                pattern_parts = []
                # Only allow whitespace and markdown bold/italic markers as padding between characters
                separator = r'[\s*]*'
                for c in clean_t:
                    if c.isalnum():
                        pattern_parts.append(re.escape(c))
                    else:
                        pattern_parts.append(r'(?:' + re.escape(c) + r')?')
                return separator.join(pattern_parts)

            # 1. Truncate BEFORE current title (to remove preamble or previous sections on the same page)
            fuzzy_curr = build_char_fuzzy_pattern(title)
            # Forgiving pattern matching the start near a line break
            curr_pattern = re.compile(r'(?:^|\n)[\s#*_-]*(' + fuzzy_curr + r')[\s*_-]*(?:\n|$)', re.IGNORECASE)
            curr_match = curr_pattern.search(raw_md)
            if curr_match:
                # Truncate everything before this header, and HEAL the broken title using the pristine TOC title
                raw_md = f"# {title}\n\n" + raw_md[curr_match.end():].strip()

            # 2. Truncate AFTER next title (to remove next sections on the same page)
            if i + 1 < len(toc):
                next_title = toc[i+1][1]
                fuzzy_next = build_char_fuzzy_pattern(next_title)
                # Forgiving pattern matching the start of the next title
                next_pattern = re.compile(r'\n[\s#*_-]*(' + fuzzy_next + r')[\s*_-]*(?:\n|$)', re.IGNORECASE)
                
                next_match = next_pattern.search(raw_md)
                if next_match:
                    # Found the next header! Truncate everything from match start.
                    truncate_pos = next_match.start()
                    raw_md = raw_md[:truncate_pos].strip()
            
            # ---------------------------------------------------------
            # NOISE CLEANING
            # ---------------------------------------------------------
            # Bbox clipping already handled headers/footers.
            # We only apply very specific hardcoded rules here if needed.
            cleaned_text = self._apply_cleaning(raw_md)
            
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
            MAX_CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1500))
            CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 200))
            RETENTION_THRESHOLD = int(os.getenv("RETENTION_THRESHOLD", 2500))
            
            if len(cleaned_text) <= RETENTION_THRESHOLD:
                # Small enough to be one chunk (e.g., Error Messages, Attributes)
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
                    chunk_overlap=CHUNK_OVERLAP,
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

    def _detect_safe_margins(self, doc: fitz.Document, num_samples: int = 20) -> Tuple[float, float]:
        """
        Automatically detect safe top and bottom margins by analyzing physical blocks.
        """
        print(f"      [DEBUG] Detecting safe margins using {num_samples} samples...")
        page_count = len(doc)
        if page_count == 0: return 0.0, 0.0
        
        # Sample uniformly
        step = max(1, page_count // num_samples)
        indices = sorted(list(set([0, page_count-1] + [i for i in range(0, page_count, step)][:num_samples])))
        
        page_height = doc[0].rect.height
        top_y1_candidates = []
        bottom_y0_candidates = []
        
        for idx in indices:
            try:
                page = doc[idx]
                blocks = page.get_text("blocks")
                # Filter text blocks (type 0)
                text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]
                
                for b in text_blocks:
                    y0, y1 = b[1], b[3]
                    # Top 12% is considered header zone
                    if y0 < page_height * 0.12:
                        top_y1_candidates.append(y1)
                    # Bottom 12% is considered footer zone
                    elif y1 > page_height * 0.88:
                        bottom_y0_candidates.append(y0)
            except:
                continue
                
        # Calculate cutoffs
        # Safe top: just below the lowest header block found
        final_top = max(top_y1_candidates) + 2 if top_y1_candidates else 0.0
        # Safe bottom: just above the highest footer block found
        final_bottom = min(bottom_y0_candidates) - 2 if bottom_y0_candidates else page_height
        
        return float(final_top), float(final_bottom)

    def _apply_cleaning(self, text: str) -> str:
        """
        Apply remaining specific cleaning rules to the markdown text.
        Bbox clipping handles most header/footer issues.
        """
        # Remove hardcoded feedback links
        text = re.sub(r'\[Feedback\]\(mailto:[^)]+\)', '', text)
        
        # Remove empty lines resulting from clipping or cleaning
        lines = [line for line in text.split('\n')]
        # Optional: remove redundant empty lines at start/end
        return "\n".join(lines).strip()
