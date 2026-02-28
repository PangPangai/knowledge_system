#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Knowledge Base Admin CLI Tool
管理员命令行工具 - 用于管理知识库文档
"""

import os
import sys
import time
import shutil
import argparse
import re
import fitz
from typing import List, Optional, Tuple
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

class PDFScanner:
    """Utility to detect garbled PDF extraction (Identity-H issues)."""
    @staticmethod
    def is_garbled(pdf_path: str) -> Tuple[bool, str]:
        if not pdf_path.lower().endswith('.pdf'):
            return False, "Not a PDF"
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            # Sample start and middle
            sample_indices = [0]
            if total_pages > 50: sample_indices.append(50)
            if total_pages > 100: sample_indices.append(102)
            
            sample_text = ""
            for idx in sample_indices:
                if idx < total_pages:
                    sample_text += doc[idx].get_text()
            
            doc.close()
            
            if not sample_text.strip():
                return False, "Empty or Scanned PDF"

            if "Chu<" in sample_text or "<untdilbtm" in sample_text or "u<<" in sample_text or "<uti" in sample_text:
                return True, "Identity-H Font Mapping Failure (Detected specific garbage patterns)"

            clean_chars = len(re.findall(r'[a-zA-Z0-9\s\.,;:!?\(\)\-\*/%#_\[\]\{\}]', sample_text))
            total_chars = len(sample_text)
            clean_ratio = clean_chars / max(1, total_chars)
            
            if clean_ratio < 0.7:
                return True, f"Low text density ({clean_ratio:.2f}) - likely garbled"
            
            return False, f"Clean (Density: {clean_ratio:.2f})"
        except Exception as e:
            return False, f"Scan Error: {e}"


class KnowledgeBaseAdmin:
    """Knowledge Base Admin CLI"""
    
    def __init__(self, api_base: str = API_BASE_URL):
        self.api_base = api_base.rstrip('/')
    
    def check_health(self) -> bool:
        """Check if backend is running"""
        try:
            response = requests.get(f"{self.api_base}/health", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def _send_file(self, file_path: str, endpoint: str = "/upload", timeout: int = 300) -> dict:
        """Send file to the specified upload endpoint"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        allowed_extensions = ['.pdf', '.md', '.markdown']
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in allowed_extensions:
            raise ValueError(f"Unsupported file type: {file_ext}. Only PDF and Markdown are supported.")

        content_type = 'application/pdf' if file_ext == '.pdf' else 'text/markdown'

        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f, content_type)}
            response = requests.post(
                f"{self.api_base}{endpoint}",
                files=files,
                timeout=timeout,
            )

        if response.status_code != 200:
            raise Exception(f"Upload failed: {response.text}")
        return response.json()

    def upload_document(self, file_path: str, poll_interval: int = 3) -> dict:
        """
        Async upload: submit file then poll until processing completes.
        Streams task logs to the local terminal incrementally during processing.
        """
        # Step 1: Submit file (timeout covers network transfer only)
        result = self._send_file(file_path, endpoint="/upload", timeout=300)
        task_id = result["task_id"]

        # Step 2: Poll until completed or failed, printing new log lines
        last_log_count = 0
        last_was_transient = False
        transient_icons = ["⏳", "⚙️", "🔢"]

        while True:
            status = self.get_task_status(task_id)
            state = status["status"]

            # Print any new log lines since last poll
            logs = status.get("logs", [])
            for line in logs[last_log_count:]:
                line = line.strip()
                if not line:
                    continue
                
                # Check if this line is a "transient" progress update
                is_transient = any(line.startswith(icon) for icon in transient_icons)
                
                if is_transient and last_was_transient:
                    # Clear last line (Move up 1, Clear line)
                    # \033[A = move up, \033[K = clear line from cursor to end
                    print("\033[F\033[K", end="")
                    print(f"   {line}")
                else:
                    print(f"   {line}")
                
                last_was_transient = is_transient

            last_log_count = len(logs)

            if state == "completed":
                return {
                    "filename": status["filename"],
                    "chunks_created": status["chunks_created"],
                    "processing_duration": status.get("processing_duration"),
                }
            elif state == "failed":
                raise Exception(f"Processing failed: {status.get('error', 'unknown')}")

            if last_log_count == 0:
                # No logs yet - show pending indicator
                print(f"   ⏳ {state}...", end="\r")
            time.sleep(poll_interval)

    def upload_document_sync(self, file_path: str) -> dict:
        """Sync upload: wait for full processing (for small files / debug)"""
        return self._send_file(file_path, endpoint="/upload/sync", timeout=7200)

    def get_task_status(self, task_id: str, retries: int = 3) -> dict:
        """Get background task status with auto-retry for transient failures"""
        for attempt in range(retries):
            try:
                response = requests.get(
                    f"{self.api_base}/tasks/{task_id}", timeout=30
                )
                if response.status_code == 404:
                    raise FileNotFoundError(f"Task not found: {task_id}")
                if response.status_code != 200:
                    raise Exception(f"Failed to get task status: {response.text}")
                return response.json()
            except requests.exceptions.Timeout:
                if attempt < retries - 1:
                    print(f"   ⚠️ 轮询超时, 重试中 ({attempt + 2}/{retries})...")
                    time.sleep(5)
                else:
                    raise

    def list_tasks(self) -> list:
        """List all background tasks"""
        response = requests.get(f"{self.api_base}/tasks", timeout=10)
        if response.status_code != 200:
            raise Exception(f"Failed to list tasks: {response.text}")
        return response.json()["tasks"]
    
    def list_documents(self) -> List[dict]:
        """List all documents in knowledge base"""
        response = requests.get(f"{self.api_base}/documents")
        
        if response.status_code != 200:
            raise Exception(f"Failed to list documents: {response.text}")
        
        return response.json()['documents']
    
    def delete_document(self, filename: str) -> bool:
        """Delete a document from knowledge base"""
        response = requests.delete(f"{self.api_base}/documents/{filename}")
        
        if response.status_code == 404:
            raise FileNotFoundError(f"Document not found: {filename}")
        elif response.status_code != 200:
            raise Exception(f"Delete failed: {response.text}")
        
        return True
    
    def clear_all(self) -> int:
        """Delete ALL documents from knowledge base"""
        docs = self.list_documents()
        deleted = 0
        for doc in docs:
            try:
                self.delete_document(doc['filename'])
                deleted += 1
            except Exception as e:
                print(f"   ⚠️ Failed to delete {doc['filename']}: {e}")
        return deleted
        
    def discover_tools(self) -> dict:
        """Trigger automated tool discovery"""
        response = requests.post(f"{self.api_base}/tools/discover", timeout=60)
        if response.status_code != 200:
             raise Exception(f"Discovery failed: {response.text}")
        return response.json()


