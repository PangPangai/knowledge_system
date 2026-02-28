# RAG 参数调研报告：Top-K 与 Rerank 策略

本文档总结了业界针对**复杂技术文档（Complex Technical Documents）**场景下 RAG 系统的检索参数（Retrieval Top-K & Rerank Top-N）的最优实践调研结果。

---

## 1. 调研背景
在处理 EDA 手册等复杂技术文档时，系统面面临术语密度高、逻辑紧密、跨页关联多等挑战。单纯依赖语义相似度（Vector）容易丢失精确指令，因此通用的两阶段检索（Hybrid + Rerank）是标准架构。

---

## 2. 核心参数据指标

### A. 初始召回 Top-K (Retrieval Top-K / 粗排)
目标是**召回率（Recall）**，即确保正确答案在候选池中。

| 来源                   | 建议值       | 技术背景                                                                       |
| :--------------------- | :----------- | :----------------------------------------------------------------------------- |
| **Anthropic**          | **150**      | 使用 Contextual Retrieval 架构，初始海选 150 个 Chunk 效果显著优于小规模召回。 |
| **Pinecone**           | **25 - 100** | 建议取 Rerank 目标数的 3 倍以上，视语料库规模而定。                            |
| **Cohere (Rerank v4)** | **≤ 100**    | API 单次处理上限通常为 100 个文档片段。                                        |
| **业界生产实践**       | **50 - 100** | 技术场景下建议偏大（100+），为重排阶段提供足够的上下文多样性。                 |

### B. 重排 Top-N (Rerank Top-N / 精排)
目标是**准确率（Precision）**，并减少 LLM 的上下文偏离（Lost in the Middle）。

| 来源                   | 建议值     | 适用场景                                                                     |
| :--------------------- | :--------- | :--------------------------------------------------------------------------- |
| **Anthropic (Claude)** | **20**     | 基于 Claude 系列强大的长上下文处理能力，20 个 Chunk 组合生成的答案更全面。   |
| **Pinecone/Cohere**    | **5 - 10** | 对于多数推理模型，Top 5-10 能在有效信息与噪声干扰之间取得最佳平衡。          |
| **学术研究表明**       | **~10**    | 研究发现，经过精排后，提供约 10 个上下文片段能达到长文本问答的性能“甜点区”。 |

---

## 3. 本项目参数建议 (针对 EDA 领域)

结合调研结果与本项目特点（使用 BGE-Reranker-v2-m3），建议配置如下：

| 参数名称            | 设定值      | 理由                                                                          |
| :------------------ | :---------- | :---------------------------------------------------------------------------- |
| **RETRIEVAL_TOP_K** | **100**     | 保持高召回率。EDA 领域专有名词多，需要大的候选池来捕获细微特征。              |
| **RERANK_TOP_N**    | **10 ~ 20** | 取决于使用的推理模型性能。对于 Claude/GPT-4o 建议 20，对于本地小模型建议 10。 |

---

## 4. 关键架构级优化建议

单纯依靠参数调优无法解决所有问题，调研显示以下两个架构变更是性能提升的核心：

1. **并行化评分 (Parallel Grading)**:
   - **痛点**: Rerank Top-N 过大（如 20）会导致 `grade_node` 串行调用 LLM 时产生几十秒的延迟。
   - **对策**: 必须实现 `asyncio.gather` 并发打分，将响应时间压缩到单次 API 调用的水平（2-3秒）。

2. **混合检索权重对齐**:
   - 在 `RETRIEVAL_TOP_K=100` 的前提下，前端 `Vector/BM25` 的权重微调收益极小。
   - 建议废弃复杂的基于正则的权重判断，回归 **0.5/0.5 均衡配准**，将决定权完全赋予重排器（Cross-Encoder Reranker）。

---

## 5. 参考来源
- [Anthropic: Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
- [Cohere: Reranking in RAG](https://docs.cohere.com/docs/reranking-in-rag)
- [Pinecone: Reranking Knowledge Base](https://www.pinecone.io/learn/series/rag/rerankers/)
- [Benchmarks: Precision@K vs. Recall@K trade-offs in 2024](https://milvus.io/blog/)
