"""
RAG Evaluation Metrics Module
Implements core evaluation metrics for RAG systems
"""

import os
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class EvaluationResult:
    """Single evaluation result"""
    question: str
    generated_answer: str
    ground_truth: Optional[str]
    retrieved_contexts: List[str]
    scores: Dict[str, float]


class RAGMetrics:
    """
    RAG evaluation metrics calculator
    Uses LLM-as-judge for semantic evaluation
    """
    
    def __init__(self, llm):
        """
        Args:
            llm: LangChain LLM instance for evaluation
        """
        self.llm = llm
    
    async def faithfulness(
        self, 
        answer: str, 
        contexts: List[str]
    ) -> float:
        """
        Evaluate if the answer is faithful to the retrieved contexts
        (no hallucination)
        
        Returns:
            Score between 0 and 1
        """
        if not contexts or not answer.strip():
            return 0.0
        
        context_text = "\n\n".join(contexts)
        
        prompt = f"""你是一个严格的事实核查员。请判断【答案】中的每个声明是否都有【上下文】的支撑。

【上下文】
{context_text}

【答案】
{answer}

评分标准:
- 1.0: 答案中所有声明都有上下文支撑
- 0.7: 大部分声明有支撑，少数无法验证
- 0.5: 一半声明有支撑
- 0.3: 大部分声明没有上下文支撑
- 0.0: 答案完全是编造的

只输出一个0到1之间的数字，不要解释:"""

        try:
            from langchain_core.messages import HumanMessage
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            score = float(response.content.strip())
            return max(0.0, min(1.0, score))
        except Exception as e:
            print(f"Faithfulness evaluation error: {e}")
            return 0.5
    
    async def answer_relevance(
        self, 
        question: str, 
        answer: str
    ) -> float:
        """
        Evaluate if the answer directly addresses the question
        
        Returns:
            Score between 0 and 1
        """
        if not answer.strip():
            return 0.0
        
        prompt = f"""你是一个问答质量评估员。请判断【答案】是否直接回答了【问题】。

【问题】
{question}

【答案】
{answer}

评分标准:
- 1.0: 答案完全切题，直接回答了问题
- 0.7: 答案基本切题，但有些偏离
- 0.5: 答案部分相关
- 0.3: 答案大部分不相关
- 0.0: 答案完全没有回答问题

只输出一个0到1之间的数字，不要解释:"""

        try:
            from langchain_core.messages import HumanMessage
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            score = float(response.content.strip())
            return max(0.0, min(1.0, score))
        except Exception as e:
            print(f"Answer relevance evaluation error: {e}")
            return 0.5
    
    async def context_relevance(
        self, 
        question: str, 
        contexts: List[str]
    ) -> float:
        """
        Evaluate if retrieved contexts are relevant to the question
        
        Returns:
            Score between 0 and 1
        """
        if not contexts:
            return 0.0
        
        # Evaluate each context and average
        scores = []
        for ctx in contexts[:5]:  # Limit to 5 contexts
            prompt = f"""判断以下【上下文】与【问题】的相关性。

【问题】
{question}

【上下文】
{ctx[:500]}

相关性评分 (0-1):
- 1.0: 高度相关，直接包含答案
- 0.7: 相关，包含有用信息
- 0.5: 部分相关
- 0.3: 边缘相关
- 0.0: 完全不相关

只输出数字:"""
            
            try:
                from langchain_core.messages import HumanMessage
                response = await self.llm.ainvoke([HumanMessage(content=prompt)])
                score = float(response.content.strip())
                scores.append(max(0.0, min(1.0, score)))
            except:
                scores.append(0.5)
        
        return sum(scores) / len(scores) if scores else 0.0
    
    async def answer_correctness(
        self, 
        answer: str, 
        ground_truth: str
    ) -> float:
        """
        Evaluate semantic similarity between answer and ground truth
        
        Returns:
            Score between 0 and 1
        """
        if not ground_truth or not answer.strip():
            return 0.5  # Unknown if no ground truth
        
        prompt = f"""比较【生成答案】与【参考答案】的语义一致性。

【参考答案】
{ground_truth}

【生成答案】
{answer}

评分标准:
- 1.0: 语义完全一致，信息完整
- 0.8: 语义基本一致，可能表述不同
- 0.6: 包含主要信息，但有遗漏
- 0.4: 部分正确
- 0.2: 大部分不正确
- 0.0: 完全错误

只输出一个0到1之间的数字:"""

        try:
            from langchain_core.messages import HumanMessage
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            score = float(response.content.strip())
            return max(0.0, min(1.0, score))
        except Exception as e:
            print(f"Answer correctness evaluation error: {e}")
            return 0.5