def cmd_upload(args):
    """Upload command handler"""
    admin = KnowledgeBaseAdmin(args.api)

    if not admin.check_health():
        print("❌ 错误: 后端服务未启动!")
        print(f"   请确保后端运行在 {args.api}")
        sys.exit(1)

    # Collect files to upload
    files_to_upload = []
    if os.path.isdir(args.file):
        print(f"📂 扫描目录: {args.file}")
        for root, _, files in os.walk(args.file):
            for file in files:
                if file.lower().endswith(('.pdf', '.md', '.markdown')):
                    files_to_upload.append(os.path.join(root, file))
        if not files_to_upload:
            print("⚠️ 目录中未找到支持的文档 (.pdf, .md, .markdown)")
            return
    elif os.path.isfile(args.file):
        files_to_upload.append(args.file)
    else:
        print(f"❌ 路径不存在: {args.file}")
        sys.exit(1)

    success_count = 0
    fail_count = 0
    skip_count = 0
    
    # Check existing files for incremental update
    existing_files = set()
    try:
        remote_docs = admin.list_documents()
        existing_files = {doc.get('filename') for doc in remote_docs if doc.get('filename')}
        print(f"🔄 知识库已有 {len(existing_files)} 个文档，将跳过重复文件。\n")
    except Exception as e:
        print(f"⚠️ 无法获取现有文档列表，将尝试上传所有文件: {e}\n")

    print(f"🚀 开始处理 {len(files_to_upload)} 个文件...")

    # --- PHASE 1: PRE-SCAN ALL PDFS ---
    print(f"\n🔍 [Phase 1/2] 正在进行文档质量扫描...")
    bad_files = set()
    for filename_path in files_to_upload:
        if filename_path.lower().endswith('.pdf'):
            is_bad, reason = PDFScanner.is_garbled(filename_path)
            if is_bad:
                bad_files.add(filename_path)
                print(f"   ❌ {os.path.basename(filename_path):<50} | {reason}")
            else:
                # Optionally print clean ones too if verbosity is desired, but keeping output lean
                pass
    
    if bad_files:
        print(f"\n⚠️ 发现 {len(bad_files)} 个乱档 PDF，将自动跳过。")
    else:
        print("   ✅ 所有 PDF 文档质量检查通过。")

    # --- PHASE 2: UPLOAD CLEAN FILES ---
    print(f"\n🚀 [Phase 2/2] 开始上传有效文件...")
    
    for idx, file_path in enumerate(files_to_upload, 1):
        filename = os.path.basename(file_path)
        
        if file_path in bad_files:
            print(f"[{idx}/{len(files_to_upload)}] ⏭️ 跳过 (质量检查未通过): {filename}")
            fail_count += 1
            continue

        if filename in existing_files:
            print(f"[{idx}/{len(files_to_upload)}] ⏭️ 跳过 (已存在): {filename}")
            skip_count += 1
            continue

        try:
            print(f"📤 [{idx}/{len(files_to_upload)}] 上传中: {filename}")
            if args.sync:
                result = admin.upload_document_sync(file_path)
            else:
                result = admin.upload_document(file_path)
            
            print(f"   ✅ 成功: {result['filename']} (片段: {result['chunks_created']})")
            success_count += 1
        except Exception as e:
            print(f"   ❌ 失败: {filename} - {e}")
            fail_count += 1

    print(f"\n📊 上传完成: 成功 {success_count}, 跳过 {skip_count}, 失败 {fail_count}")

    # Auto-trigger discovery unless disabled
    if not args.no_discover and success_count > 0:
        print("\n🔍 正在自动扫描新工具 (更新 tools_config.json)...")
        try:
            disc_result = admin.discover_tools()
            if disc_result.get("new_tools"):
                 print(f"   🆕 发现并添加新工具: {', '.join(disc_result['new_tools'])}")
            else:
                 print(f"   ✅ 配置已更新 (无新工具发现)")
        except Exception as e:
            print(f"   ⚠️ 自动发现失败: {e}")


