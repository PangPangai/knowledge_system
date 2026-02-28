#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Async Task Manager for Document Upload
Background task lifecycle management for long-running document ingestion.
"""

import asyncio
import io
import sys
import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Awaitable


class TaskStatus(str, Enum):
    """Upload task status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class _TeeWriter:
    """
    Stdout tee-writer: writes to both original stdout (server terminal)
    and a line buffer (for client-side log streaming).
    Thread-safe line splitting is handled internally.
    """

    def __init__(self, task: "UploadTask", original_stdout):
        self._task = task
        self._original = original_stdout
        self._buf = ""

    def write(self, text: str):
        self._original.write(text)  # Always mirror to server terminal
        self._buf += text
        # Flush complete lines to task.logs
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line:  # Skip blank lines
                self._task.logs.append(line)

    def flush(self):
        self._original.flush()
        # Flush any remaining partial line
        if self._buf.strip():
            self._task.logs.append(self._buf)
            self._buf = ""


@dataclass
class UploadTask:
    """Single upload task state"""
    task_id: str
    filename: str
    status: TaskStatus = TaskStatus.PENDING
    chunks_created: int = 0
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    processing_started_at: Optional[str] = None
    processing_duration: Optional[float] = None
    file_path: Optional[str] = None  # Temp file path for cleanup
    logs: List[str] = field(default_factory=list)  # Captured processing logs

    def to_dict(self) -> dict:
        """Serialize task to dict"""
        return {
            "task_id": self.task_id,
            "filename": self.filename,
            "status": self.status.value,
            "chunks_created": self.chunks_created,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "processing_duration": self.processing_duration,
            "logs": self.logs,
        }


class TaskManager:
    """Manage async background upload tasks"""

    def __init__(self):
        self._tasks: Dict[str, UploadTask] = {}
        self._async_handles: Dict[str, asyncio.Task] = {}

    def submit(
        self,
        filename: str,
        file_path: str,
        ingest_fn: Callable[[str, str], Awaitable[int]],
    ) -> str:
        """
        Submit a new upload task for background processing.

        Args:
            filename: Original document filename
            file_path: Path to the saved temp file
            ingest_fn: Async callable(file_path, filename) -> chunks_created

        Returns:
            task_id for status polling
        """
        task_id = uuid.uuid4().hex[:12]
        task = UploadTask(task_id=task_id, filename=filename, file_path=file_path)
        self._tasks[task_id] = task

        # Schedule background coroutine
        handle = asyncio.create_task(self._run(task, ingest_fn))
        self._async_handles[task_id] = handle
        return task_id

    async def _run(
        self,
        task: UploadTask,
        ingest_fn: Callable[[str, str], Awaitable[int]],
    ):
        """Execute ingestion in a thread pool to avoid blocking event loop"""
        import os

        task.status = TaskStatus.PROCESSING
        task.processing_started_at = datetime.now().isoformat()
        start_time = datetime.now()

        print(f"\n{'='*60}")
        print(f"📥 [Task {task.task_id}] Starting: {task.filename}")
        print(f"{'='*60}")

        def run_in_thread():
            """
            Run ingest_fn in a worker thread, capturing stdout via TeeWriter
            so logs appear in both server terminal and task.logs for client polling.
            """
            original_stdout = sys.stdout
            tee = _TeeWriter(task, original_stdout)
            sys.stdout = tee
            try:
                return asyncio.run(ingest_fn(task.file_path, task.filename))
            finally:
                sys.stdout = original_stdout
                tee.flush()  # Flush any remaining partial line

        try:
            loop = asyncio.get_running_loop()
            chunks = await loop.run_in_executor(None, run_in_thread)
            task.chunks_created = chunks
            task.status = TaskStatus.COMPLETED
            duration = (datetime.now() - start_time).total_seconds()
            print(f"\n✅ [Task {task.task_id}] Completed: {task.filename}")
            print(f"   Chunks: {chunks}  |  Duration: {duration:.1f}s")
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            duration = (datetime.now() - start_time).total_seconds()
            print(f"\n❌ [Task {task.task_id}] Failed: {task.filename}")
            print(f"   Error: {e}  |  Duration: {duration:.1f}s")
        finally:
            end_time = datetime.now()
            task.completed_at = end_time.isoformat()
            task.processing_duration = (end_time - start_time).total_seconds()
            # Cleanup temp file
            if task.file_path and os.path.exists(task.file_path):
                try:
                    os.remove(task.file_path)
                    print(f"   🗑️  Temp file removed: {task.file_path}")
                except OSError:
                    pass

    def get_status(self, task_id: str) -> Optional[dict]:
        """Get task status by id, returns None if not found"""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        return task.to_dict()

    def list_tasks(self) -> list:
        """List all tasks, newest first"""
        tasks = sorted(
            self._tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )
        return [t.to_dict() for t in tasks]
