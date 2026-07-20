"""Komari 探针 API 客户端（REST + RPC2）。"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import aiohttp

from astrbot.api import logger

try:
    from .utils import (
        TTLCache,
        safe_float,
        safe_int,
        sanitize_for_log,
        validate_url,
    )
except ImportError:
    from utils import (  # type: ignore
        TTLCache,
        safe_float,
        safe_int,
        sanitize_for_log,
        validate_url,
    )


class KomariError(Exception):
    """Komari API 调用失败。"""

    def __init__(self, msg: str, *, public: Optional[str] = None):
        super().__init__(msg)
        # 群聊可暴露的简短信息（不含内部地址/正文）
        self.public = public or "Komari 请求失败"


# 全局并发上限：避免单次命令把后端打满
_REST_RECENT_SEMAPHORE: Optional[asyncio.Semaphore] = None


def _get_recent_semaphore(limit: int = 8) -> asyncio.Semaphore:
    global _REST_RECENT_SEMAPHORE
    if _REST_RECENT_SEMAPHORE is None:
        _REST_RECENT_SEMAPHORE = asyncio.Semaphore(max(1, limit))
    return _REST_RECENT_SEMAPHORE


# 单节点状态获取的并发上限（仅在 RPC 失败回退时生效）
_REST_RECENT_CONCURRENCY = 8
# REST recent 最多拉多少个节点（防放大）
_REST_RECENT_MAX_NODES = 60
# 节点列表最大返回数（防止超大规模面板拖垮渲染）
_MAX_NODES_RETURNED = 200
# HTTP 响应体最大字节数
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB
# 失败 RPC 的冷却时间（避免每条命令都重试 RPC）
_RPC_FAIL_COOLDOWN = 30.0


class KomariClient:
    """访问 Komari 面板的轻量客户端。

    优先使用 JSON-RPC2（>=1.0.7），失败时回退到 REST。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: float = 10.0,
        show_hidden: bool = False,
        *,
        allow_insecure: bool = False,
        cache_ttl: float = 5.0,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = (api_key or "").strip()
        # timeout 做范围校验：1~60s，避免极端值
        try:
            t = float(timeout)
        except (TypeError, ValueError):
            t = 10.0
        if t != t or t in (float("inf"), float("-inf")):  # NaN/Inf
            t = 10.0
        self.timeout = max(1.0, min(60.0, t))
        self.show_hidden = bool(show_hidden)
        # 是否允许 http + 内网地址（默认拒绝）
        self.allow_insecure = bool(allow_insecure)
        self._session: Optional[aiohttp.ClientSession] = None
        self._rpc_available: Optional[bool] = None
        self._rpc_last_fail_ts: float = 0.0
        # 短期缓存：nodes / status
        self._nodes_cache = TTLCache(ttl=max(1.0, cache_ttl), max_size=4)
        self._status_cache = TTLCache(ttl=max(1.0, cache_ttl), max_size=32)

    def configured(self) -> bool:
        return bool(self.base_url)

    def validate(self) -> None:
        """启动期校验配置；失败抛 ValueError。"""
        if not self.base_url:
            return  # 未配置由上层提示
        schemes = ("http", "https") if self.allow_insecure else ("https",)
        # 带 api_key 时强制 https（即便 allow_insecure 也不放开 http）
        cleaned = validate_url(
            self.base_url,
            allow_schemes=schemes,
            require_https_when_auth=True,
            has_auth=bool(self.api_key),
            allow_private=True,  # 内网 Komari 是常见部署
            allow_userinfo=False,
        )
        self.base_url = cleaned

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"User-Agent": "AstrBot-Komari-Plugin/1.5"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            # trust_env=False：避免意外使用宿主机代理配置
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=timeout,
                trust_env=False,
            )
        return self._session

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "AstrBot-Komari-Plugin/1.5"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: Optional[dict] = None,
    ) -> Any:
        if not self.base_url:
            raise KomariError(
                "未配置 Komari 面板地址",
                public="⚠️ 未配置面板地址",
            )

        url = f"{self.base_url}{path}"
        session = await self._get_session()
        try:
            async with session.request(
                method, url, json=json_body, params=params,
                allow_redirects=False,  # 显式禁止：避免被诱导到内网
            ) as resp:
                # 拒绝重定向：Komari API 不应重定向；若出现则视为异常
                if resp.status in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("Location", "")
                    logger.warning(
                        f"Komari 返回重定向 ({resp.status})，已拒绝: "
                        f"{sanitize_for_log(loc, 120)}"
                    )
                    raise KomariError(
                        f"Komari 返回重定向 ({resp.status})，已拒绝",
                        public="❌ 面板地址异常（重定向），请检查 base_url",
                    )

                # 先看 Content-Length，再受限读
                clen = resp.headers.get("Content-Length")
                if clen:
                    try:
                        if int(clen) > _MAX_RESPONSE_BYTES:
                            raise KomariError(
                                f"响应体过大: {clen} bytes",
                                public="❌ 面板返回数据过大",
                            )
                    except ValueError:
                        pass

                # 受限读取：超过上限立即中止
                body = await resp.content.read(_MAX_RESPONSE_BYTES + 1)
                if len(body) > _MAX_RESPONSE_BYTES:
                    raise KomariError(
                        f"响应体超过 {_MAX_RESPONSE_BYTES} bytes",
                        public="❌ 面板返回数据过大",
                    )
                try:
                    text = body.decode("utf-8", errors="replace")
                except Exception:
                    text = ""

                if resp.status >= 400:
                    logger.debug(
                        f"Komari HTTP {resp.status}: "
                        f"{sanitize_for_log(text, 200)}"
                    )
                    raise KomariError(
                        f"HTTP {resp.status}: {text[:200] or resp.reason}",
                        public=f"❌ 面板返回 HTTP {resp.status}",
                    )
                if not text:
                    return None
                try:
                    import json as _json
                    return _json.loads(text)
                except Exception as e:
                    logger.debug(
                        f"响应不是合法 JSON: {sanitize_for_log(text, 200)}"
                    )
                    raise KomariError(
                        f"响应不是合法 JSON: {e}: {text[:200]}",
                        public="❌ 面板响应格式异常",
                    )
        except aiohttp.ClientError as e:
            raise KomariError(
                f"网络错误: {e}",
                public="❌ 无法连接面板（网络错误）",
            ) from e
        except asyncio.TimeoutError as e:
            raise KomariError(
                f"请求超时（{self.timeout}s）",
                public=f"❌ 请求超时（{self.timeout:.0f}s）",
            ) from e
        except KomariError:
            raise
        except Exception as e:
            logger.exception("Komari 请求未知异常")
            raise KomariError(
                f"请求异常: {e}",
                public="❌ 请求异常",
            ) from e

    async def rpc(self, method: str, params: Optional[dict] = None) -> Any:
        """调用 JSON-RPC2。"""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": 1,
        }
        data = await self._request("POST", "/api/rpc2", json_body=payload)
        if not isinstance(data, dict):
            raise KomariError(
                "RPC 响应格式异常",
                public="❌ RPC 响应格式异常",
            )
        if data.get("error"):
            err = data["error"]
            if isinstance(err, dict):
                msg = err.get("message") or str(err)
            else:
                msg = str(err)
            raise KomariError(
                f"RPC 错误: {msg}",
                public="❌ RPC 调用失败",
            )
        return data.get("result")

    async def _rest_get(self, path: str, params: Optional[dict] = None) -> Any:
        data = await self._request("GET", path, params=params)
        if isinstance(data, dict) and data.get("status") == "success":
            return data.get("data")
        if isinstance(data, dict) and "data" in data:
            return data.get("data")
        return data

    # ---------- 高层接口 ----------

    async def get_public_info(self) -> dict:
        try:
            result = await self.rpc("common:getPublicInfo")
            if isinstance(result, dict):
                return result
        except KomariError as e:
            logger.debug(
                f"RPC getPublicInfo 失败，回退 REST: {sanitize_for_log(str(e))}"
            )
        data = await self._rest_get("/api/public")
        return data if isinstance(data, dict) else {}

    async def get_version(self) -> dict:
        # REST 返回 Komari 服务端版本；RPC rpc.version 是协议版本（如 2.0），仅作补充
        try:
            data = await self._rest_get("/api/version")
            if isinstance(data, dict) and (data.get("version") or data.get("hash")):
                return data
            if data is not None:
                return {"version": str(data)}
        except KomariError:
            pass
        try:
            ver = await self.rpc("rpc.version")
            if ver is not None:
                return {"version": str(ver), "source": "rpc"}
        except KomariError:
            pass
        return {}

    def _rpc_usable(self) -> bool:
        """RPC 失败后短期冷却，避免每条命令都重试。"""
        if self._rpc_available is True:
            return True
        now = time.time()
        if self._rpc_last_fail_ts and now - self._rpc_last_fail_ts < _RPC_FAIL_COOLDOWN:
            return False
        return True

    def _mark_rpc_fail(self) -> None:
        self._rpc_available = False
        self._rpc_last_fail_ts = time.time()

    def _mark_rpc_ok(self) -> None:
        self._rpc_available = True
        self._rpc_last_fail_ts = 0.0

    async def get_nodes(self) -> list[dict]:
        """返回节点列表（list of Client dict）。"""
        cached = self._nodes_cache.get("all")
        if cached is not None:
            return cached

        nodes: list[dict] = []
        if self._rpc_usable():
            try:
                result = await self.rpc("common:getNodes")
                if isinstance(result, dict):
                    # 可能是单个节点或 {uuid: Client}
                    if "uuid" in result and "name" in result:
                        nodes = [result]
                    else:
                        nodes = list(result.values())
                elif isinstance(result, list):
                    nodes = result
                if nodes:
                    self._mark_rpc_ok()
                    filtered = self._filter_nodes(nodes)
                    self._nodes_cache.set("all", filtered)
                    return filtered
            except KomariError as e:
                self._mark_rpc_fail()
                logger.debug(
                    f"RPC getNodes 失败，回退 REST: {sanitize_for_log(str(e))}"
                )

        data = await self._rest_get("/api/nodes")
        if isinstance(data, list):
            nodes = data
        elif isinstance(data, dict):
            nodes = list(data.values())
        else:
            nodes = []
        filtered = self._filter_nodes(nodes)
        self._nodes_cache.set("all", filtered)
        return filtered

    def _filter_nodes(self, nodes: list[dict]) -> list[dict]:
        result = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            if n.get("hidden") and not self.show_hidden:
                continue
            result.append(n)
        # weight 大的靠前；weight 用 safe_int 保护
        result.sort(
            key=lambda x: (
                -safe_int(x.get("weight"), 0),
                str(x.get("name") or ""),
            )
        )
        # 限制节点数量上限，防止超大规模面板拖垮渲染
        if len(result) > _MAX_NODES_RETURNED:
            result = result[:_MAX_NODES_RETURNED]
        return result

    async def get_latest_status(
        self, uuid: Optional[str] = None
    ) -> dict[str, dict]:
        """返回 {uuid: NodeStatus}。"""
        cache_key = uuid or "all"
        cached = self._status_cache.get(cache_key)
        if cached is not None:
            return cached

        if self._rpc_usable():
            try:
                params: dict[str, Any] = {}
                if uuid:
                    params["uuid"] = uuid
                result = await self.rpc("common:getNodesLatestStatus", params)
                if isinstance(result, dict):
                    # 兼容直接返回单节点状态
                    if "online" in result and "client" in result:
                        key = result.get("client") or uuid or "unknown"
                        out = {key: result}
                    else:
                        out = {k: v for k, v in result.items() if isinstance(v, dict)}
                    self._mark_rpc_ok()
                    self._status_cache.set(cache_key, out)
                    return out
            except KomariError as e:
                self._mark_rpc_fail()
                logger.debug(
                    f"RPC getNodesLatestStatus 失败，回退 REST: "
                    f"{sanitize_for_log(str(e))}"
                )

        # REST 回退：逐节点拉 recent，受限并发
        nodes = await self.get_nodes()
        targets = nodes
        if uuid:
            targets = [n for n in nodes if n.get("uuid") == uuid]
            if not targets:
                targets = [{"uuid": uuid}]

        # 限制单次命令最多拉多少个节点状态
        if len(targets) > _REST_RECENT_MAX_NODES:
            logger.warning(
                f"节点数 {len(targets)} 超过上限 {_REST_RECENT_MAX_NODES}，"
                f"仅拉取前 {_REST_RECENT_MAX_NODES} 个"
            )
            targets = targets[:_REST_RECENT_MAX_NODES]

        sem = _get_recent_semaphore(_REST_RECENT_CONCURRENCY)

        async def _fetch_one(n: dict) -> tuple[str, dict]:
            uid = n.get("uuid")
            if not uid:
                return "", {}
            async with sem:
                try:
                    recent = await self._rest_get(f"/api/recent/{uid}")
                    status = self._recent_to_status(uid, recent)
                    if status:
                        return uid, status
                except KomariError as e:
                    logger.debug(
                        f"获取节点 {uid} recent 失败: {sanitize_for_log(str(e))}"
                    )
            return uid, {"client": uid, "online": False}

        out: dict[str, dict] = {}
        results = await asyncio.gather(
            *[_fetch_one(n) for n in targets], return_exceptions=True
        )
        for r in results:
            if isinstance(r, Exception):
                logger.debug(f"recent gather 异常: {sanitize_for_log(str(r))}")
                continue
            uid, status = r  # type: ignore[misc]
            if uid and status:
                out[uid] = status
        self._status_cache.set(cache_key, out)
        return out

    def _normalize_status(self, status: dict, uuid: str) -> dict:
        """规范化状态字段：强制数值类型，过滤异常值。"""
        out = dict(status)
        out["client"] = out.get("client") or uuid
        # 数值字段统一规范
        for k in ("cpu", "load", "load5", "load15"):
            if k in out:
                out[k] = safe_float(out.get(k), 0.0, minimum=0.0)
        for k in (
            "ram", "ram_total", "swap", "swap_total",
            "disk", "disk_total", "net_in", "net_out",
            "net_total_up", "net_total_down", "process",
            "connections", "connections_udp",
        ):
            if k in out:
                out[k] = safe_int(out.get(k), 0, minimum=0)
        # cpu / 百分比合理范围 0~100
        if "cpu" in out:
            out["cpu"] = max(0.0, min(100.0, out["cpu"]))
        return out

    def _recent_to_status(self, uuid: str, recent: Any) -> Optional[dict]:
        """将 /api/recent 嵌套结构转为扁平 NodeStatus。"""
        record = None
        if isinstance(recent, list) and recent:
            record = recent[-1]
        elif isinstance(recent, dict):
            if "cpu" in recent or "ram" in recent:
                record = recent
            elif isinstance(recent.get("records"), list) and recent["records"]:
                record = recent["records"][-1]

        if not isinstance(record, dict):
            return {"client": uuid, "online": False}

        # 已是扁平结构
        if isinstance(record.get("cpu"), (int, float)) and "ram_total" in record:
            status = dict(record)
            status.setdefault("client", uuid)
            status.setdefault("online", True)
            return self._normalize_status(status, uuid)

        # 嵌套结构（WebSocket / recent）
        cpu = record.get("cpu") or {}
        ram = record.get("ram") or {}
        swap = record.get("swap") or {}
        load = record.get("load") or {}
        disk = record.get("disk") or {}
        network = record.get("network") or {}
        conn = record.get("connections") or {}

        status = {
            "client": uuid,
            "time": record.get("updated_at") or record.get("time"),
            "cpu": safe_float(
                cpu.get("usage", 0) if isinstance(cpu, dict) else cpu,
                0.0, minimum=0.0, maximum=100.0,
            ),
            "ram": safe_int(ram.get("used", 0) if isinstance(ram, dict) else 0, 0, minimum=0),
            "ram_total": safe_int(ram.get("total", 0) if isinstance(ram, dict) else 0, 0, minimum=0),
            "swap": safe_int(swap.get("used", 0) if isinstance(swap, dict) else 0, 0, minimum=0),
            "swap_total": safe_int(swap.get("total", 0) if isinstance(swap, dict) else 0, 0, minimum=0),
            "load": safe_float(load.get("load1", 0) if isinstance(load, dict) else load, 0.0, minimum=0.0),
            "load5": safe_float(load.get("load5", 0) if isinstance(load, dict) else 0, 0.0, minimum=0.0),
            "load15": safe_float(load.get("load15", 0) if isinstance(load, dict) else 0, 0.0, minimum=0.0),
            "disk": safe_int(disk.get("used", 0) if isinstance(disk, dict) else 0, 0, minimum=0),
            "disk_total": safe_int(disk.get("total", 0) if isinstance(disk, dict) else 0, 0, minimum=0),
            "net_in": safe_int(network.get("down", 0) if isinstance(network, dict) else 0, 0, minimum=0),
            "net_out": safe_int(network.get("up", 0) if isinstance(network, dict) else 0, 0, minimum=0),
            "net_total_up": safe_int(network.get("totalUp", 0) if isinstance(network, dict) else 0, 0, minimum=0),
            "net_total_down": safe_int(network.get("totalDown", 0) if isinstance(network, dict) else 0, 0, minimum=0),
            "process": safe_int(record.get("process"), 0, minimum=0),
            "connections": safe_int(conn.get("tcp", 0) if isinstance(conn, dict) else 0, 0, minimum=0),
            "connections_udp": safe_int(conn.get("udp", 0) if isinstance(conn, dict) else 0, 0, minimum=0),
            "uptime": record.get("uptime"),
            "online": True,
        }
        return self._normalize_status(status, uuid)

    @staticmethod
    def _node_search_blob(node: dict) -> str:
        """汇总可搜索字段，便于模糊匹配。"""
        parts = [
            str(node.get("name") or ""),
            str(node.get("tags") or "").replace(";", " ").replace(",", " "),
            str(node.get("group") or ""),
            str(node.get("region") or ""),
            str(node.get("public_remark") or ""),
            str(node.get("remark") or ""),
            str(node.get("os") or ""),
            str(node.get("cpu_name") or ""),
            str(node.get("uuid") or ""),
        ]
        return " ".join(parts).lower()

    @staticmethod
    def _match_score(node: dict, ql: str) -> int:
        """分数越高越优先；0 表示不匹配。"""
        import re
        if not ql:
            return 0
        name = str(node.get("name") or "").lower()
        tags = str(node.get("tags") or "").lower().replace(",", ";")
        tag_list = [t.strip() for t in tags.split(";") if t.strip()]
        group = str(node.get("group") or "").lower()
        remark = (
            str(node.get("public_remark") or "")
            + " "
            + str(node.get("remark") or "")
        ).lower()
        uid = str(node.get("uuid") or "").lower()

        if name == ql or uid == ql:
            return 100
        if any(t == ql for t in tag_list):
            return 95
        if group == ql:
            return 92
        if name.startswith(ql):
            return 90
        # 名称按 - _ / 空格 分段：DMIT 命中 LAX-DMIT-xx
        name_tokens = [t for t in re.split(r"[\s\-_./|]+", name) if t]
        if any(t == ql for t in name_tokens):
            return 88
        if any(t.startswith(ql) for t in name_tokens):
            return 84
        if ql in name:
            return 80
        if any(ql in t or t in ql for t in tag_list if len(t) >= 2):
            return 78
        if ql in tags:
            return 75
        if uid.startswith(ql) and len(ql) >= 4:
            return 72
        if ql in group:
            return 65
        if ql in remark:
            return 60
        # 多关键词：/km dmit lax  -> 全部命中
        blob = KomariClient._node_search_blob(node)
        words = [w for w in re.split(r"\s+", ql) if w]
        if len(words) > 1 and all(w in blob for w in words):
            return 70
        if ql in blob:
            return 50
        return 0

    async def find_nodes(self, query: str, limit: int = 10) -> list[dict]:
        """模糊搜索节点，按匹配分数排序。"""
        q = (query or "").strip()
        if not q:
            return []
        nodes = await self.get_nodes()
        if not nodes:
            return []

        if q.isdigit():
            idx = int(q) - 1
            if 0 <= idx < len(nodes):
                return [nodes[idx]]
            return []

        ql = q.lower()
        scored: list[tuple[int, dict]] = []
        for n in nodes:
            score = self._match_score(n, ql)
            if score > 0:
                scored.append((score, n))
        scored.sort(
            key=lambda x: (
                -x[0],
                -safe_int(x[1].get("weight"), 0),
                str(x[1].get("name") or ""),
            )
        )
        # 限制搜索返回上限
        limit = max(1, min(int(limit or 10), 20))
        return [n for _, n in scored[:limit]]

    async def find_node(self, query: str) -> Optional[dict]:
        """按名称 / 标签 / 分组 / uuid / 序号模糊查找最优节点。"""
        hits = await self.find_nodes(query, limit=1)
        return hits[0] if hits else None

    def invalidate_cache(self) -> None:
        """配置变更或主动刷新时调用。"""
        self._nodes_cache.clear()
        self._status_cache.clear()