def cmd_tasks(args):
    """List background tasks"""
    admin = KnowledgeBaseAdmin(args.api)

    if not admin.check_health():
        print("❌ 错误: 后端服务未启动!")
        sys.exit(1)

    try:
        tasks = admin.list_tasks()
        if not tasks:
            print("📭 无后台任务")
            return

        print(f"📋 后台任务列表 (共 {len(tasks)} 个):\n")
        for t in tasks:
            icon = {"pending": "⏳", "processing": "⚙️", "completed": "✅", "failed": "❌"}.get(t["status"], "❓")
            line = f"  {icon} [{t['task_id']}] {t['filename']}  状态: {t['status']}"
            if t["chunks_created"]:
                line += f"  片段: {t['chunks_created']}"
            if t.get("processing_duration"):
                line += f"  耗时: {t['processing_duration']:.2f}s"
            if t.get("error"):
                line += f"  错误: {t['error']}"
            print(line)
    except Exception as e:
        print(f"❌ 获取任务列表失败: {e}")
        sys.exit(1)


def cmd_list(args):
    """List command handler"""
    admin = KnowledgeBaseAdmin(args.api)
    
    if not admin.check_health():
        print("❌ 错误: 后端服务未启动!")
        sys.exit(1)
    
    try:
        documents = admin.list_documents()
        
        if not documents:
            print("📭 知识库为空")
            return
        
        print(f"📚 知识库文档列表 (共 {len(documents)} 个):\n")
        for idx, doc in enumerate(documents, 1):
            print(f"  {idx}. {doc['filename']}")
            print(f"     片段数: {doc['chunks']}")
            print()
    except Exception as e:
        print(f"❌ 获取列表失败: {e}")
        sys.exit(1)


def cmd_delete(args):
    """Delete command handler"""
    admin = KnowledgeBaseAdmin(args.api)
    
    if not admin.check_health():
        print("❌ 错误: 后端服务未启动!")
        sys.exit(1)
    
    # Confirmation
    if not args.yes:
        confirm = input(f"确定要删除 '{args.filename}' 吗? (y/N): ")
        if confirm.lower() != 'y':
            print("❌ 已取消")
            return
    
    try:
        admin.delete_document(args.filename)
        print(f"✅ 已删除: {args.filename}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 删除失败: {e}")
        sys.exit(1)


