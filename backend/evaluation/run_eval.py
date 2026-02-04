"""
RAG Evaluation CLI Script
Run: py -m evaluation.run_eval
"""

import os
import sys
import json
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from .evaluator import RAGEvaluator


async def main():
    """Main evaluation entry point"""
    print("\n" + "="*60)
    print("🔬 RAG Evaluation System")
    print("="*60 + "\n")
    
    # Initialize RAG engine
    print("🚀 Initializing RAG Engine...")
    from rag_engine import AdvancedRAGEngine
    rag_engine = AdvancedRAGEngine()
    
    # Use the same LLM for evaluation (DeepSeek-Chat)
    llm_judge = rag_engine.llm
    print(f"   Judge LLM: {rag_engine.chat_model}")
    
    # Load test dataset
    test_file = Path(__file__).parent / "test_dataset.json"
    print(f"\n📂 Loading test dataset: {test_file}")
    
    with open(test_file, 'r', encoding='utf-8') as f:
        dataset = json.load(f)
    
    test_cases = dataset.get("test_cases", [])
    print(f"   Found {len(test_cases)} test cases")
    
    # Filter by category or difficulty (optional)
    # test_cases = [t for t in test_cases if t.get("difficulty") == "easy"]
    
    # Create evaluator and run
    evaluator = RAGEvaluator(rag_engine, llm_judge)
    
    results = await evaluator.run_evaluation(
        test_cases=test_cases,
        save_results=True
    )
    
    # Print recommendations
    print("\n💡 Recommendations:")
    avg = results.get("average_scores", {})
    
    if avg.get("faithfulness", 1) < 0.7:
        print("   ⚠️ Faithfulness低: 考虑加强Reranker或减少检索数量")
    
    if avg.get("context_relevance", 1) < 0.7:
        print("   ⚠️ Context Relevance低: 检查Embedding模型或分块策略")
    
    if avg.get("answer_relevance", 1) < 0.7:
        print("   ⚠️ Answer Relevance低: 优化System Prompt或增加上下文")
    
    if avg.get("answer_correctness", 1) < 0.7:
        print("   ⚠️ Answer Correctness低: 综合改进检索和生成")
    
    if results.get("overall_score", 0) >= 0.7:
        print("   ✅ 整体评分良好!")
    
    return results


if __name__ == "__main__":
    asyncio.run(main())
