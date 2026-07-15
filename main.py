"""AstrBot 插件：Komari 服务器监控（概况 / 列表 / 单机 / 分类）。"""

from __future__ import annotations

import asyncio
import re
import time

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

try:
    from .cards import (
        DEFAULT_BG_URL,
        TMPL_DETAIL,
        TMPL_GROUP,
        TMPL_LIST,
        TMPL_SUMMARY,
        WIDTH_DETAIL,
        WIDTH_GROUP,
        WIDTH_LIST,
        WIDTH_SUMMARY,
        build_group_data,
        build_list_data,
        build_node_view,
        build_summary_data,
        screenshot_options,
    )
    from .formatter import (
        format_group,
        format_help,
        format_list,
        format_status_one,
        format_summary,
    )
    from .komari_client import KomariClient, KomariError
except ImportError:
    from cards import (  # type: ignore
        DEFAULT_BG_URL,
        TMPL_DETAIL,
        TMPL_GROUP,
        TMPL_LIST,
        TMPL_SUMMARY,
        WIDTH_DETAIL,
        WIDTH_GROUP,
        WIDTH_LIST,
        WIDTH_SUMMARY,
        build_group_data,
        build_list_data,
        build_node_view,
        build_summary_data,
        screenshot_options,
    )
    from formatter import (  # type: ignore
        format_group,
        format_help,
        format_list,
        format_status_one,
        format_summary,
    )
    from komari_client import KomariClient, KomariError  # type: ignore


