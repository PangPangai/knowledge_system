# RAG 知识库系统优化报告

**项目名称**: EDA 知识库 RAG 系统  
**优化目标**: 提升回答质量至 NotebookLM 水准  
**完成日期**: 2026-02-04

---

## 一、优化概述

本次优化针对 EDA 知识库 RAG 系统进行了全面改进，涵盖检索参数调优、System Prompt 重构、来源匹配算法升级以及前端 Bug 修复四个核心方面。

---

## 二、检索参数优化

### 2.1 参数调整

| 参数                 | 优化前 | 优化后   | 说明                               |
| -------------------- | ------ | -------- | ---------------------------------- |
| `RETRIEVAL_TOP_K`    | 20     | **30**   | 初检召回数量，增加候选池           |
| `RERANK_TOP_N`       | 5      | **10**   | 精排保留数量，提供更多上下文       |
| `max_content_length` | 1500   | **2500** | 单文档最大内容长度，保留更完整信息 |

### 2.2 涉及文件

- [.env](file:///c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/backend/.env)
- [rag_engine.py](file:///c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/backend/rag_engine.py)

---

## 三、System Prompt 优化

### 3.1 问题描述

原有 Prompt 导致回答风格机械，开头固定使用 "根据参考文档..." 等模板化措辞，用户体验较差。

### 3.2 优化方案

| 项目     | 优化前       | 优化后             |
| -------- | ------------ | ------------------ |
| 角色定位 | 无明确定位   | **"EDA 技术专家"** |
| 对话风格 | 机械模板化   | **自然对话**       |
| 回答方式 | 强调来源出处 | **直接回答问题**   |

### 3.3 涉及文件

- [rag_engine.py](file:///c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/backend/rag_engine.py)

---

## 四、来源精准匹配

### 4.1 问题描述

用户提问 "FC 中的..." 相关问题时，系统错误引用 PT（PrimeTime）文档，导致回答来源与问题不匹配。

### 4.2 解决方案

新增 `_filter_by_source_priority()` 方法，根据用户问题中的工具关键词动态调整文档优先级。

#### 工具匹配模式

```python
tool_patterns = {
    r'\bfc\b|\bfusion\s*compiler\b': ['fc', 'fusion', 'FC'],
    r'\bpt\b|\bprimetime\b': ['pt', 'primetime', 'PT'],
    r'\bicc2\b': ['icc2', 'icc', 'ICC'],
    r'\bdc\b': ['dc', 'design_compiler', 'DC'],
}
```

### 4.3 匹配逻辑

1. 从用户问题中提取工具关键词（如 fc, pt, icc2）
2. 根据关键词匹配相应的文档来源标识
3. 对匹配的文档进行优先排序
4. 确保回答来源与问题高度相关

### 4.4 涉及文件

- [rag_engine.py#L631-689](file:///c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/backend/rag_engine.py#L631-L689)

---

## 五、前端 Bug 修复

### 5.1 消息丢失问题

| 项目     | 内容                                                |
| -------- | --------------------------------------------------- |
| **现象** | AI 流式输出时用户问题从界面消失                     |
| **根因** | `useEffect` 获取历史消息时覆盖了本地状态            |
| **修复** | 添加 `isStreaming` 标志，在流式输出期间阻止状态覆盖 |

**涉及文件**: [ChatInterface.tsx](file:///c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/frontend/app/components/ChatInterface.tsx)

### 5.2 表格显示问题

| 项目     | 内容                                   |
| -------- | -------------------------------------- |
| **现象** | 表格第一列中文文字垂直排列，影响可读性 |
| **根因** | 缺少列最小宽度限制                     |
| **修复** | 添加 CSS 最小列宽约束                  |

```css
.prose th:first-child,
.prose td:first-child {
  min-width: 100px;
}
```

**涉及文件**: [globals.css](file:///c:/Niexingyu/AI/TRAE/backend/笔记/knowledge_system/frontend/app/globals.css)

---

## 六、变更文件汇总

| 文件                | 变更内容                   |
| ------------------- | -------------------------- |
| `.env`              | 检索参数调优               |
| `rag_engine.py`     | Prompt 优化 + 来源过滤算法 |
| `ChatInterface.tsx` | Streaming 状态修复         |
| `globals.css`       | 表格样式修复               |

---

## 七、验证方法

### 7.1 启动服务

```bash
cd backend && py main.py
```

### 7.2 测试用例

```
fc中有哪些改善congestion的手段
fc中的constant propagation和case propagation有什么区别
```

### 7.3 预期效果

- ✅ 回答结构化、详细
- ✅ 来源匹配正确（FC 问题引用 FC 文档）
- ✅ 语气自然专业

---

## 八、后续建议

1. **持续监控**: 观察实际使用中的来源匹配准确率
2. **扩展工具库**: 根据需要添加更多 EDA 工具的匹配模式
3. **用户反馈**: 收集用户对回答质量的反馈进行迭代优化