def cmd_clear(args):
    """Clear all documents command handler"""
    admin = KnowledgeBaseAdmin(args.api)
    
    # Fast mode: delete chroma_db folder directly
    if args.fast:
        chroma_path = os.path.join(os.path.dirname(__file__), 'chroma_db')
        
        if not os.path.exists(chroma_path):
            print("ℹ️ 知识库为空，无需清理")
            return
        
        # Confirmation
        if not args.yes:
            confirm = input(f"⚠️ 快速模式将直接删除 chroma_db 文件夹，此操作不可逆! (y/N): ")
            if confirm.lower() != 'y':
                print("❌ 已取消")
                return
        
        print("🗑️ 正在快速清空知识库...")
        try:
            shutil.rmtree(chroma_path)
            print("✅ 已清空知识库 (请重启后端服务)")
        except Exception as e:
            print(f"❌ 删除失败: {e}")
            sys.exit(1)
        return
    
    # Normal mode: API calls
    if not admin.check_health():
        print("❌ 错误: 后端服务未启动!")
        sys.exit(1)
    
    # Get document count first
    docs = admin.list_documents()
    count = len(docs)
    
    if count == 0:
        print("ℹ️ 知识库为空，无需清理")
        return
    
    # Confirmation
    if not args.yes:
        confirm = input(f"⚠️ 确定要删除全部 {count} 个文档吗? 此操作不可逆! (y/N): ")
        if confirm.lower() != 'y':
            print("❌ 已取消")
            return
    
    print(f"🗑️ 正在清空知识库 ({count} 个文档)...")
    deleted = admin.clear_all()
    print(f"✅ 已删除 {deleted}/{count} 个文档")


def cmd_discover(args):
    """Discover tools command handler"""
    admin = KnowledgeBaseAdmin(args.api)
    
    if not admin.check_health():
        print("❌ 错误: 后端服务未启动!")
        sys.exit(1)
        
    print("🔍 正在扫描现有文档以发现新工具...")
    try:
        result = admin.discover_tools()
        new_tools = result.get("new_tools", [])
        print(f"✅ 扫描完成!")
        if new_tools:
            print(f"   🆕 新发现工具 ({len(new_tools)}): {', '.join(new_tools)}")
        else:
            print(f"   ℹ️ 未发现新工具 (现有配置已覆盖)")
    except Exception as e:
        print(f"❌ 扫描失败: {e}")
        sys.exit(1)


def cmd_status(args):
    """Status command handler"""
    admin = KnowledgeBaseAdmin(args.api)
    
    print(f"🔍 检查后端状态: {args.api}")
    
    if admin.check_health():
        print("✅ 后端服务运行正常")
        try:
            documents = admin.list_documents()
            print(f"📚 知识库文档数: {len(documents)}")
        except:
            print("⚠️  无法获取文档统计")
    else:
        print("❌ 后端服务未运行")
        print("   请先启动后端: cd backend && py -m uvicorn main:app --reload")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Knowledge Base Admin CLI - 知识库管理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 上传文档
  python admin_cli.py upload document.pdf
  
  # 列出所有文档
  python admin_cli.py list
  
  # 删除文档
  python admin_cli.py delete document.pdf
  
  # 检查状态
  python admin_cli.py status
        """
    )
    
    parser.add_argument(
        '--api',
        default=API_BASE_URL,
        help=f'API 地址 (默认: {API_BASE_URL})'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # Upload command
    upload_parser = subparsers.add_parser('upload', aliases=['u'], help='上传文档或目录 (默认开启自动工具发现)')
    upload_parser.add_argument('file', help='文件或目录路径')
    upload_parser.add_argument('-s', '--sync', action='store_true', help='同步模式 (等待处理完成)')
    upload_parser.add_argument('--no-discover', action='store_true', help='禁用上传后的自动工具发现')
    upload_parser.set_defaults(func=cmd_upload)

    # List command
    list_parser = subparsers.add_parser('list', aliases=['l'], help='列出所有文档')
    list_parser.set_defaults(func=cmd_list)

    # Delete command
    delete_parser = subparsers.add_parser('delete', aliases=['d'], help='删除文档')
    delete_parser.add_argument('filename', help='文件名')
    delete_parser.add_argument('-y', '--yes', action='store_true', help='跳过确认')
    delete_parser.set_defaults(func=cmd_delete)

    # Status command
    status_parser = subparsers.add_parser('status', help='检查后端状态')
    status_parser.set_defaults(func=cmd_status)

    # Tasks command
    tasks_parser = subparsers.add_parser('tasks', aliases=['t'], help='查看后台任务')
    tasks_parser.set_defaults(func=cmd_tasks)

    # Clear command
    clear_parser = subparsers.add_parser('clear', help='清空所有文档')
    clear_parser.add_argument('-y', '--yes', action='store_true', help='跳过确认')
    clear_parser.add_argument('-f', '--fast', action='store_true', help='快速模式 (直接删除数据库文件夹)')
    clear_parser.set_defaults(func=cmd_clear)
    
    # Discover tools command
    disc_parser = subparsers.add_parser('discover-tools', aliases=['disc'], help='自动发现新工具并更新配置')
    disc_parser.set_defaults(func=cmd_discover)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    args.func(args)


if __name__ == '__main__':
    main()
