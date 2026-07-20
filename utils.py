"""安全工具：URL 校验、数值规范、HTML 转义、错误脱敏、TTL 缓存。"""

from __future__ import annotations

import html
import math
import time
from collections import OrderedDict
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

# ---------- 数值规范 ----------

def safe_int(value: Any, default: int = 0, minimum: Optional[int] = None,
             maximum: Optional[int] = None) -> int:
    """安全转 int；拒绝 NaN/Infinity/异常字符串。"""
    if value is None:
        return default
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int,)):
            n = value
        elif isinstance(value, float):
            if not math.isfinite(value):
                return default
            n = int(value)
        else:
            # 字符串：先 float 再 int，兼容 "1.0"
            s = str(value).strip()
            if not s:
                return default
            f = float(s)
            if not math.isfinite(f):
                return default
            n = int(f)
    except (TypeError, ValueError, OverflowError):
        return default
    if minimum is not None and n < minimum:
        n = minimum
    if maximum is not None and n > maximum:
        n = maximum
    return n


def safe_float(value: Any, default: float = 0.0, minimum: Optional[float] = None,
               maximum: Optional[float] = None) -> float:
    """安全转 float；拒绝 NaN/Infinity。"""
    if value is None:
        return default
    try:
        if isinstance(value, bool):
            f = float(value)
        elif isinstance(value, (int, float)):
            f = float(value)
        else:
            s = str(value).strip()
            if not s:
                return default
            f = float(s)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(f):
        return default
    if minimum is not None and f < minimum:
        f = minimum
    if maximum is not None and f > maximum:
        f = maximum
    return f


# ---------- URL 校验 ----------

# 内网/本机主机名（不含端口）。用于默认拒绝场景。
_LOOPBACK_HOSTS = {"localhost", "ip6-localhost", "ip6-loopback"}
_LINK_LOCAL_PREFIXES = ("169.254.", "fe80:", "fc00:", "fd", "ff00:")


def _is_private_host(hostname: str) -> bool:
    h = (hostname or "").lower().rstrip(".")
    if not h:
        return True
    if h in _LOOPBACK_HOSTS:
        return True
    if h.endswith(".local") or h.endswith(".internal"):
        return True
    if h.startswith("127."):
        return True
    if h.startswith("10.") or h.startswith("192.168.") or h.startswith("0."):
        return True
    if h.startswith("172."):
        parts = h.split(".")
        if len(parts) >= 2:
            try:
                second = int(parts[1])
                if 16 <= second <= 31:
                    return True
            except ValueError:
                pass
    if any(h.startswith(p) for p in _LINK_LOCAL_PREFIXES):
        return True
    return False


def validate_url(
    url: str,
    *,
    allow_schemes: tuple[str, ...] = ("http", "https"),
    require_https_when_auth: bool = True,
    has_auth: bool = False,
    allow_private: bool = True,
    allow_userinfo: bool = False,
) -> str:
    """校验并规范化 URL；不合法抛 ValueError。

    - allow_schemes：允许的协议
    - require_https_when_auth：带 api_key 时强制 https
    - has_auth：是否携带鉴权（决定是否强制 https）
    - allow_private：是否允许内网/本机地址
    - allow_userinfo：是否允许 URL userinfo（user:pass@）
    """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("URL 为空")
    if len(raw) > 2048:
        raise ValueError("URL 过长")

    try:
        parsed = urlparse(raw)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"URL 解析失败: {e}") from e

    scheme = (parsed.scheme or "").lower()
    if scheme not in allow_schemes:
        raise ValueError(f"不支持的协议: {scheme or '(空)'}")

    if require_https_when_auth and has_auth and scheme != "https":
        raise ValueError("携带 API Key 时必须使用 HTTPS")

    if not allow_userinfo and (parsed.username or parsed.password):
        raise ValueError("URL 不允许包含用户名/密码")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("URL 缺少主机名")

    if not allow_private and _is_private_host(hostname):
        raise ValueError(f"不允许的内网/本机地址: {hostname}")

    # 端口范围校验
    port = parsed.port
    if port is not None and not (1 <= port <= 65535):
        raise ValueError(f"端口超出范围: {port}")

    # 重建 URL，避免携带 fragment；保留 query/path
    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{parsed.hostname}:{parsed.port}"
    if parsed.username or parsed.password:
        # 仅 allow_userinfo=True 时会到这里
        userinfo = parsed.username or ""
        if parsed.password:
            userinfo = f"{userinfo}:{parsed.password}"
        netloc = f"{userinfo}@{netloc}"
    cleaned = urlunparse((
        scheme,
        netloc,
        parsed.path or "",
        "",
        parsed.query or "",
        "",
    ))
    return cleaned


