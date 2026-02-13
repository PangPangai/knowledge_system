
import os
import sys
from rag_engine import AdvancedRAGEngine
from langchain_core.documents import Document

from rag_engine import AdvancedRAGEngine
from langchain_core.documents import Document
from unittest.mock import MagicMock

def test_parent_matching():
    # Mocking init to avoid loading heavy models/API keys
    original_init = AdvancedRAGEngine.__init__
    def mock_init(self):
        self.chunk_size = 500
        self.chunk_overlap = 100
        self.parent_docs = {}
        # Initialize splitters as they are needed for chunking
        from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap
        )
        self.md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")]
        )
        self.rerank_enabled = False
        
    AdvancedRAGEngine.__init__ = mock_init

    print("🚀 Initializing Engine for Chunker Test (Mocked)...")
    engine = AdvancedRAGEngine()
    
    # Sample text that mimics a large document section
    sample_text = """# Section 1: Introduction to Congestion

Congestion is a major issue in physical design. It occurs when the number of required routing tracks exceeds the available tracks.

## 1.1 Causes of Congestion

There are many causes including high cell density, bad placement, and limited routing resources.

(Here is some filler text to simulate distance...)
""" + ("Filler text line.\n" * 50) + """

## 1.2 Fixing Congestion

To fix congestion, you can use cell padding, congestion-aware placement, and blockage.
Specific commands include `refine_placement` and `route_opt`.

**IR Drop Analysis** is also related. Sometimes we spread cells for IR drop which helps congestion.
"""

    print("\n📦 Chunking Sample Text...")
    result_chunks = engine._chunk_markdown(sample_text, "test_file.md")
    
    print(f"   Created {len(result_chunks)} child chunks.")
    
    # Simulate Retrieval of a specific "deep" chunk
    # e.g. the one about "Fixing Congestion" which is at the end
    
    target_child = None
    for chunk in result_chunks:
        if "refine_placement" in chunk["content"]:
            target_child = chunk
            print("\n🎯 Found Target Child Chunk (deep in text):")
            print(f"   Content Snippet: {chunk['content'][:50]}...")
            print(f"   Parent ID: {chunk['parent_id']}")
            break
            
    if not target_child:
        print("❌ Could not find target chunk in test data!")
        return

    # Simulate _expand_to_parent logic
    print("\n🔍 Testing _expand_to_parent Logic...")
    
    # Construct Document object as retrieval would
    doc_obj = Document(
        page_content=target_child["content"],
        metadata={
            "source": "test_file.md",
            "parent_id": target_child["parent_id"]
        }
    )
    
    # Manually populate parent_docs for match
    # (Already done by _chunk_markdown in memory, but let's verify)
    parent_id = target_child["parent_id"]
    if parent_id in engine.parent_docs["test_file.md"]:
        print("   ✅ Parent content exists in memory.")
    else:
        print("   ❌ Parent content MISSING in memory!")
        return

    # Run expansion
    expanded_docs = engine._expand_to_parent([doc_obj])
    
    if expanded_docs:
        expanded_doc = expanded_docs[0]
        ex_content = expanded_doc.page_content
        
        print(f"\n📄 Expanded Content (Windowed):")
        print("-" * 40)
        print(ex_content)
        print("-" * 40)
        
        # VERIFICATION: Does the expanded content actually contain the child content?
        if target_child["content"] in ex_content:
            print("\n✅ SUCCESS: Child content found in Expanded Parent Window.")
        else:
            print("\n❌ FAILURE: Child content NOT found in Expanded Parent Window!")
            print("   (This means the Sliding Window logic failed to locate the child strings inside the parent string)")
            
            # Debugging why
            full_parent = engine.parent_docs["test_file.md"][parent_id]
            print(f"\n   Debug Detail:")
            print(f"   Child len: {len(target_child['content'])}")
            print(f"   Parent search result: {full_parent.find(target_child['content'])}")
            if full_parent.find(target_child['content']) == -1:
                print("   ⚠️  String exact match failed. Whitespace variation likely.")
                
    else:
        print("❌ Expansion returned no documents.")

if __name__ == "__main__":
    test_parent_matching()
