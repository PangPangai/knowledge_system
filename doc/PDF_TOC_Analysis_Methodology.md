# PDF 目录层级与字符统计分析方案

本文档介绍如何使用 Python 脚本自动化分析 PDF 文档的目录结构（Table of Contents, TOC），并统计各层级章节的字符数与 Token 数量。该分析对于评估 RAG 系统的切片（Chunking）策略具有重要参考价值。

## 1. 分析方法论

### 1.1 核心思路
不直接读取全文，而是基于 PDF 内置的 **书签（Bookmarks/Outlines）** 来界定“语义章节”。
1.  **提取 TOC**：获取每个书签的 `(层级, 标题, 起始页码)`。
2.  **确定范围**：当前书签的结束页码 = 下一个书签的起始页码 - 1。
3.  **文本提取**：读取该范围内的所有页面文本。
4.  **计量统计**：
    *   **字符数 (Chars)**：直接使用 Python `len()`。
    *   **Token 数**：使用 OpenAI `tiktoken` (cl100k_base) 编码器进行精确计量。

### 1.2 技术栈
*   **PyMuPDF (fitz)**: 高性能 PDF 解析库，用于快速提取 TOC 和页面文本。
*   **tiktoken**: 用于计算文本对应的 LLM Token 数量。
*   **Statistics**: 用于计算平均值、中位数等统计指标。

## 2. 实现脚本

分析脚本位于：`knowledge_system/backend/analyze_corpus_toc.py`

### 关键代码逻辑

```python
import fitz
import tiktoken
import statistics

def analyze_pdf_toc(pdf_path):
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()  # 返回列表: [[lvl, title, page_num], ...]

    level_stats = {} # 存储各层级的统计数据

    for i, entry in enumerate(toc):
        level, title, page = entry[0], entry[1], entry[2]
        start_page_idx = page - 1
        
        # 1. 计算结束页码
        if i + 1 < len(toc):
            end_page_idx = toc[i+1][2] - 1
        else:
            end_page_idx = len(doc) - 1
            
        # 2. 提取该章节范围内的文本
        full_text = ""
        for p_idx in range(start_page_idx, end_page_idx + 1):
            full_text += doc.load_page(p_idx).get_text()
            
        # 3. 统计指标
        char_count = len(full_text)
        token_count = len(tiktoken.get_encoding("cl100k_base").encode(full_text))
        
        # 4. 归档
        if level not in level_stats:
            level_stats[level] = {"chars": [], "tokens": []}
        level_stats[level]["chars"].append(char_count)
        level_stats[level]["tokens"].append(token_count)
        
    return level_stats
```

## 3. 分析结果示例

以下是使用上述脚本对 `knowledge_system/input_data` 目录下的 7 份 EDA 技术文档（Fusion Compiler & PrimeTime）进行全量扫描后的统计结果。

### 数据说明
*   **Avg Chars / Max Chars**: 章节的字符数统计。
*   **Avg Tokens / Max Tokens**: 章节的 Token 数统计（更贴近 LLM 上下文消耗）。

### 统计报表

| 文档名称                             |  层级  |   章节数   | 平均字符数 | 最大字符数  | **平均 Token** | **最大 Token** |
| :----------------------------------- | :----: | :--------: | :--------: | :---------: | :------------: | :------------: |
| **fcug.pdf**                         |   H1   |     15     |   8,678    |   95,745    |   **2,994**    |   **37,167**   |
| (Fusion Compiler User Guide)         |   H2   |    197     |   3,628    |   12,755    |    **842**     |   **2,800**    |
|                                      |   H3   |    453     |   3,734    |   12,301    |    **871**     |   **3,835**    |
|                                      | **H4** |  **241**   | **3,628**  | **11,403**  |    **844**     |   **2,639**    |
|                                      |   H5   |     64     |   3,582    |   11,033    |    **874**     |   **3,663**    |
| **ptug+.pdf**                        |   H1   |     28     |   7,012    |   126,273   |   **2,371**    |   **51,230**   |
| (PrimeTime User Guide)               |   H2   |    187     |   3,566    |    9,883    |    **814**     |   **2,692**    |
|                                      |   H3   |    555     |   3,541    |   12,902    |    **822**     |   **3,247**    |
|                                      | **H4** |  **433**   | **3,585**  | **14,772**  |    **827**     |   **3,871**    |
|                                      |   H5   |    177     |   3,284    |   13,367    |    **748**     |   **2,710**    |
| **Fusion Compiler Tool Commands**    |   H1   |     2      |    111k    |    221k     |    **50k**     |    **99k**     |
|                                      |   H2   |     21     |   1,134    |    1,579    |    **272**     |    **420**     |
|                                      | **H3** | **2,837**  | **5,139**  | **62,888**  |   **1,183**    |   **14,754**   |
| **Fusion Compiler Error Messages**   |   H1   |     2      |    118k    |    235k     |    **59k**     |    **118k**    |
|                                      |   H2   |    250     |   1,186    |    1,925    |    **282**     |    **529**     |
|                                      | **H3** | **23,682** | **1,745**  | **10,693**  |    **419**     |   **2,508**    |
| **Variables & Attributes**           |   H1   |     3      |    68k     |    204k     |    **27k**     |    **82k**     |
|                                      |   H2   |     38     |   1,256    |    1,813    |    **276**     |    **377**     |
|                                      | **H3** | **2,604**  | **2,502**  | **36,080**  |    **568**     |   **7,783**    |
| **Application Options & Attributes** |   H1   |     3      |    68k     |    203k     |    **35k**     |    **106k**    |
|                                      |   H2   |     61     |   1,369    |    2,247    |    **692**     |   **1,193**    |
|                                      | **H3** | **3,827**  | **4,274**  | **130,424** |   **2,126**    |   **65,783**   |

*(注：该统计数据生成于 2026-02-13)*
