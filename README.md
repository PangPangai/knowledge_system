# 数字后端知识库系统

基于 RAG (Retrieval-Augmented Generation) 的智能知识库系统,**管理员后台管理文档,用户纯聊天查询**。

## 🎯 功能特性

- 📄 **管理员文档管理**: 通过 CLI 工具上传/删除文档
- 💬 **用户智能问答**: 纯聊天界面,基于知识库对话
- 🔍 **来源追溯**: 每个回答标注参考来源
- 🎨 **现代化界面**: Glassmorphism 设计风格
- 🚀 **混合架构**: 本地向量存储 + 云端大模型推理

## 🛠️ 技术栈

### 后端
- **FastAPI**: 高性能 Python Web 框架
- **LangChain**: LLM 应用开发框架
- **ChromaDB**: 本地向量数据库
- **PyMuPDF**: PDF 文档解析

### 前端
- **Next.js 14**: React 框架 (App Router)
- **TypeScript**: 类型安全
- **Tailwind CSS**: 样式框架
- **React Markdown**: Markdown 渲染

## 📦 安装步骤

### 1. 后端设置

```powershell
cd backend

# 创建虚拟环境 (推荐)
py -m venv venv
.\venv\Scripts\activate

# 安装依赖 (使用国内镜像源)
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 额外安装 CLI 工具依赖
pip install requests -i https://pypi.tuna.tsinghua.edu.cn/simple

# 配置环境变量
copy .env.example .env
notepad .env
```

### 2. 前端设置

```powershell
cd frontend

# 安装依赖
npm install
```

## 🚀 启动服务

### 启动后端 (终端 1)

```powershell
cd backend
.\venv\Scripts\activate
py -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

或使用启动脚本:

```powershell
.\start_backend.bat
```

后端 API 文档: http://localhost:8000/docs

### 启动前端 (终端 2)

```powershell
cd frontend
npm run dev
```

或使用启动脚本:

```powershell
.\start_frontend.bat
```

前端界面: http://localhost:3000

## 🔑 API Key 配置

编辑 `backend/.env` 文件:

```env
# DeepSeek API (推荐,性价比高)
OPENAI_API_KEY=sk-your-deepseek-api-key
OPENAI_API_BASE=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat

# 或使用 OpenAI
# OPENAI_API_KEY=sk-your-openai-api-key
# OPENAI_API_BASE=https://api.openai.com/v1
# MODEL_NAME=gpt-4

# API Base URL (for CLI tools)
API_BASE_URL=http://localhost:8000
```

## 📖 使用指南

### 管理员 - 文档管理 (CLI)

#### 查看帮助

```powershell
cd backend
py admin_cli.py --help
```

#### 上传文档/目录

```powershell
# 1. 上传单个文件 (默认开启自动工具发现)
py admin_cli.py upload path/to/document.pdf

# 2. 递归上传整个目录 (自动跳过已存在的同名文件，实现增量更新)
py admin_cli.py upload D:\EDA_Docs\Innovus

# 3. 禁用上传后的自动工具发现 (如果你不想更新 tools_config.json)
py admin_cli.py upload path/to/docs --no-discover
```

#### 查看后台任务

```powershell
py admin_cli.py tasks
```

#### 列出所有文档

```powershell
py admin_cli.py list
```

#### 删除文档

```powershell
py admin_cli.py delete document.pdf
```

#### 清空知识库 (危险操作)

```powershell
# 正常模式: 逐个删除文档 (较慢，需要后端运行中)
py admin_cli.py clear

# 快速模式: 直接物理删除数据库文件夹 (瞬间完成)
# ⚠️ 关键: 必须先关闭后端服务窗口！否则会报错 [WinError 32] 文件被占用

# 方式 1: 手动关闭后端终端，然后运行:
py admin_cli.py clear --fast

# 方式 2 (推荐): 使用强制清理脚本 (会自动关闭后端进程)
.\force_clean.bat

```

#### 高级工具发现 (Tool Discovery)

```powershell
# 扫描现有文档文件名，自动更新 tools_config.json 中的工具匹配规则
# (通常在上传时会自动触发，此命令用于手动强制刷新)
py admin_cli.py discover-tools
```

#### 检查系统状态

```powershell
py admin_cli.py status
```

### 用户 - 聊天查询 (Web)

1. 访问 http://localhost:3000
2. 在聊天框输入问题
3. 系统会基于知识库回答,并显示参考来源

## 🎨 界面说明

**用户前端 (http://localhost:3000)**:
- 纯聊天界面,居中单栏布局
- 无文档上传/管理功能
- 专注于对话体验

**管理员后台**:
- 命令行工具 (CLI)
- 完整的文档管理功能
- 支持批量操作

## 📁 项目结构

```
knowledge_system/
├── backend/
│   ├── main.py              # FastAPI 主应用
│   ├── rag_engine.py        # RAG 核心引擎
│   ├── task_manager.py      # 异步上传任务管理器
│   ├── admin_cli.py         # 管理员 CLI 工具 (含批量上传)
│   ├── tools_config.json    # 可配置化工具规则
│   ├── requirements.txt     # Python 依赖
│   └── .env.example         # 环境变量模板
└── frontend/
    ├── app/
    │   ├── components/
    │   │   └── ChatInterface.tsx  # 聊天组件
    │   ├── page.tsx         # 主页面 (纯聊天)
    │   └── globals.css      # 全局样式
    └── package.json
```

## 🐛 常见问题

### CLI 工具提示 "后端服务未启动"
- 确认后端已启动: `py -m uvicorn main:app --reload`
- 检查端口是否正确 (默认 8000)
- 查看 `.env` 中的 `API_BASE_URL` 配置

### 上传文档失败
- 确认文件是 PDF 或 Markdown 格式
- 超大文件 (如 6000 页 PDF) 请使用默认异步模式上传，不要加 `--sync`
- 上传后可用 `py admin_cli.py tasks` 查看处理进度
- 查看后端终端日志获取详细错误信息

### 上传中断/失败后的处理
如果上传过程中意外中断（如进度条走到一半），数据库中可能残留部分"脏数据"。
**正确做法**：
1. **清理残余**：执行 `py admin_cli.py delete filename.pdf`（即使之前只传了一半，此命令也能清理干净）
2. **重新上传**：执行 `py admin_cli.py upload filename.pdf`
⚠️ 请勿直接重新上传，否则会导致内容重复（旧的残缺数据 + 新的完整数据）。

### 用户前端无法连接后端
- 确认后端服务已启动 (http://localhost:8000/health)
- 检查 CORS 配置
- 查看浏览器控制台错误信息

## 💡 使用场景示例

### 场景 1: 导入技术文档

```powershell
# 管理员操作: 批量导入 Innovus User Guide (自动扫描子目录)
cd backend
py admin_cli.py upload D:\EDA_Docs\Innovus
```

用户访问前端,提问: "如何在 Innovus 中优化时序?"

### 场景 2: 定期更新

```powershell
# 管理员操作: 上传新版本文档
cd backend
py admin_cli.py upload new_design_spec_v2.pdf

# 删除旧版本
py admin_cli.py delete design_spec_v1.pdf
```

## 🔧 后续优化建议

1. **访问控制**: 添加用户认证
2. **Web 管理界面**: 开发管理员 Web UI (可选)
3. **文档版本管理**: 支持文档版本控制
4. **多语言支持**: 支持英文/中文切换

## 📝 License

MIT License

## 👨‍💻 作者

数字后端工程师专用知识库系统 - 管理员后台管理 + 用户纯查询模式
