"""
纯 Python 录制引擎 — Raw Socket + TCP Keepalive

参照 BililiveRecorder FillPipeAsync:
  - raw socket 连接, TCP keepalive 防止 CDN 断开
  - 持续读取, 在应用层切换分段文件
  - 滤除 mcdn 节点 (在 bilibili_api 中完成)
"""
from __future__ import annotations

import os
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

import file_logger as flog

FLV_HEADER = b'FLV\x01\x05\x00\x00\x00\x09'
PREV_TAG_SIZE = b'\x00\x00\x00\x00'


@dataclass
class RecordTask:
    task_id: str
    room_id: int
    platform: str
    stream_url: str
    output_dir: str
    title: str = ""
    uname: str = ""
    running: bool = False
    start_time: float = 0
    segment_start: float = 0
    total_bytes: int = 0
    segment_bytes: int = 0
    current_file: str = ""
    segment_index: int = 0
    error: str = ""
    segment_seconds: int = 1800
    max_retries: int = 50
    retry_delay: float = 5.0
    chunk_size: int = 131072
    stream_headers: dict = field(default_factory=dict)
    speed_window: list = field(default_factory=list)
    last_data_time: float = 0
    _flv_header: bytes | None = None
    _first_tags: bytearray = field(default_factory=bytearray)


