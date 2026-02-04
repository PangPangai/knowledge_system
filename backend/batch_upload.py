#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Batch Upload Script
批量上传脚本 - 批量导入指定目录的所有 PDF 文件
"""

import os
import sys
from pathlib import Path
from admin_cli import KnowledgeBaseAdmin, API_BASE_URL


def batch_upload(directory: str, api_base: str = API_BASE_URL):
    """
    Batch upload all PDF files from a directory
    
    Args:
        directory: Directory path containing PDF files
        api_base: API base URL
    """
    admin = KnowledgeBaseAdmin(api_base)
    
    # Check backend health
    if not admin.check_health():
        print(f"❌ 错误: 后端服务未启动! ({api_base})")
        sys.exit(1)
    
    all_files = []
    
    print(f"📂 扫描目录: {directory}")
    print(f"⚠️ 注意: 如果路径过长(>260字符), 可能会被跳过.")
    
    # Use os.walk which is more robust than glob for long paths and permission errors
    for root, dirs, files in os.walk(directory):
        for file in files:
            try:
                # Check extension
                if file.lower().endswith(('.pdf', '.md', '.markdown')):
                    full_path = Path(root) / file
                    all_files.append(full_path)
            except Exception as e:
                print(f"⚠️ 跳过无法访问的文件: {file} ({e})")
                continue
    
    if not all_files:
        print(f"📭 未找到文档文件: {directory}")
        return
    
    pdf_count = len([f for f in all_files if f.suffix.lower() == '.pdf'])
    md_count = len([f for f in all_files if f.suffix.lower() in ['.md', '.markdown']])
    print(f"📚 找到 {len(all_files)} 个文档文件 (PDF: {pdf_count}, Markdown: {md_count})\n")
    
    # Get existing documents for incremental update
    try:
        remote_docs = admin.list_documents()
        existing_files = {doc.get('filename') for doc in remote_docs if doc.get('filename')}
        print(f"🔄 知识库已有 {len(existing_files)} 个文档，将跳过重复文件。\n")
    except Exception as e:
        print(f"⚠️ 无法获取现有文档列表，将尝试上传所有文件: {e}\n")
        existing_files = set()

    # Upload each file
    success_count = 0
    skipped_count = 0
    failed_files = []
    
    for idx, file_path in enumerate(all_files, 1):
        if file_path.name in existing_files:
            print(f"[{idx}/{len(all_files)}] ⏭️ 跳过 (已存在): {file_path.name}")
            skipped_count += 1
            continue

        print(f"[{idx}/{len(all_files)}] 上传中: {file_path.name}")
        
        try:
            result = admin.upload_document(str(file_path))
            print(f"  ✅ 成功 (片段数: {result['chunks_created']})\n")
            success_count += 1
        except Exception as e:
            print(f"  ❌ 失败: {e}\n")
            failed_files.append(file_path.name)
    
    # Summary
    print("=" * 50)
    print(f"📊 上传完成:")
    print(f"  ✅ 成功: {success_count}")
    print(f"  ⏭️ 跳过: {skipped_count}")
    print(f"  ❌ 失败: {len(failed_files)}")
    
    if failed_files:
        print(f"  ❌ 失败: {len(failed_files)}")
        print("\n失败文件列表:")
        for filename in failed_files:
            print(f"  - {filename}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Batch Upload PDFs - 批量上传 PDF 文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 上传指定目录下的所有 PDF
  python batch_upload.py /path/to/pdfs
  
  # 递归上传子目录中的 PDF
  python batch_upload.py /path/to/pdfs --recursive
        """
    )
    
    parser.add_argument(
        'directory',
        help='包含 PDF 文件的目录路径'
    )
    
    parser.add_argument(
        '--api',
        default=API_BASE_URL,
        help=f'API 地址 (默认: {API_BASE_URL})'
    )
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.directory):
        print(f"❌ 错误: 目录不存在: {args.directory}")
        sys.exit(1)
    
    batch_upload(args.directory, args.api)


if __name__ == '__main__':
    main()
