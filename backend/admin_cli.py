#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Knowledge Base Admin CLI Tool
管理员命令行工具 - 用于管理知识库文档
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


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
    
    def upload_document(self, file_path: str) -> dict:
        """Upload a document (PDF or Markdown) to knowledge base"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Check file extension
        allowed_extensions = ['.pdf', '.md', '.markdown']
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext not in allowed_extensions:
            raise ValueError(f"Unsupported file type: {file_ext}. Only PDF and Markdown are supported.")
        
        # Determine content type
        if file_ext == '.pdf':
            content_type = 'application/pdf'
        else:
            content_type = 'text/markdown'
        
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f, content_type)}
            response = requests.post(
                f"{self.api_base}/upload",
                files=files,
                timeout=900  # 15 minutes timeout for large files
            )
        
        if response.status_code != 200:
            raise Exception(f"Upload failed: {response.text}")
        
        return response.json()
    
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


def cmd_upload(args):
    """Upload command handler"""
    admin = KnowledgeBaseAdmin(args.api)
    
    if not admin.check_health():
        print("❌ 错误: 后端服务未启动!")
        print(f"   请确保后端运行在 {args.api}")
        sys.exit(1)
    
    try:
        print(f"📤 上传中: {args.file}")
        result = admin.upload_document(args.file)
        print(f"✅ 上传成功!")
        print(f"   文件名: {result['filename']}")
        print(f"   片段数: {result['chunks_created']}")
    except Exception as e:
        print(f"❌ 上传失败: {e}")
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
    upload_parser = subparsers.add_parser('upload', help='上传 PDF 文档')
    upload_parser.add_argument('file', help='PDF 文件路径')
    upload_parser.set_defaults(func=cmd_upload)
    
    # List command
    list_parser = subparsers.add_parser('list', help='列出所有文档')
    list_parser.set_defaults(func=cmd_list)
    
    # Delete command
    delete_parser = subparsers.add_parser('delete', help='删除文档')
    delete_parser.add_argument('filename', help='文件名')
    delete_parser.add_argument('-y', '--yes', action='store_true', help='跳过确认')
    delete_parser.set_defaults(func=cmd_delete)
    
    # Status command
    status_parser = subparsers.add_parser('status', help='检查后端状态')
    status_parser.set_defaults(func=cmd_status)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    args.func(args)


if __name__ == '__main__':
    main()
