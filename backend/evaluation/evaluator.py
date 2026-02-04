"""
RAG Evaluator - Main evaluation orchestrator
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from .metrics import RAGMetrics, EvaluationResult


class RAGEvaluator:
    """
    Main RAG evaluation orchestrator
    Runs test cases through RAG system and evaluates results
    """
    
    def __init__(self, rag_engine, llm_judge):
        """
        Args:
            rag_engine: RAG engine instance to evaluate
            llm_judge: LLM for evaluation (e.g., DeepSeek-Chat)
        """
        self.rag = rag_engine
        self.metrics = RAGMetrics(llm_judge)
        self.results: List[EvaluationResult] = []
    
    async def run_single_test(self, test_case: Dict) -> EvaluationResult:
        """Run evaluation on a single test case"""
        question = test_case["question"]
        ground_truth = test_case.get("ground_truth_answer", "")
        
        print(f"   📝 Testing: {question[:50]}...")
        
        # Get RAG response
        try:
            response = await self.rag.query(question)
            generated_answer = response.get("answer", "")
            sources = response.get("sources", [])
            contexts = [s.get("content", "") for s in sources]
        except Exception as e:
            print(f"   ⚠️ RAG query failed: {e}")
            generated_answer = ""
            contexts = []
        
        # Calculate metrics
        scores = {}
        
        # Faithfulness
        scores["faithfulness"] = await self.metrics.faithfulness(
            generated_answer, contexts
        )
        
        # Answer Relevance
        scores["answer_relevance"] = await self.metrics.answer_relevance(
            question, generated_answer
        )
        
        # Context Relevance
        scores["context_relevance"] = await self.metrics.context_relevance(
            question, contexts
        )
        
        # Answer Correctness (if ground truth available)
        if ground_truth:
            scores["answer_correctness"] = await self.metrics.answer_correctness(
                generated_answer, ground_truth
            )
        
        return EvaluationResult(
            question=question,
            generated_answer=generated_answer,
            ground_truth=ground_truth,
            retrieved_contexts=contexts,
            scores=scores
        )
    
    async def run_evaluation(
        self, 
        test_cases: List[Dict],
        save_results: bool = True,
        output_path: Optional[str] = None
    ) -> Dict:
        """
        Run full evaluation on all test cases
        
        Returns:
            Aggregated evaluation results
        """
        print(f"\n{'='*60}")
        print(f"🔬 RAG Evaluation Started")
        print(f"   Total test cases: {len(test_cases)}")
        print(f"{'='*60}\n")
        
        self.results = []
        
        for i, test_case in enumerate(test_cases):
            print(f"\n[{i+1}/{len(test_cases)}] {test_case.get('id', 'unknown')}")
            result = await self.run_single_test(test_case)
            self.results.append(result)
            
            # Print scores
            for metric, score in result.scores.items():
                status = "✅" if score >= 0.7 else "⚠️" if score >= 0.5 else "❌"
                print(f"   {status} {metric}: {score:.2f}")
        
        # Aggregate results
        summary = self._aggregate_results()
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"📊 Evaluation Summary")
        print(f"{'='*60}")
        for metric, avg_score in summary["average_scores"].items():
            status = "✅" if avg_score >= 0.7 else "⚠️" if avg_score >= 0.5 else "❌"
            print(f"   {status} {metric}: {avg_score:.3f}")
        print(f"\n   Overall Score: {summary['overall_score']:.3f}")
        print(f"{'='*60}\n")
        
        # Save results
        if save_results:
            if output_path is None:
                output_path = Path(__file__).parent / f"eval_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            self._save_results(output_path, summary)
            print(f"📁 Results saved to: {output_path}")
        
        return summary
    
    def _aggregate_results(self) -> Dict:
        """Aggregate individual results into summary statistics"""
        if not self.results:
            return {"average_scores": {}, "overall_score": 0.0}
        
        # Collect all scores
        all_scores = {}
        for result in self.results:
            for metric, score in result.scores.items():
                if metric not in all_scores:
                    all_scores[metric] = []
                all_scores[metric].append(score)
        
        # Calculate averages
        average_scores = {
            metric: sum(scores) / len(scores)
            for metric, scores in all_scores.items()
        }
        
        # Overall score (weighted average)
        weights = {
            "faithfulness": 0.3,
            "answer_relevance": 0.25,
            "context_relevance": 0.2,
            "answer_correctness": 0.25
        }
        
        overall = 0.0
        total_weight = 0.0
        for metric, avg in average_scores.items():
            weight = weights.get(metric, 0.2)
            overall += avg * weight
            total_weight += weight
        
        overall_score = overall / total_weight if total_weight > 0 else 0.0
        
        return {
            "average_scores": average_scores,
            "overall_score": overall_score,
            "total_cases": len(self.results),
            "timestamp": datetime.now().isoformat()
        }
    
    def _save_results(self, path: str, summary: Dict):
        """Save detailed results to JSON file"""
        output = {
            "summary": summary,
            "detailed_results": [
                {
                    "question": r.question,
                    "generated_answer": r.generated_answer,
                    "ground_truth": r.ground_truth,
                    "contexts": r.retrieved_contexts[:3],  # Limit for readability
                    "scores": r.scores
                }
                for r in self.results
            ]
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
