"""纯文本回退。"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Optional


def human_bytes(n: Any) -> str:
    try:
        num = float(n or 0)
    except (TypeError, ValueError):
        return "0 B"
    if num < 0:
        num = 0
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while num >= 1024 and i < len(units) - 1:
        num /= 1024
        i += 1
    if i == 0:
        return f"{int(num)} {units[i]}"
    return f"{num:.2f} {units[i]}"


def human_speed(n: Any) -> str:
    return f"{human_bytes(n)}/s"


def percent(used: Any, total: Any) -> float:
    try:
        u = float(used or 0)
        t = float(total or 0)
    except (TypeError, ValueError):
        return 0.0
    if t <= 0:
        return 0.0
    return max(0.0, min(100.0, u / t * 100))


def human_uptime(seconds: Any) -> str:
    try:
        s = int(float(seconds or 0))
    except (TypeError, ValueError):
        return "-"
    if s <= 0:
        return "-"
    days, rem = divmod(s, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}天")
    if hours or days:
        parts.append(f"{hours}时")
    parts.append(f"{mins}分")
    return "".join(parts)


def is_online(status: Optional[dict]) -> bool:
    if not status:
        return False
    if "online" in status:
        return bool(status.get("online"))
    return status.get("cpu") is not None or status.get("time") is not None


def format_help(prefix: str = "km") -> str:
    p = prefix
    return (
        "📡 服务器监控\n"
        "──────────────\n"
        f"/{p}              服务器概况\n"
        f"/{p} list         服务器列表\n"
        f"/{p} <名称>       单机详情（含CPU）\n"
        f"/{p} group [分组] 分类信息\n"
        "──────────────\n"
        "名称支持模糊：节点名 / 标签 / 分组 / UUID\n"
        "多匹配时用 /km 1、/km 2 选候选（非 list 全局序号）\n"
        f"示例：/{p} list  |  /{p} DMIT  |  /{p} group Japan"
    )


def format_summary(nodes: list[dict], status_map: dict[str, dict]) -> str:
    if not nodes:
        return "暂无服务器。"
    online = offline = 0
    cpu_sum = ram_sum = 0.0
    cpu_n = 0
    total_cores = total_mem = total_disk = 0
    used_mem = used_disk = 0
    groups: OrderedDict[str, list] = OrderedDict()
    for n in nodes:
        st = status_map.get(n.get("uuid") or "")
        g = (n.get("group") or "").strip() or "未分组"
        groups.setdefault(g, [0, 0])
        groups[g][1] += 1
        try:
            total_cores += int(n.get("cpu_cores") or 0)
        except (TypeError, ValueError):
            pass
        try:
            total_mem += int(n.get("mem_total") or 0)
        except (TypeError, ValueError):
            pass
        try:
            total_disk += int(n.get("disk_total") or 0)
        except (TypeError, ValueError):
            pass
        if is_online(st):
            online += 1
            groups[g][0] += 1
            cpu_sum += float(st.get("cpu") or 0)
            ram_sum += percent(
                st.get("ram"), st.get("ram_total") or n.get("mem_total")
            )
            cpu_n += 1
            try:
                used_mem += int(st.get("ram") or 0)
            except (TypeError, ValueError):
                pass
            try:
                used_disk += int(st.get("disk") or 0)
            except (TypeError, ValueError):
                pass
        else:
            offline += 1
    avg_c = (cpu_sum / cpu_n) if cpu_n else 0.0
    avg_r = (ram_sum / cpu_n) if cpu_n else 0.0
    lines = [
        "📊 服务器概况",
        "──────────────",
        f"总计 {len(nodes)} · 在线 {online} · 离线 {offline}",
        f"CPU 总数 {total_cores} 核",
        f"内存总数 {human_bytes(total_mem)}（已用 {human_bytes(used_mem)}）",
        f"硬盘总数 {human_bytes(total_disk)}（已用 {human_bytes(used_disk)}）",
        f"在线均 CPU {avg_c:.1f}% · 均内存 {avg_r:.1f}%",
        "──────────────",
    ]
    for g, (on, tot) in groups.items():
        lines.append(f"· {g}：{on}/{tot} 在线")
    return "\n".join(lines)


def format_list(nodes: list[dict], status_map: Optional[dict[str, dict]] = None) -> str:
    if not nodes:
        return "暂无服务器。"
    status_map = status_map or {}
    lines = [f"📋 服务器列表（{len(nodes)}）", "──────────────"]
    for i, n in enumerate(nodes, 1):
        st = status_map.get(n.get("uuid") or "")
        on = is_online(st)
        flag = "🟢" if on else "🔴"
        name = n.get("name") or "?"
        region = n.get("region") or ""
        group = n.get("group") or ""
        extra = f" [{group}]" if group else ""
        if on:
            cpu = float(st.get("cpu") or 0)
            ram_p = percent(st.get("ram"), st.get("ram_total") or n.get("mem_total"))
            lines.append(
                f"{i}. {flag} {region}{name}{extra}  "
                f"负载 {cpu:.0f}% · 内存 {ram_p:.0f}%"
            )
        else:
            lines.append(f"{i}. {flag} {region}{name}{extra}  离线")
    return "\n".join(lines)


def format_status_one(node: dict, status: Optional[dict]) -> str:
    name = node.get("name") or "?"
    region = node.get("region") or ""
    group = (node.get("group") or "").strip() or "未分组"
    online = is_online(status)
    st = status or {}
    title = f"{region} {name}".strip()
    cpu_name = node.get("cpu_name") or "-"
    cores = node.get("cpu_cores") or "-"
    lines = [
        f"🖥 {title}",
        f"分组：{group}",
        f"状态：{'🟢 在线' if online else '🔴 离线'}",
        f"CPU：{cpu_name} × {cores}",
        f"系统：{node.get('os') or '-'} · {node.get('arch') or '-'}",
    ]
    if not online:
        lines.append(f"规格：内存 {human_bytes(node.get('mem_total'))} · 磁盘 {human_bytes(node.get('disk_total'))}")
        return "\n".join(lines)

    cpu = float(st.get("cpu") or 0)
    ram_p = percent(st.get("ram"), st.get("ram_total") or node.get("mem_total"))
    disk_p = percent(st.get("disk"), st.get("disk_total") or node.get("disk_total"))
    lines.extend(
        [
            "──────────────",
            f"负载 CPU {cpu:.1f}% · 内存 {ram_p:.1f}% · 磁盘 {disk_p:.1f}%",
            f"内存 {human_bytes(st.get('ram'))}/{human_bytes(st.get('ram_total') or node.get('mem_total'))}",
            f"磁盘 {human_bytes(st.get('disk'))}/{human_bytes(st.get('disk_total') or node.get('disk_total'))}",
            f"网速 ↓{human_speed(st.get('net_in') or 0)} ↑{human_speed(st.get('net_out') or 0)}",
            f"流量 ↓{human_bytes(st.get('net_total_down') or 0)} ↑{human_bytes(st.get('net_total_up') or 0)}",
            f"系统负载 {float(st.get('load') or 0):.2f} · 运行 {human_uptime(st.get('uptime'))}",
        ]
    )
    return "\n".join(lines)


def format_group(
    nodes: list[dict], status_map: dict[str, dict], group_query: str = ""
) -> str:
    buckets: OrderedDict[str, list] = OrderedDict()
    for i, n in enumerate(nodes, 1):
        g = (n.get("group") or "").strip() or "未分组"
        buckets.setdefault(g, []).append((i, n))

    q = (group_query or "").strip().lower()
    lines = [
        f"🗂 分类{' · ' + group_query if group_query else ''}",
        "──────────────",
    ]
    found = False
    for gname, items in buckets.items():
        if q and q not in gname.lower() and gname.lower() != q:
            continue
        found = True
        on = sum(
            1
            for _, n in items
            if is_online(status_map.get(n.get("uuid") or ""))
        )
        lines.append(f"【{gname}】{on}/{len(items)} 在线")
        for i, n in items:
            st = status_map.get(n.get("uuid") or "")
            flag = "🟢" if is_online(st) else "🔴"
            name = n.get("name") or "?"
            region = n.get("region") or ""
            if is_online(st):
                cpu = float(st.get("cpu") or 0)
                lines.append(f"  {i}. {flag} {region}{name}  负载 {cpu:.0f}%")
            else:
                lines.append(f"  {i}. {flag} {region}{name}  离线")
        lines.append("")
    if not found:
        return f"未找到分组「{group_query}」。" if group_query else "暂无服务器。"
    return "\n".join(lines).rstrip()
