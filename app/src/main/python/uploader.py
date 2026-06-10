from __future__ import annotations
"""
B站视频上传引擎 — 纯标准库 (urllib)
参照 biliup 源码 (crates/biliup/src/uploader/bilibili.rs)
"""

import hashlib
import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class UploadTask:
    task_id: str
    file_path: str
    platform: str
    title: str
    desc: str = ""
    tags: list = None
    progress: float = 0.0
    speed: float = 0.0
    status: str = "pending"
    error: str = ""


class BilibiliUploader:
    CHUNK_SIZE = 4 * 1024 * 1024  # 4MB

    def __init__(self, cookies: dict):
        self.cookies = cookies
        self._callbacks: dict[str, list[Callable]] = {}

    def on_progress(self, task_id: str, callback: Callable):
        if task_id not in self._callbacks:
            self._callbacks[task_id] = []
        self._callbacks[task_id].append(callback)

    def _notify(self, task_id: str, progress: float, speed: float, status: str):
        for cb in self._callbacks.get(task_id, []):
            try:
                cb(task_id, progress, speed, status)
            except Exception:
                pass

    def _request(self, url: str, data: bytes = None, headers: dict = None,
                 method: str = "GET") -> dict:
        hdrs = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://member.bilibili.com/",
        }
        cookie_str = "; ".join("%s=%s" % (k, v) for k, v in self.cookies.items())
        if cookie_str:
            hdrs["Cookie"] = cookie_str
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        with urllib.request.urlopen(req, timeout=3600) as resp:
            return json.loads(resp.read().decode())

    def upload(self, task: UploadTask) -> dict:
        if not os.path.exists(task.file_path):
            return {"success": False, "message": "文件不存在"}

        task.status = "uploading"
        file_size = os.path.getsize(task.file_path)
        filename = os.path.basename(task.file_path)

        try:
            # Step 1: 预上传
            pre_upload_url = "https://member.bilibili.com/preupload"
            params = "name=%s&size=%d&r=upos&profile=ugcupos/bup&ssl=1&version=2.0" % (
                urllib.request.quote(filename), file_size
            )
            data = self._request("%s?%s" % (pre_upload_url, params))

            if not data.get("OK") and not data.get("ok"):
                task.status = "failed"
                task.error = "预上传失败: %s" % data
                return {"success": False, "message": task.error}

            upload_url = data.get("url") or data.get("bili_url")
            complete_url = data.get("complete_url", "")
            if not upload_url:
                task.status = "failed"
                task.error = "预上传未返回URL"
                return {"success": False, "message": task.error}

            # Step 2: 分片上传
            chunks_count = (file_size + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE
            start_time = time.time()
            bytes_uploaded = 0

            with open(task.file_path, "rb") as f:
                for i in range(chunks_count):
                    chunk = f.read(self.CHUNK_SIZE)
                    start = i * self.CHUNK_SIZE
                    end = min(start + len(chunk) - 1, file_size - 1)

                    hdrs = {
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": "bytes %d-%d/%d" % (start, end, file_size),
                    }

                    for retry in range(3):
                        try:
                            self._request(upload_url, data=chunk, headers=hdrs, method="PUT")
                            break
                        except Exception as e:
                            if retry == 2:
                                raise e
                            time.sleep(2)

                    bytes_uploaded += len(chunk)
                    elapsed = time.time() - start_time
                    task.progress = bytes_uploaded / file_size
                    task.speed = bytes_uploaded / elapsed if elapsed > 0 else 0
                    self._notify(task.task_id, task.progress, task.speed, "uploading")

            # Step 3: 提交
            csrf = self.cookies.get("bili_jct", "")
            tags = ",".join(task.tags) if task.tags else "直播录像"
            submit_data = {
                "title": task.title,
                "tid": "138",
                "tag": tags,
                "desc": task.desc or "录播 by biliup-android",
                "copyright": "2",
                "videos": json.dumps([{"title": task.title, "desc": "", "filename": filename}]),
                "csrf": csrf,
            }
            result = self._request(
                "https://member.bilibili.com/x/vu/web/add/v3?csrf=%s" % csrf,
                data=urllib.parse.urlencode(submit_data).encode(),
            )

            if result.get("code") == 0:
                task.status = "done"
                task.progress = 1.0
                self._notify(task.task_id, 1.0, 0, "done")
                return {"success": True, "aid": result.get("data", {}).get("aid")}
            else:
                task.status = "failed"
                task.error = "投稿提交失败: %s" % result.get("message", "")
                return {"success": False, "message": task.error}

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            return {"success": False, "message": str(e)}


def create_uploader(platform: str, cookies: dict):
    if platform == "bilibili":
        return BilibiliUploader(cookies)
    raise ValueError("不支持的上传平台: %s" % platform)


def upload_video_sync(uploader, task_id: str, file_path: str, title: str,
                      platform: str = "bilibili", desc: str = "",
                      tags: list = None) -> dict:
    task = UploadTask(
        task_id=task_id, file_path=file_path, platform=platform,
        title=title, desc=desc, tags=tags or [],
    )
    return uploader.upload(task)
