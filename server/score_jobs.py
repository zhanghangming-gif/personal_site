"""Bounded score job queue with atomic, persistent public status snapshots."""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor


class QueueFull(RuntimeError):
    pass


class ScoreJobs:
    def __init__(self, root, worker, capacity=5):
        self.root = root
        self.worker = worker
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(capacity)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.active = set()

    def path(self, job_id):
        return os.path.join(self.root, job_id, "job-status.json")

    def write(self, job_id, data):
        with self.lock:
            path = self.path(job_id)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            value = dict(data, jobId=job_id, updatedAt=time.time())
            temp = path + ".tmp"
            with open(temp, "w", encoding="utf8") as stream:
                json.dump(value, stream, ensure_ascii=False)
            os.replace(temp, path)
            return value

    def read(self, job_id):
        with self.lock:
            try:
                with open(self.path(job_id), encoding="utf8") as stream:
                    result = json.load(stream)
            except (OSError, ValueError):
                return None
            if result.get("status") in ("queued", "processing") and job_id not in self.active:
                result = self.write(job_id, {
                    "status": "failed", "stage": "failed", "progress": 0,
                    "message": "服务已重启，请重新提交乐谱", "outputAllowed": False,
                    "pipelineStatus": "REJECTED", "warnings": [],
                })
            return result

    def submit(self, job_id, request):
        if not self.slots.acquire(False):
            raise QueueFull("当前处理队列已满，请稍后再试")
        try:
            with self.lock:
                self.active.add(job_id)
                initial = self.write(job_id, {
                    "status": "queued", "stage": "queued", "progress": 4,
                    "message": "已接收 PDF，等待处理", "outputAllowed": False,
                    "pipelineStatus": "PROCESSING", "warnings": [],
                })
                self.executor.submit(self._run, job_id, request)
            return initial
        except Exception:
            self.active.discard(job_id)
            self.slots.release()
            raise

    def _run(self, job_id, request):
        def progress(stage, message, percent):
            self.write(job_id, {"status": "processing", "stage": stage, "message": message,
                                "progress": percent, "outputAllowed": False,
                                "pipelineStatus": "PROCESSING", "warnings": []})
        try:
            result = self.worker(job_id, request, progress)
            self.write(job_id, result)
        except Exception:
            import logging
            logging.exception("score job failed: %s", job_id)
            self.write(job_id, {"status": "failed", "stage": "failed", "message": "乐谱处理失败，请稍后重试",
                                "progress": 0, "outputAllowed": False, "pipelineStatus": "REJECTED", "warnings": []})
        finally:
            with self.lock:
                self.active.discard(job_id)
            self.slots.release()