def is_safe_bg_url(url: str) -> tuple[bool, str]:
    """校验背景图地址：必须 https，无 userinfo，非内网。"""
    try:
        cleaned = validate_url(
            url,
            allow_schemes=("https",),
            require_https_when_auth=False,
            has_auth=False,
            allow_private=False,
            allow_userinfo=False,
        )
        return True, cleaned
    except ValueError as e:
        return False, str(e)


# ---------- HTML 转义 ----------

def esc(value: Any, max_len: int = 200) -> str:
    """HTML 转义字符串并限制长度，用于模板渲染前。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    s = str(value)
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return html.escape(s, quote=True)


# ---------- 错误脱敏 ----------

_SENSITIVE_KEYS = ("authorization", "api_key", "apikey", "token", "password",
                   "secret", "cookie", "set-cookie")


def sanitize_for_log(text: str, max_len: int = 500) -> str:
    """清理日志中的敏感字段，限制长度。"""
    if text is None:
        return ""
    s = str(text)
    # 屏蔽 Bearer xxx
    s = _redact_bearer(s)
    # 屏蔽 ?api_key=xxx / &token=xxx
    s = _redact_query(s)
    if len(s) > max_len:
        s = s[:max_len] + "…"
    return s


def _redact_bearer(s: str) -> str:
    import re
    return re.sub(
        r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[A-Za-z0-9_\-.:=]+",
        r"\1***",
        s,
    )


def _redact_query(s: str) -> str:
    import re
    return re.sub(
        r"(?i)([?&](?:api_key|apikey|token|access_token|secret|password)=)[^&\s]+",
        r"\1***",
        s,
    )


# ---------- TTL + 容量受限缓存 ----------

class TTLCache:
    """简单的 TTL + 最大容量缓存。线程不安全，仅用于 asyncio 协程。"""

    def __init__(self, ttl: float = 5.0, max_size: int = 32):
        self.ttl = float(ttl)
        self.max_size = int(max_size)
        self._store: OrderedDict[Any, tuple[float, Any]] = OrderedDict()

    def get(self, key: Any) -> Optional[Any]:
        now = time.time()
        ent = self._store.get(key)
        if ent is None:
            return None
        ts, val = ent
        if now - ts > self.ttl:
            self._store.pop(key, None)
            return None
        # 命中时移到末尾（LRU）
        self._store.move_to_end(key)
        return val

    def set(self, key: Any, value: Any) -> None:
        now = time.time()
        self._store[key] = (now, value)
        self._store.move_to_end(key)
        # 容量限制：淘汰最旧条目
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()

    def purge_expired(self) -> int:
        """清理所有过期项；返回清理数量。"""
        now = time.time()
        expired = [k for k, (ts, _) in self._store.items() if now - ts > self.ttl]
        for k in expired:
            self._store.pop(k, None)
        return len(expired)

    def __len__(self) -> int:
        return len(self._store)


# ---------- 限频器 ----------

class Cooldown:
    """按 key 的冷却限频器。"""

    def __init__(self, cooldown_seconds: float = 5.0):
        self.cooldown = float(cooldown_seconds)
        self._last: dict[Any, float] = {}

    def check(self, key: Any) -> tuple[bool, float]:
        """返回 (是否允许, 距离下次可用的剩余秒数)。"""
        if self.cooldown <= 0:
            return True, 0.0
        now = time.time()
        last = self._last.get(key, 0.0)
        wait = self.cooldown - (now - last)
        if wait > 0:
            return False, wait
        self._last[key] = now
        # 顺便清理：避免字典无限增长
        if len(self._last) > 4096:
            cutoff = now - self.cooldown * 4
            for k in list(self._last.keys()):
                if self._last[k] < cutoff:
                    self._last.pop(k, None)
        return True, 0.0