class FFmpegRecorder:

    def __init__(self, ffmpeg_path=None, download_dir=None, lib_dir=None):
        self.download_dir = download_dir or "/sdcard/biliup"
        self._tasks: dict[str, RecordTask] = {}
        self._callbacks: dict[str, list[Callable]] = {}
        self._url_refresher: Callable | None = None
        os.makedirs(self.download_dir, exist_ok=True)

    def set_url_refresher(self, cb): self._url_refresher = cb
    def on_event(self, tid, cb): self._callbacks.setdefault(tid, []).append(cb)

    def _notify(self, tid, event, data=None):
        for cb in self._callbacks.get(tid, []):
            try: cb(tid, event, data or {})
            except Exception: pass

    def create_task(self, **kw) -> RecordTask:
        pdir = os.path.join(self.download_dir, kw["platform"], str(kw["room_id"]))
        os.makedirs(pdir, exist_ok=True)
        t = RecordTask(**kw, output_dir=pdir)
        self._tasks[kw["task_id"]] = t
        return t

    def start_recording(self, tid: str) -> bool:
        t = self._tasks.get(tid)
        if not t or t.running: return False
        t.running = True
        th = threading.Thread(target=self._download_loop, args=(t,), daemon=True)
        th.start()
        return True

    def _download_loop(self, task: RecordTask):
        try:
            retries = 0
            task.start_time = time.time()
            while task.running and retries < task.max_retries:
                if retries > 0 and self._url_refresher:
                    try:
                        new = self._url_refresher(task.room_id)
                        if new: task.stream_url = new
                    except Exception: pass
                try:
                    before = task.total_bytes
                    self._download_continuous(task)
                    if not task.running: break
                    if task.total_bytes > before:
                        retries = 0  # 收到数据就重置重试计数
                    else:
                        flog.warn("[%s] 0字节, 重试" % task.task_id)
                except Exception as e:
                    retries += 1
                    flog.warn("[%s] 断开 (%d/%d): %s" % (task.task_id, retries, task.max_retries, str(e)))
                    self._notify(task.task_id, "reconnecting", {"retry": retries, "max": task.max_retries})
                    # 收到过数据 → 短暂等待后重试；没收过数据 → 长等待
                    delay = task.retry_delay if task.total_bytes > 0 else task.retry_delay * 3
                    time.sleep(delay)
            if not task.running:
                self._notify(task.task_id, "stopped", {})
            elif retries >= task.max_retries:
                task.error = "重连失败(%d)" % task.max_retries
                self._notify(task.task_id, "error", {"error": task.error})
        except Exception as e:
            flog.error("[%s] 线程崩溃: %s" % (task.task_id, str(e)))
            task.error = "线程崩溃: %s" % str(e)
            self._notify(task.task_id, "error", {"error": task.error})
        finally:
            task.running = False

    def _download_continuous(self, task: RecordTask):
        """HTTP 持续下载 — urlopen 优先（Android socket 不稳定）"""
        self._download_urlopen(task)

    def _download_socket(self, task: RecordTask):
        parsed = urlparse(task.stream_url)
        host = parsed.hostname
        port = parsed.port or 443
        path = parsed.path + ("?" + parsed.query if parsed.query else "")

        hdr = [
            "GET %s HTTP/1.1" % path, "Host: %s" % host,
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept: */*", "Referer: https://live.bilibili.com/",
            "Origin: https://live.bilibili.com", "Accept-Encoding: identity",
        ]
        for k, v in task.stream_headers.items():
            hdr.append("%s: %s" % (k, v))
        hdr.append("")
        req = ("\r\n".join(hdr)).encode()

        try:
            sock = socket.create_connection((host, port), timeout=15)
        except Exception as e:
            raise Exception("TCP连接失败 %s:%s — %s" % (host, port, str(e)))

        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception: pass

        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE  # CDN IP主机名不匹配证书
            sock = ctx.wrap_socket(sock, server_hostname=host)
        except Exception as e:
            try: sock.close()
            except Exception: pass
            raise Exception("SSL握手失败 — %s" % str(e))

        try:
            sock.sendall(req)
            resp = b""
            while b"\r\n\r\n" not in resp:
                b = sock.recv(1)
                if not b: raise Exception("握手断开")
                resp += b
            status = resp[:resp.index(b"\r\n\r\n")].decode().split("\r\n")[0]
            flog.info("[%s] socket: %s" % (task.task_id, status))
            if "200" not in status:
                raise Exception("HTTP %s" % status.strip())

            sock.settimeout(30)  # 30s读超时（参照biliup）
            self._read_stream(task, sock)
        finally:
            try: sock.close()
            except Exception: pass

    def _download_urlopen(self, task: RecordTask):
        from urllib.request import Request, urlopen
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://live.bilibili.com/", "Origin": "https://live.bilibili.com",
            "Accept": "*/*", "Accept-Encoding": "identity",
        }
        headers.update(task.stream_headers)
        req = Request(task.stream_url, headers=headers)
        flog.info("[%s] 请求: %s" % (task.task_id, task.stream_url[:150]))
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        with urlopen(req, timeout=30, context=ctx) as resp:
            flog.info("[%s] 响应: status=%d" % (task.task_id, resp.status))
            self._read_stream(task, resp)

    def _read_stream(self, task: RecordTask, src):
        """一个 HTTP 连接 = 一个文件（参照 BililiveRecorder RawData）。不切分段，只在重连时建新文件。"""
        f = None
        try:
            task.segment_start = time.time()
            loop_count = 0

            while task.running:
                try:
                    chunk = src.read(task.chunk_size) if hasattr(src, 'read') else src.recv(task.chunk_size)
                except Exception as ex:
                    flog.debug("[%s] 读超时: %s" % (task.task_id, str(ex)))
                    continue
                if not chunk:
                    flog.info("[%s] 流结束" % task.task_id)
                    break

                loop_count += 1
                if loop_count == 1:
                    flog.info("[%s] 首块数据到达, size=%d" % (task.task_id, len(chunk)))
                elif loop_count % 50 == 0:
                    flog.debug("[%s] 已读%d块, %.1fMB" % (task.task_id, loop_count, task.total_bytes / 1048576))

                now = time.time()
                task.total_bytes += len(chunk)
                task.last_data_time = now
                task.speed_window.append((now, len(chunk)))
                cut = now - 15
                task.speed_window = [(t, b) for t, b in task.speed_window if t > cut]

                if f is None:
                    f = open(self._seg_path(task), 'wb')
                    # 写完整 FLV header + previous tag size 0
                    f.write(FLV_HEADER)
                    f.write(PREV_TAG_SIZE)
                    task.current_file = f.name
                    task.segment_index += 1
                    flog.info("[%s] 新文件: %s" % (task.task_id, f.name))
                    self._notify(task.task_id, "recording_start", {"file": f.name, "title": task.title})

                f.write(chunk)

            if f:
                f.close()
                self._notify(task.task_id, "segment_complete",
                             {"file": f.name, "size": os.path.getsize(f.name)})
        except Exception as e:
            flog.error("[%s] 读异常: %s" % (task.task_id, str(e)))
            if f:
                try: f.close()
                except Exception: pass

    def _seg_path(self, task):
        ts = time.strftime("%Y%m%d_%H%M%S")
        s = "".join(c for c in task.title if c.isalnum() or c in "._- ")[:50].strip()
        idx = task.segment_index
        if idx > 0:
            return os.path.join(task.output_dir, "%s_%s_%03d.flv" % (s, ts, idx))
        return os.path.join(task.output_dir, "%s_%s.flv" % (s, ts))

    def stop_recording(self, tid):
        t = self._tasks.get(tid)
        if t: t.running = False
        self._notify(tid, "stopped", {})

    def stop_all(self):
        for tid in list(self._tasks): self.stop_recording(tid)

    def get_task_status(self, tid: str) -> dict:
        t = self._tasks.get(tid)
        if not t: return {"error": "task not found"}
        now = time.time()
        td = now - t.start_time if t.running and t.start_time else 0
        sd = now - t.segment_start if t.running and t.segment_start else 0

        # 网速
        speed = 0
        if t.speed_window:
            total = sum(b for _, b in t.speed_window)
            span = max(1, now - t.speed_window[0][0])
            speed = total / span

        # 速度比 = 实际下载速度 / 流码率 (150KB/s典型B站蓝光)
        # 接近1.0表示实时跟上，<1.0表示落后
        expected = 150_000
        ratio = speed / expected if speed > 0 else 0

        def _fmt(d):
            h, m, s = int(d // 3600), int((d % 3600) // 60), int(d % 60)
            return "%02d:%02d:%02d" % (h, m, s)

        def _spd(bps):
            if bps < 1024: return "%d B/s" % int(bps)
            if bps < 1048576: return "%.1f KB/s" % (bps / 1024)
            return "%.1f MB/s" % (bps / 1048576)

        return {
            "task_id": t.task_id, "room_id": t.room_id,
            "platform": t.platform, "title": t.title, "uname": t.uname,
            "running": t.running,
            "duration": int(td), "duration_str": _fmt(td),
            "segment_duration": int(sd), "segment_str": _fmt(sd),
            "total_bytes": t.total_bytes,
            "total_mb": round(t.total_bytes / 1048576, 1),
            "speed_bytes": int(speed), "speed_str": _spd(speed),
            "speed_ratio": round(ratio, 2),
            "current_file": t.current_file, "error": t.error,
        }

    def get_all_status(self) -> list[dict]:
        return [self.get_task_status(tid) for tid in self._tasks]