@register(
    "astrbot_plugin_komari",
    "serenite",
    "Komari 服务器监控：概况 / 列表 / 单机 / 分类",
    "1.4.9",
)
class KomariPlugin(Star):
    # 模糊多选缓存：序号对应「上一次候选列表」，而非全量 list 序号
    _PICK_TTL = 300  # 秒（5 分钟）

    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self.client = self._build_client()
        # key -> {"ts": float, "uuids": [str, ...], "query": str}
        self._pick_cache: dict[str, dict] = {}

    def _build_client(self) -> KomariClient:
        return KomariClient(
            base_url=str(self.config.get("base_url", "") or ""),
            api_key=str(self.config.get("api_key", "") or ""),
            timeout=float(self.config.get("timeout", 10) or 10),
            show_hidden=bool(self.config.get("show_hidden", False)),
        )

    def _reload_client(self) -> None:
        new = self._build_client()
        changed = (
            new.base_url != self.client.base_url
            or new.api_key != self.client.api_key
            or abs(new.timeout - self.client.timeout) > 1e-6
            or new.show_hidden != self.client.show_hidden
        )
        if not changed:
            return
        old = self.client
        self.client = new
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(old.close())
        except Exception:
            pass

    def _use_card(self) -> bool:
        mode = str(self.config.get("output_mode", "card") or "card").lower()
        return mode != "text"

    def _image_quality(self) -> str:
        q = str(self.config.get("image_quality", "ultra") or "ultra").lower()
        return q if q in ("normal", "high", "ultra") else "ultra"

    def _bg_url(self) -> str:
        """二次元背景图接口；带时间戳避免缓存同一张。"""
        base = str(self.config.get("bg_url", "") or DEFAULT_BG_URL).strip()
        if not base:
            base = DEFAULT_BG_URL
        base = base.rstrip("/")
        # 随机图接口：加 query 防止文转图缓存
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}_t={int(time.time() * 1000)}"

    def _with_bg(self, data: dict) -> dict:
        out = dict(data)
        out["bg_url"] = self._bg_url()
        return out

    def _whitelist_ids(self) -> set[str]:
        raw = str(self.config.get("allowed_users", "") or "")
        parts = re.split(r"[\s,;，；]+", raw)
        return {p.strip() for p in parts if p.strip()}

    def _check_permission(self, event: AstrMessageEvent) -> tuple[bool, str]:
        """返回 (是否允许, 拒绝时的提示)。"""
        mode = str(self.config.get("permission_mode", "all") or "all").lower()
        if mode in ("", "all", "everyone", "public"):
            return True, ""

        sender = str(event.get_sender_id() or "")
        is_admin = False
        try:
            is_admin = bool(event.is_admin())
        except Exception:
            is_admin = False

        if mode in ("admin", "admins", "管理员"):
            if is_admin:
                return True, ""
            return False, "⛔ 此指令仅 AstrBot 管理员可用。"

        if mode in ("whitelist", "wl", "白名单"):
            if is_admin:
                return True, ""
            allow = self._whitelist_ids()
            if sender and sender in allow:
                return True, ""
            return (
                False,
                "⛔ 你不在白名单中，无法使用此指令。\n"
                "（管理员可在插件配置里添加 allowed_users，或用 /sid 查看自己的 ID）",
            )

        # 未知模式当作 all
        return True, ""

    async def initialize(self):
        if self.client.configured():
            logger.info(f"Komari 插件已加载：{self.client.base_url}")
        else:
            logger.warning("Komari 插件未配置 base_url，请在后台填写")

    async def terminate(self):
        await self.client.close()

    def _parse_args(self, event: AstrMessageEvent) -> list[str]:
        text = (event.message_str or "").strip()
        if not text:
            return []
        parts = text.split()
        if parts and parts[0].lstrip("/").lower() in {"km", "komari"}:
            parts = parts[1:]
        return parts

    def _session_key(self, event: AstrMessageEvent) -> str:
        sender = str(event.get_sender_id() or "")
        try:
            umo = getattr(event, "unified_msg_origin", None) or ""
        except Exception:
            umo = ""
        return f"{umo}:{sender}"

    def _save_pick_cache(self, event: AstrMessageEvent, query: str, nodes: list[dict]) -> None:
        """保存模糊多选候选，供后续 /km 1 选择。"""
        now = time.time()
        # 清理过期
        expired = [
            k
            for k, v in self._pick_cache.items()
            if now - float(v.get("ts") or 0) > self._PICK_TTL
        ]
        for k in expired:
            self._pick_cache.pop(k, None)

        uuids = [str(n.get("uuid") or "") for n in nodes if n.get("uuid")]
        if not uuids:
            return
        self._pick_cache[self._session_key(event)] = {
            "ts": now,
            "uuids": uuids,
            "query": query,
        }

    def _resolve_pick_index(self, event: AstrMessageEvent, idx_1based: int):
        """把 1-based 序号解析为缓存候选的 uuid；无缓存则返回 None。"""
        key = self._session_key(event)
        entry = self._pick_cache.get(key)
        if not entry:
            return None
        if time.time() - float(entry.get("ts") or 0) > self._PICK_TTL:
            self._pick_cache.pop(key, None)
            return None
        uuids = entry.get("uuids") or []
        i = idx_1based - 1
        if i < 0 or i >= len(uuids):
            return None
        return uuids[i]

    async def _render_card(self, tmpl: str, data: dict, width: int):
        try:
            opts = screenshot_options(width, self._image_quality())
            return await self.html_render(tmpl, data, options=opts)
        except Exception as e:
            logger.warning(f"卡片渲染失败，回退文本: {e}")
            return None

    async def _reply(
        self,
        event: AstrMessageEvent,
        tmpl: str,
        data: dict,
        text: str,
        width: int,
    ):
        if self._use_card():
            url = await self._render_card(tmpl, self._with_bg(data), width)
            if url:
                yield event.image_result(url)
                return
        yield event.plain_result(text)

    async def _fetch_all(self):
        nodes = await self.client.get_nodes()
        try:
            status_map = await self.client.get_latest_status()
        except KomariError:
            status_map = {}
        return nodes, status_map

    @filter.command("km", alias={"komari"})
    async def km_cmd(self, event: AstrMessageEvent):
        """服务器监控：概况 / 列表 / 单机 / 分类"""
        self._reload_client()

        ok, deny_msg = self._check_permission(event)
        if not ok:
            yield event.plain_result(deny_msg)
            return

        if not self.client.configured():
            yield event.plain_result(
                "⚠️ 未配置面板地址。\n"
                "请到 AstrBot 后台 → 插件 → Komari 探针 填写 base_url。"
            )
            return

        args = self._parse_args(event)
        if not args:
            async for m in self._cmd_summary(event):
                yield m
            return

        sub = args[0].lower()
        rest = " ".join(args[1:]).strip()

        try:
            if sub in ("help", "帮助", "h", "?"):
                yield event.plain_result(format_help("km"))
            elif sub in ("概况", "summary", "ov", "overview", "总览"):
                async for m in self._cmd_summary(event):
                    yield m
            elif sub in ("list", "ls", "列表"):
                async for m in self._cmd_list(event):
                    yield m
            elif sub in ("group", "分类", "grp", "g", "groups"):
                async for m in self._cmd_group(event, rest):
                    yield m
            elif sub in ("info", "status", "st", "信息", "状态", "s", "i"):
                if not rest:
                    yield event.plain_result(
                        "用法：/km <名称|序号>  或  /km info <名称>"
                    )
                    return
                async for m in self._cmd_one(event, rest):
                    yield m
            else:
                async for m in self._cmd_one(event, " ".join(args).strip()):
                    yield m
        except KomariError as e:
            logger.error(f"Komari 失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{e}")
        except Exception as e:
            logger.exception("Komari 插件异常")
            yield event.plain_result(f"❌ 插件错误：{e}")

    async def _cmd_summary(self, event: AstrMessageEvent):
        nodes, status_map = await self._fetch_all()
        data = build_summary_data(nodes, status_map)
        text = format_summary(nodes, status_map)
        async for m in self._reply(
            event, TMPL_SUMMARY, data, text, WIDTH_SUMMARY
        ):
            yield m

    async def _cmd_list(self, event: AstrMessageEvent):
        nodes, status_map = await self._fetch_all()
        data = build_list_data(nodes, status_map)
        text = format_list(nodes, status_map)
        async for m in self._reply(event, TMPL_LIST, data, text, WIDTH_LIST):
            yield m

    async def _cmd_one(self, event: AstrMessageEvent, query: str):
        q = (query or "").strip()
        node = None

        # 纯数字：优先用「上一次模糊候选」的序号，而不是全量 list 序号
        if q.isdigit():
            pick_uuid = self._resolve_pick_index(event, int(q))
            if pick_uuid:
                node = await self.client.find_node(pick_uuid)
                if node:
                    # 选中后清掉缓存，避免后续误点
                    self._pick_cache.pop(self._session_key(event), None)

        if node is None:
            hits = await self.client.find_nodes(q, limit=8)
            if not hits:
                # 数字且没有候选缓存时，提示可能是选候选
                if q.isdigit():
                    yield event.plain_result(
                        f"未找到序号「{q}」。\n"
                        "若刚看到多选列表，请在 5 分钟内用 /km 1、/km 2… 选择候选；\n"
                        "否则序号表示 /km list 的全局编号。"
                    )
                    return
                yield event.plain_result(
                    f"未找到「{query}」。\n"
                    "支持模糊匹配名称 / 标签 / 分组。发送 /km list 查看列表。"
                )
                return

            # 多个同分候选时列出，序号写入会话缓存
            if len(hits) > 1:
                ql = q.lower()
                s0 = self.client._match_score(hits[0], ql)
                s1 = self.client._match_score(hits[1], ql)
                if s0 < 95 and s0 == s1:
                    self._save_pick_cache(event, q, hits)
                    lines = [
                        f"找到多个与「{query}」相关的节点，请选择：",
                        "──────────────",
                    ]
                    for i, n in enumerate(hits, 1):
                        region = n.get("region") or ""
                        name = n.get("name") or "?"
                        group = n.get("group") or ""
                        tags = (n.get("tags") or "").replace(";", "/")
                        extra = f" · {group}" if group else ""
                        if tags:
                            extra += f" · {tags}"
                        lines.append(f"{i}. {region}{name}{extra}")
                    lines.append("──────────────")
                    lines.append(
                        f"回复 /km 1 ~ /km {len(hits)} 选择上方候选（5 分钟内有效）\n"
                        "或直接 /km 节点全名"
                    )
                    yield event.plain_result("\n".join(lines))
                    return

            node = hits[0]

        uid = node.get("uuid")
        status_map = await self.client.get_latest_status(uid)
        status = status_map.get(uid) if uid else None
        view = build_node_view(node, status, 1)
        text = format_status_one(node, status)
        async for m in self._reply(
            event, TMPL_DETAIL, {"node": view}, text, WIDTH_DETAIL
        ):
            yield m

    async def _cmd_group(self, event: AstrMessageEvent, group_query: str):
        nodes, status_map = await self._fetch_all()
        data = build_group_data(nodes, status_map, group_query)
        text = format_group(nodes, status_map, group_query)
        if group_query and not data["sections"]:
            yield event.plain_result(
                f"未找到分组「{group_query}」。\n"
                "发送 /km group 查看全部分类。"
            )
            return
        async for m in self._reply(event, TMPL_GROUP, data, text, WIDTH_GROUP):
            yield m
