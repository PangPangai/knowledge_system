#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Async Task Manager for Document Upload
Background task lifecycle management for long-running document ingestion.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Optional, Awaitable


class TaskStatus(str, Enum):
    """Upload task status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


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

    def to_dict(self) -> dict:
        """Serialize task to dict"""
        return {
            "task_id": self.task_id,
            "filename": self.filename,
            "status": self.status.value,
            "chunks_created": self.chunks_created,
            "error": self.error,
            "created_at": self.created_at,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "processing_duration": self.processing_duration,
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
        try:
            # Run in thread pool: ingest_fn is async but internally CPU-bound,
            # calling it directly would block the event loop and prevent
            # FastAPI from handling other requests (e.g. next file upload).
            loop = asyncio.get_running_loop()
            chunks = await loop.run_in_executor(
                None,
                lambda: asyncio.run(ingest_fn(task.file_path, task.filename)),
            )
            task.chunks_created = chunks
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
        finally:
            end_time = datetime.now()
            task.completed_at = end_time.isoformat()
            task.processing_duration = (end_time - start_time).total_seconds()
            # Cleanup temp file
            if task.file_path and os.path.exists(task.file_path):
                try:
                    os.remove(task.file_path)
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
