"""Komari 探针 API 客户端（REST + RPC2）。"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

import aiohttp

from astrbot.api import logger


class KomariError(Exception):
    """Komari API 调用失败。"""


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
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self.show_hidden = show_hidden
        self._session: Optional[aiohttp.ClientSession] = None
        self._rpc_available: Optional[bool] = None

    def configured(self) -> bool:
        return bool(self.base_url)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"User-Agent": "AstrBot-Komari-Plugin/1.0"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        return self._session

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "AstrBot-Komari-Plugin/1.0"}
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
            raise KomariError("未配置 Komari 面板地址，请在插件设置中填写 base_url")

        url = f"{self.base_url}{path}"
        session = await self._get_session()
        try:
            async with session.request(
                method, url, json=json_body, params=params
            ) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise KomariError(
                        f"HTTP {resp.status}: {text[:200] or resp.reason}"
                    )
                if not text:
                    return None
                try:
                    return await resp.json(content_type=None)
                except Exception:
                    raise KomariError(f"响应不是合法 JSON: {text[:200]}")
        except aiohttp.ClientError as e:
            raise KomariError(f"网络错误: {e}") from e
        except asyncio.TimeoutError as e:
            raise KomariError(f"请求超时（{self.timeout}s）") from e

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
            raise KomariError("RPC 响应格式异常")
        if data.get("error"):
            err = data["error"]
            if isinstance(err, dict):
                msg = err.get("message") or str(err)
            else:
                msg = str(err)
            raise KomariError(f"RPC 错误: {msg}")
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
            logger.debug(f"RPC getPublicInfo 失败，回退 REST: {e}")
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

    async def get_nodes(self) -> list[dict]:
        """返回节点列表（list of Client dict）。"""
        nodes: list[dict] = []
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
                return self._filter_nodes(nodes)
        except KomariError as e:
            logger.debug(f"RPC getNodes 失败，回退 REST: {e}")

        data = await self._rest_get("/api/nodes")
        if isinstance(data, list):
            nodes = data
        elif isinstance(data, dict):
            nodes = list(data.values())
        else:
            nodes = []
        return self._filter_nodes(nodes)

    def _filter_nodes(self, nodes: list[dict]) -> list[dict]:
        result = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            if n.get("hidden") and not self.show_hidden:
                continue
            result.append(n)
        # weight 大的靠前
        result.sort(key=lambda x: (-int(x.get("weight") or 0), str(x.get("name") or "")))
        return result

    async def get_latest_status(
        self, uuid: Optional[str] = None
    ) -> dict[str, dict]:
        """返回 {uuid: NodeStatus}。"""
        try:
            params: dict[str, Any] = {}
            if uuid:
                params["uuid"] = uuid
            result = await self.rpc("common:getNodesLatestStatus", params)
            if isinstance(result, dict):
                # 兼容直接返回单节点状态
                if "online" in result and "client" in result:
                    key = result.get("client") or uuid or "unknown"
                    return {key: result}
                return {k: v for k, v in result.items() if isinstance(v, dict)}
        except KomariError as e:
            logger.debug(f"RPC getNodesLatestStatus 失败，回退 REST: {e}")

        # REST 回退：逐节点拉 recent
        nodes = await self.get_nodes()
        targets = nodes
        if uuid:
            targets = [n for n in nodes if n.get("uuid") == uuid]
            if not targets:
                targets = [{"uuid": uuid}]

        out: dict[str, dict] = {}
        for n in targets:
            uid = n.get("uuid")
            if not uid:
                continue
            try:
                recent = await self._rest_get(f"/api/recent/{uid}")
                status = self._recent_to_status(uid, recent)
                if status:
                    out[uid] = status
            except KomariError as e:
                logger.debug(f"获取节点 {uid} recent 失败: {e}")
                out[uid] = {"client": uid, "online": False}
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
            return status

        # 嵌套结构（WebSocket / recent）
        cpu = record.get("cpu") or {}
        ram = record.get("ram") or {}
        swap = record.get("swap") or {}
        load = record.get("load") or {}
        disk = record.get("disk") or {}
        network = record.get("network") or {}
        conn = record.get("connections") or {}

        return {
            "client": uuid,
            "time": record.get("updated_at") or record.get("time"),
            "cpu": float(cpu.get("usage", 0) if isinstance(cpu, dict) else cpu or 0),
            "ram": int(ram.get("used", 0) if isinstance(ram, dict) else 0),
            "ram_total": int(ram.get("total", 0) if isinstance(ram, dict) else 0),
            "swap": int(swap.get("used", 0) if isinstance(swap, dict) else 0),
            "swap_total": int(swap.get("total", 0) if isinstance(swap, dict) else 0),
            "load": float(load.get("load1", 0) if isinstance(load, dict) else load or 0),
            "load5": float(load.get("load5", 0) if isinstance(load, dict) else 0),
            "load15": float(load.get("load15", 0) if isinstance(load, dict) else 0),
            "disk": int(disk.get("used", 0) if isinstance(disk, dict) else 0),
            "disk_total": int(disk.get("total", 0) if isinstance(disk, dict) else 0),
            "net_in": int(network.get("down", 0) if isinstance(network, dict) else 0),
            "net_out": int(network.get("up", 0) if isinstance(network, dict) else 0),
            "net_total_up": int(
                network.get("totalUp", 0) if isinstance(network, dict) else 0
            ),
            "net_total_down": int(
                network.get("totalDown", 0) if isinstance(network, dict) else 0
            ),
            "process": int(record.get("process") or 0),
            "connections": int(conn.get("tcp", 0) if isinstance(conn, dict) else 0),
            "connections_udp": int(
                conn.get("udp", 0) if isinstance(conn, dict) else 0
            ),
            "uptime": record.get("uptime"),
            "online": True,
        }

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
        name_tokens = [
            t for t in re.split(r"[\s\-_./|]+", name) if t
        ]
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
        # 多关键词：/km dmit lax  → 全部命中
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
                -int(x[1].get("weight") or 0),
                str(x[1].get("name") or ""),
            )
        )
        return [n for _, n in scored[:limit]]

    async def find_node(self, query: str) -> Optional[dict]:
        """按名称 / 标签 / 分组 / uuid / 序号模糊查找最优节点。"""
        hits = await self.find_nodes(query, limit=1)
        return hits[0] if hits else None
