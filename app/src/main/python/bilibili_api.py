"""
B站 API 客户端 — 逐行参照 biliup 源码

参照文件:
  crates/biliup/src/downloader/live/bilibili.rs
  crates/biliup/src/downloader/live/wbi.rs
  crates/biliup/src/uploader/bilibili.rs

API 调用链:
  getInfoByRoom → room_info.live_status → 如果=1 → getRoomPlayInfo → 获取流地址
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.cookiejar import CookieJar

# ─── 常量 (bilibili.rs:17-20) ───────────────────────────────

BILIBILI_LIVE_API = "https://api.live.bilibili.com"
BILIBILI_REFERER = "https://live.bilibili.com"
BILIBILI_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
WBI_WEB_LOCATION = "444.8"  # bilibili.rs:20

# WBI KEY_MAP (wbi.rs:12-14)
_KEY_MAP = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


# ─── WBI 签名 (wbi.rs:34-138) ────────────────────────────────

class WbiSigner:
    """B站 WBI 签名器 (wbi.rs:34-138)"""

    def __init__(self):
        self._key: str | None = None
        self._last_update: int = 0

    @staticmethod
    def _extract_key(url: str) -> str:
        """wbi.rs:49-53"""
        return url.rsplit("/", 1)[-1].split(".")[0]

    @staticmethod
    def _create_mixin_key(img: str, sub: str) -> str:
        """wbi.rs:56-63"""
        full = img + sub
        return "".join(full[i] for i in _KEY_MAP[:32] if i < len(full))

    def update_key(self, opener) -> bool:
        """wbi.rs:65-98"""
        now = int(time.time())
        if now - self._last_update < 7200 and self._key:
            return True

        try:
            req = urllib.request.Request(
                "https://api.bilibili.com/x/web-interface/nav",
                headers={
                    "User-Agent": BILIBILI_USER_AGENT,
                    "Referer": "https://www.bilibili.com/",
                },
            )
            with opener.open(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            wbi = data.get("data", {}).get("wbi_img", {})
            img_url = wbi.get("img_url", "")
            sub_url = wbi.get("sub_url", "")

            if img_url and sub_url:
                self._key = self._create_mixin_key(
                    self._extract_key(img_url),
                    self._extract_key(sub_url),
                )
                self._last_update = now
                return True
        except Exception:
            pass
        return False

    def sign(self, params: dict) -> dict:
        """wbi.rs:100-138"""
        if not self._key:
            return dict(params)

        p = dict(params)
        p["wts"] = str(int(time.time()))

        # 过滤特殊字符后排序拼接
        sanitized = {k: re.sub(r"[!'()*]", "", str(v)) for k, v in p.items()}
        sorted_items = sorted(sanitized.items(), key=lambda x: x[0])
        query = "&".join(
            "%s=%s" % (urllib.parse.quote(k, safe=""), urllib.parse.quote(v, safe=""))
            for k, v in sorted_items
        )
        p["w_rid"] = hashlib.md5((query + self._key).encode()).hexdigest()
        return p


# ─── 数据模型 ────────────────────────────────────────────────

@dataclass
class RoomInfo:
    room_id: int = 0
    short_id: int = 0
    uid: int = 0
    title: str = ""
    cover: str = ""
    uname: str = ""
    face_url: str = ""
    live_status: int = 0
    online: int = 0
    candidates: list = field(default_factory=list)
    error: str = ""


@dataclass
class LoginState:
    logged_in: bool = False
    qr_key: str = ""
    qr_url: str = ""
    uid: int = 0
    uname: str = ""
    cookies: dict = field(default_factory=dict)


# ─── B站 API 客户端 ──────────────────────────────────────────

class BilibiliAPI:
    """B站 API 客户端 — 参照 bilibili.rs:56-601"""

    def __init__(self, cookie_str: str = None):
        self._cookie_jar = CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar),
            urllib.request.HTTPSHandler(),
        )
        self._wbi = WbiSigner()
        self.login = LoginState()
        self._timeout = 30
        if cookie_str:
            self.load_cookies(cookie_str)

    # ─── HTTP (参照 bilibili.rs client usage) ────────────────

    def _get_json_no_cookies(self, url: str, params: dict = None,
                              headers: dict = None) -> dict:
        """HTTP GET → JSON（不带任何 Cookie）"""
        if params:
            qs = urllib.parse.urlencode(params)
            url = "%s?%s" % (url, qs)
        hdrs = _make_headers()
        if headers:
            hdrs.update(headers)
        # 不添加 Cookie
        req = urllib.request.Request(url, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return {"code": e.code, "message": e.read().decode("utf-8", errors="replace")[:500]}
        except Exception as e:
            return {"code": -1, "message": str(e)}

    def _get_json(self, url: str, params: dict = None,
                  headers: dict = None) -> dict:
        """HTTP GET → JSON"""
        if params:
            qs = urllib.parse.urlencode(params)
            url = "%s?%s" % (url, qs)

        hdrs = _make_headers()
        if headers:
            hdrs.update(headers)
        _add_cookie(hdrs, self.login.cookies)

        req = urllib.request.Request(url, headers=hdrs)
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return {"code": e.code, "message": body[:500]}
        except Exception as e:
            return {"code": -1, "message": str(e)}

    # ─── 直播间 (bilibili.rs:209-280) ────────────────────────

    def get_room_info(self, room_id: int, qn: int = 10000) -> RoomInfo:
        """
        获取直播间信息
        参照 bilibili.rs:209-280 get_room_info()
        调用: GET /xlive/web-room/v1/index/getInfoByRoom
        """
        info = RoomInfo(room_id=room_id)

        # Step 1: 用 getInfoByRoom 获取房间信息 (bilibili.rs:214-231)
        params = {"room_id": str(room_id), "web_location": WBI_WEB_LOCATION}

        # WBI 签名 (bilibili.rs:217)
        if self._wbi.update_key(self._opener):
            params = self._wbi.sign(params)

        data = self._get_json(
            "%s/xlive/web-room/v1/index/getInfoByRoom" % BILIBILI_LIVE_API,
            params=params,
        )

        if data.get("code") != 0:
            info.error = "API返回 code=%s msg=%s" % (
                data.get("code"), data.get("message", ""))
            # 回退：旧版 API (room_init + get_info)
            return self._get_room_info_v1(room_id, info)

        # bilibili.rs:244-279
        room_data = data.get("data", {})
        room = room_data.get("room_info", {})
        anchor = room_data.get("anchor_info", {})

        live_status = room.get("live_status", 0)
        info.live_status = live_status
        info.title = room.get("title", "") or ""
        info.cover = room.get("cover", "") or ""
        info.uid = room.get("uid", 0)
        info.room_id = room.get("room_id", room_id)
        info.live_start_time = room.get("live_start_time", 0)
        info.online = room.get("online", 0)
        info.uname = (anchor.get("base_info") or {}).get("uname", "") or ""

        # 如果正在直播，获取流地址 (bilibili.rs:282-306)
        if live_status == 1:
            candidates = self._get_stream_url(info.room_id, qn)
            info.candidates = candidates

        return info

    def _get_room_info_v1(self, room_id: int, info: RoomInfo) -> RoomInfo:
        """回退到旧版 API"""
        try:
            # room_init 获取真实 room_id
            data = self._get_json(
                "%s/room/v1/Room/room_init" % BILIBILI_LIVE_API,
                params={"id": room_id},
            )
            if data.get("code") == 0:
                real_id = data["data"]["room_id"]
                info.room_id = real_id
                info.uid = data["data"].get("uid", 0)

                # get_info 获取详细信息
                data2 = self._get_json(
                    "%s/room/v1/Room/get_info" % BILIBILI_LIVE_API,
                    params={"room_id": real_id},
                )
                if data2.get("code") == 0:
                    room = data2["data"].get("room_info", {}) or data2["data"]
                    anchor = data2["data"].get("anchor_info", {})
                    info.live_status = room.get("live_status", 0)
                    info.title = room.get("title", "") or ""
                    info.cover = room.get("cover", "") or ""
                    info.uname = (anchor.get("base_info") or {}).get("uname", "") or ""
                    info.face_url = (anchor.get("base_info") or {}).get("face", "") or ""
                    info.error = ""  # 成功

                    if info.live_status == 1:
                        urls = self._get_stream_url_v1(real_id)
                        info.candidates = urls
        except Exception as e:
            info.error = "v1回退也失败: %s" % e
        return info

    def _get_stream_url(self, room_id: int, qn: int = 10000) -> list[dict]:
        """
        获取直播流 (bilibili.rs:308-408)
        调用: GET /xlive/web-room/v2/index/getRoomPlayInfo
        """
        params = {
            "room_id": str(room_id),
            "qn": "10000",
            "platform": "html5",
            "protocol": "0,1",
            "format": "0,1,2",
            "codec": "0",
            "dolby": "5",
            "web_location": WBI_WEB_LOCATION,
        }
        if self._wbi._key:
            params = self._wbi.sign(params)

        data = self._get_json(
            "%s/xlive/web-room/v2/index/getRoomPlayInfo" % BILIBILI_LIVE_API,
            params=params,
        )

        candidates = []
        try:
            playurl = data["data"]["playurl_info"]["playurl"]
            for stream in playurl.get("stream", []):
                for fmt in stream.get("format", []):
                    for codec in fmt.get("codec", []):
                        base_url = codec.get("base_url", "")
                        qn = codec.get("current_qn", 0)
                        all_candidates = []
                        for u in codec.get("url_info", []):
                            host = u.get("host", "")
                            url = "%s%s%s" % (host, base_url, u.get("extra", ""))
                            m = re.search(r"[?&]cdn=([^&]+)", u.get("extra", ""))
                            all_candidates.append({
                                "qn": qn, "cdn": m.group(1) if m else "",
                                "url": url, "host": host,
                            })
                        # 优先非 mcdn，但全 mcdn 则全保留
                        non_mcdn = [c for c in all_candidates if ".mcdn." not in c["host"]]
                        candidates.extend(non_mcdn if non_mcdn else all_candidates)
        except Exception:
            pass
        return candidates

    def _get_stream_url_v1(self, room_id: int) -> list[dict]:
        """旧版流地址 (bilibili.rs 中的回退)"""
        candidates = []
        try:
            data = self._get_json(
                "%s/room/v1/Room/playUrl" % BILIBILI_LIVE_API,
                params={"cid": room_id, "platform": "web", "qn": 10000,
                        "https_url_req": 1},
            )
            if data.get("code") == 0:
                for item in data["data"].get("durl", []):
                    url = item.get("url", "")
                    if url:
                        candidates.append({"qn": 10000, "cdn": "", "url": url})
        except Exception:
            pass
        return candidates

    def get_stream_urls(self, room_id: int, qn: int = 10000) -> list[str]:
        info = self.get_room_info(room_id)
        return [c["url"] for c in info.candidates]

    def get_play_url(self, room_id: int, qn: int = 10000) -> list[str]:
        return self.get_stream_urls(room_id, qn)

    def check_live(self, room_id: int) -> bool:
        return self.get_room_info(room_id).live_status == 1

    # ─── 扫码登录 ────────────────────────────────────────────

    def generate_qr(self) -> dict:
        try:
            data = self._get_json(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
            )
            if data.get("code") == 0:
                qr = data["data"]
                self.login.qr_key = qr["qrcode_key"]
                self.login.qr_url = qr["url"]
                return {"success": True, "url": qr["url"], "qrcode_key": qr["qrcode_key"]}
            return {"success": False, "message": str(data.get("message", ""))}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def poll_qr(self) -> dict:
        if not self.login.qr_key:
            return {"status": "error", "message": "未生成二维码"}
        try:
            url = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
            qs = urllib.parse.urlencode({"qrcode_key": self.login.qr_key})
            url = "%s?%s" % (url, qs)
            hdrs = _make_headers()
            # 不带 Cookie 的请求
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                set_cookies = resp.headers.get_all("Set-Cookie") or []
                body = resp.read().decode("utf-8")
                # 紧急调试：完整原始响应
                import file_logger as _fl
                _fl.info("QR_POLL_RAW status=%d headers=%s body=%s" % (
                    resp.status, dict(resp.headers), body[:500]))
                data = json.loads(body)
            # B站 API 新格式: 外层code=HTTP状态, data.code=QR状态
            inner = data.get("data") or {}
            code = inner.get("code", data.get("code"))
            if code == 0:
                # 从响应头提取 cookies
                cookie_pairs = {}
                for sc in set_cookies:
                    parts = sc.split(";")[0].strip().split("=", 1)
                    if len(parts) == 2:
                        cookie_pairs[parts[0]] = parts[1]
                if cookie_pairs:
                    self.login.cookies = cookie_pairs
                    self.login.logged_in = True
                    # 获取用户信息
                    try:
                        nav = self._get_json("https://api.bilibili.com/x/web-interface/nav")
                        if nav.get("code") == 0:
                            self.login.uid = nav["data"].get("mid", 0)
                            self.login.uname = nav["data"].get("uname", "")
                    except Exception: pass
                return {"status": "success", "message": "登录成功",
                        "uid": self.login.uid, "uname": self.login.uname}
            msgs = {86038: "expired", 86090: "scanned", 86101: "waiting"}
            status = msgs.get(code, "error")
            msg = {86038: "二维码已过期", 86090: "已扫码", 86101: "等待扫码"}.get(
                code, data.get("message", "code=%s" % code))
            return {"status": status, "message": msg, "uid": 0, "uname": ""}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _extract_cookies(self):
        cookies = {}
        for c in self._cookie_jar:
            cookies[c.name] = c.value
        self.login.cookies = cookies
        self.login.logged_in = bool(cookies.get("SESSDATA"))
        if self.login.logged_in:
            try:
                data = self._get_json("https://api.bilibili.com/x/web-interface/nav")
                if data.get("code") == 0:
                    self.login.uid = data["data"].get("mid", 0)
                    self.login.uname = data["data"].get("uname", "")
            except Exception:
                pass

    def clear_cookies(self):
        """清空所有 Cookie（用于重新登录）"""
        self._cookie_jar.clear()
        self.login = LoginState()

    def load_cookies(self, s: str):
        for item in s.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                self.login.cookies[k.strip()] = v.strip()
        self.login.logged_in = bool(self.login.cookies.get("SESSDATA"))

    def get_cookies_str(self) -> str:
        return "; ".join("%s=%s" % it for it in self.login.cookies.items())


# ─── helpers ─────────────────────────────────────────────────

def _make_headers() -> dict:
    """bilibili.rs:169-181 headers()"""
    return {
        "User-Agent": BILIBILI_USER_AGENT,
        "Referer": BILIBILI_REFERER,
    }


def _add_cookie(hdrs: dict, cookies: dict):
    """bilibili.rs:183-207 cookie()"""
    if cookies:
        hdrs["Cookie"] = "; ".join(
            "%s=%s" % (k, v) for k, v in cookies.items()
        )
