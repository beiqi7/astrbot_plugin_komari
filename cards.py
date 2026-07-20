"""群聊服务器高清卡片：概况 / 列表 / 单机 / 分类。"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Optional

try:
    from .formatter import (
        human_bytes,
        human_speed,
        human_uptime,
        is_online,
        percent,
    )
    from .utils import esc, safe_float, safe_int, is_safe_bg_url
except ImportError:
    from formatter import (  # type: ignore
        human_bytes,
        human_speed,
        human_uptime,
        is_online,
        percent,
    )
    from utils import (  # type: ignore
        esc,
        safe_float,
        safe_int,
        is_safe_bg_url,
    )

# 内容宽度（与 CSS 一致；高清靠 device_scale_factor 放大）
WIDTH_SUMMARY = 960
WIDTH_LIST = 960
WIDTH_DETAIL = 900
WIDTH_GROUP = 940

# 字段长度上限：防止远端异常数据撑爆渲染
MAX_NAME_LEN = 80
MAX_TAG_LEN = 40
MAX_REMARK_LEN = 200
MAX_OS_LEN = 80
MAX_GROUP_LEN = 60
# 列表/分组单页最大节点数（防止生成超大图片）
MAX_LIST_ROWS = 100
MAX_GROUP_ROWS = 80


def _level(online: bool, cpu: float, ram_p: float, disk_p: float = 0) -> str:
    if not online:
        return "off"
    if cpu >= 90 or ram_p >= 90 or disk_p >= 95:
        return "crit"
    if cpu >= 70 or ram_p >= 75 or disk_p >= 85:
        return "warn"
    return "ok"


def _short(s: Any, n: int = 42) -> str:
    t = str(s or "").strip()
    if not t or t.lower() in ("none", "null", "-"):
        return ""
    return t if len(t) <= n else t[: n - 1] + "…"


def build_node_view(
    node: dict, status: Optional[dict], index: int = 0
) -> dict[str, Any]:
    st = status or {}
    online = is_online(st)
    cpu = safe_float(st.get("cpu"), 0.0, 0.0, 100.0) if online else 0.0
    ram_used = st.get("ram") or 0
    ram_total = st.get("ram_total") or node.get("mem_total") or 0
    disk_used = st.get("disk") or 0
    disk_total = st.get("disk_total") or node.get("disk_total") or 0
    swap_used = st.get("swap") or 0
    swap_total = st.get("swap_total") or node.get("swap_total") or 0
    ram_p = percent(ram_used, ram_total) if online else 0.0
    disk_p = percent(disk_used, disk_total) if online else 0.0
    swap_p = percent(swap_used, swap_total) if online else 0.0

    cpu_name = esc(_short(node.get("cpu_name"), MAX_NAME_LEN), MAX_NAME_LEN + 4) or "-"
    cpu_cores = safe_int(node.get("cpu_cores"), 0, minimum=0)
    cpu_phys = safe_int(node.get("cpu_physical_cores"), 0, minimum=0)
    if cpu_phys and cpu_phys != cpu_cores:
        cores_label = f"{cpu_phys}P/{cpu_cores}T"
    elif cpu_cores:
        cores_label = f"{cpu_cores} 核"
    else:
        cores_label = "-"

    gpu_raw = _short(node.get("gpu_name"), MAX_NAME_LEN)
    if gpu_raw.lower() in ("none", "null", "-"):
        gpu_raw = ""
    gpu = esc(gpu_raw, MAX_NAME_LEN + 4)

    tags_raw = str(node.get("tags") or "")
    tag_list = [
        esc(t.strip(), MAX_TAG_LEN)
        for t in tags_raw.replace(",", ";").split(";")
        if t.strip()
    ][:5]

    load1 = st.get("load") if online else None
    load5 = st.get("load5") if online else None
    load15 = st.get("load15") if online else None
    load_str = "-"
    if online and load1 is not None:
        parts = [f"{safe_float(load1, 0.0, 0.0):.2f}"]
        if load5 is not None:
            parts.append(f"{safe_float(load5, 0.0, 0.0):.2f}")
        if load15 is not None:
            parts.append(f"{safe_float(load15, 0.0, 0.0):.2f}")
        load_str = " / ".join(parts)

    temp = st.get("temp")
    temp_str = ""
    if online and temp is not None:
        tv = safe_float(temp, -1.0)
        if tv > 0:
            temp_str = f"{tv:.0f}°C"

    name_raw = _short(node.get("name"), MAX_NAME_LEN) or "未命名"
    region_raw = _short(node.get("region"), MAX_NAME_LEN)
    group_raw = _short((node.get("group") or "").strip(), MAX_GROUP_LEN) or "未分组"
    return {
        "index": index,
        "name": esc(name_raw, MAX_NAME_LEN + 4),
        "region": esc(region_raw, MAX_NAME_LEN + 4),
        "group": esc(group_raw, MAX_GROUP_LEN + 4),
        "tags": tag_list,
        "online": online,
        "level": _level(online, cpu, ram_p, disk_p),
        # CPU
        "cpu": round(cpu, 1),
        "cpu_w": round(min(100.0, max(0.0, cpu)), 1),
        "cpu_name": cpu_name,
        "cpu_name_short": esc(_short(node.get("cpu_name"), 36), 40),
        "cpu_cores": cpu_cores or "-",
        "cores_label": cores_label,
        # 内存 / 磁盘 / 交换
        "ram_p": round(ram_p, 1),
        "ram_w": round(min(100.0, max(0.0, ram_p)), 1),
        "disk_p": round(disk_p, 1),
        "disk_w": round(min(100.0, max(0.0, disk_p)), 1),
        "swap_p": round(swap_p, 1),
        "swap_w": round(min(100.0, max(0.0, swap_p)), 1),
        "has_swap": bool(swap_total),
        "ram_label": (
            f"{human_bytes(ram_used)} / {human_bytes(ram_total)}"
            if online
            else human_bytes(node.get("mem_total"))
        ),
        "disk_label": (
            f"{human_bytes(disk_used)} / {human_bytes(disk_total)}"
            if online
            else human_bytes(node.get("disk_total"))
        ),
        "swap_label": (
            f"{human_bytes(swap_used)} / {human_bytes(swap_total)}"
            if online and swap_total
            else human_bytes(node.get("swap_total"))
        ),
        "mem_total": human_bytes(node.get("mem_total")),
        "disk_total": human_bytes(node.get("disk_total")),
        # 系统
        "os": esc(_short(node.get("os"), MAX_OS_LEN), MAX_OS_LEN + 4) or "-",
        "kernel": esc(_short(node.get("kernel_version"), 36), 40) or "-",
        "arch": esc(_short(node.get("arch"), 20), 24) or "-",
        "virt": esc(_short(node.get("virtualization"), 24), 28) or "-",
        "gpu": gpu,
        # 网络 / 运行
        "net_in": human_speed(st.get("net_in") or 0) if online else "-",
        "net_out": human_speed(st.get("net_out") or 0) if online else "-",
        "traffic_down": human_bytes(st.get("net_total_down") or 0) if online else "-",
        "traffic_up": human_bytes(st.get("net_total_up") or 0) if online else "-",
        "load": load_str,
        "temp": temp_str,
        "process": safe_int(st.get("process"), 0, minimum=0) if online else None,
        "tcp": safe_int(st.get("connections"), 0, minimum=0) if online else None,
        "udp": safe_int(st.get("connections_udp"), 0, minimum=0) if online else None,
        "uptime": human_uptime(st.get("uptime")) if online else "-",
        "remark": esc(_short(node.get("public_remark"), MAX_REMARK_LEN), MAX_REMARK_LEN + 4),
    }


def build_summary_data(
    nodes: list[dict], status_map: dict[str, dict]
) -> dict[str, Any]:
    online = offline = 0
    cpu_pct_sum = ram_pct_sum = disk_pct_sum = 0.0
    cpu_n = 0
    total_cores = 0
    total_mem = 0
    total_disk = 0
    used_mem = 0
    used_disk = 0
    groups: OrderedDict[str, dict] = OrderedDict()

    for n in nodes:
        st = status_map.get(n.get("uuid") or "")
        on = is_online(st)
        g_raw = _short((n.get("group") or "").strip(), MAX_GROUP_LEN) or "未分组"
        # 同一分组名在 OrderedDict 里以未转义形式聚合，渲染时统一转义
        if g_raw not in groups:
            groups[g_raw] = {
                "name": g_raw,
                "total": 0,
                "online": 0,
                "offline": 0,
                "cpu_sum": 0.0,
                "cpu_n": 0,
                "cores": 0,
                "mem": 0,
                "disk": 0,
            }
        groups[g_raw]["total"] += 1

        cores = safe_int(n.get("cpu_cores"), 0, minimum=0)
        mem_t = safe_int(n.get("mem_total"), 0, minimum=0)
        disk_t = safe_int(n.get("disk_total"), 0, minimum=0)

        # 硬件总量（全部节点，含离线）
        total_cores += cores
        total_mem += mem_t
        total_disk += disk_t
        groups[g_raw]["cores"] += cores
        groups[g_raw]["mem"] += mem_t
        groups[g_raw]["disk"] += disk_t

        if on:
            online += 1
            groups[g_raw]["online"] += 1
            c = safe_float(st.get("cpu"), 0.0, 0.0, 100.0)
            cpu_pct_sum += c
            cpu_n += 1
            groups[g_raw]["cpu_sum"] += c
            groups[g_raw]["cpu_n"] += 1
            ram_pct_sum += percent(
                st.get("ram"), st.get("ram_total") or mem_t
            )
            disk_pct_sum += percent(
                st.get("disk"), st.get("disk_total") or disk_t
            )
            used_mem += safe_int(st.get("ram"), 0, minimum=0)
            used_disk += safe_int(st.get("disk"), 0, minimum=0)
        else:
            offline += 1
            groups[g_raw]["offline"] += 1

    group_list = []
    for g in groups.values():
        t = g["total"] or 1
        g["online_pct"] = round(g["online"] / t * 100, 0)
        g["avg_cpu"] = (
            round(g["cpu_sum"] / g["cpu_n"], 1) if g["cpu_n"] else 0.0
        )
        g["cores_label"] = f"{g['cores']}核"
        g["mem_label"] = human_bytes(g["mem"])
        g["disk_label"] = human_bytes(g["disk"])
        # 渲染前对分组名做转义
        g["name"] = esc(g["name"], MAX_GROUP_LEN + 4)
        group_list.append(g)

    return {
        "total": len(nodes),
        "online": online,
        "offline": offline,
        "avg_cpu": round(cpu_pct_sum / cpu_n, 1) if cpu_n else 0.0,
        "avg_ram": round(ram_pct_sum / cpu_n, 1) if cpu_n else 0.0,
        "avg_disk": round(disk_pct_sum / cpu_n, 1) if cpu_n else 0.0,
        # 硬件总数
        "total_cores": total_cores,
        "total_cores_label": f"{total_cores}核",
        "total_mem": human_bytes(total_mem),
        "total_disk": human_bytes(total_disk),
        "used_mem": human_bytes(used_mem),
        "used_disk": human_bytes(used_disk),
        "groups": group_list,
        "group_count": len(group_list),
        "page_width": WIDTH_SUMMARY,
    }


def build_list_data(
    nodes: list[dict], status_map: dict[str, dict]
) -> dict[str, Any]:
    rows = []
    online = 0
    # 限制列表行数，避免超大图片
    visible_nodes = nodes[:MAX_LIST_ROWS]
    truncated = len(nodes) - len(visible_nodes)
    for i, n in enumerate(visible_nodes, 1):
        st = status_map.get(n.get("uuid") or "")
        view = build_node_view(n, st, i)
        rows.append(view)
        if view["online"]:
            online += 1
    return {
        "total": len(nodes),
        "online": online,
        "offline": len(visible_nodes) - online,
        "rows": rows,
        "truncated": truncated,
        "page_width": WIDTH_LIST,
    }


def build_group_data(
    nodes: list[dict],
    status_map: dict[str, dict],
    group_query: str = "",
) -> dict[str, Any]:
    buckets: OrderedDict[str, list] = OrderedDict()
    for i, n in enumerate(nodes, 1):
        g = _short((n.get("group") or "").strip(), MAX_GROUP_LEN) or "未分组"
        st = status_map.get(n.get("uuid") or "")
        view = build_node_view(n, st, i)
        buckets.setdefault(g, []).append(view)

    q = (group_query or "").strip().lower()
    sections = []
    for gname, items in buckets.items():
        if q and q not in gname.lower() and gname.lower() != q:
            continue
        # 每组限制行数
        visible = items[:MAX_GROUP_ROWS]
        on = sum(1 for x in visible if x["online"])
        sections.append(
            {
                "name": esc(gname, MAX_GROUP_LEN + 4),
                "total": len(items),
                "online": on,
                "offline": len(visible) - on,
                "rows": visible,
                "truncated": len(items) - len(visible),
            }
        )

    return {
        "title": esc(
            f"分类 · {group_query}" if group_query else "服务器分类",
            MAX_GROUP_LEN * 2 + 8,
        ),
        "sections": sections,
        "section_count": len(sections),
        "total": sum(s["total"] for s in sections),
        "page_width": WIDTH_GROUP,
    }


DEFAULT_BG_URL = "https://mygo.pp.ua/"


def safe_bg_url(url: str) -> str:
    """校验背景图 URL；不合法返回空字符串（由模板使用 fallback）。"""
    if not url:
        return ""
    ok, cleaned = is_safe_bg_url(url)
    if not ok:
        return ""
    return cleaned


def screenshot_options(width: int, quality: str = "ultra") -> dict:
    """高清大图截图参数。"""
    level = (quality or "ultra").lower()
    if level not in ("normal", "high", "ultra"):
        level = "ultra"
    return {
        "full_page": True,
        "type": "png",
        "viewport_width": int(width),
        "viewport_height": 480,
        "device_scale_factor_level": level,
        # 允许背景图加载
        "animations": "allow",
    }


# ---------- 二次元玻璃拟态 ----------

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  margin: 0; padding: 0; width: 100%;
  background: #12081a;
  color: #f8f4ff;
  font-family: "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
    "Noto Sans SC", sans-serif;
  -webkit-font-smoothing: antialiased;
}
.page {
  position: relative;
  width: 100%;
  overflow: hidden;
  min-height: 200px;
}
.bg-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 30%;
  z-index: 0;
  filter: brightness(0.72) saturate(1.15) contrast(1.05);
}
.bg-fallback {
  position: absolute;
  inset: 0;
  z-index: 0;
  background:
    radial-gradient(ellipse 80% 60% at 20% 10%, rgba(244,114,182,.35), transparent 55%),
    radial-gradient(ellipse 70% 50% at 90% 20%, rgba(56,189,248,.28), transparent 50%),
    radial-gradient(ellipse 60% 50% at 50% 100%, rgba(167,139,250,.25), transparent 50%),
    linear-gradient(160deg, #1a0b24 0%, #0d1528 45%, #12081a 100%);
}
.veil {
  position: absolute;
  inset: 0;
  z-index: 1;
  background:
    linear-gradient(180deg, rgba(12,8,24,.42) 0%, rgba(12,8,24,.55) 45%, rgba(12,8,24,.72) 100%),
    radial-gradient(ellipse 90% 70% at 50% 0%, rgba(255,182,220,.12), transparent 60%);
  pointer-events: none;
}
.content {
  position: relative;
  z-index: 2;
  padding: 22px 24px 20px;
}
.glass {
  background: linear-gradient(145deg, rgba(255,255,255,.18), rgba(255,255,255,.06));
  border: 1px solid rgba(255,255,255,.28);
  box-shadow:
    0 8px 32px rgba(20, 8, 40, .35),
    inset 0 1px 0 rgba(255,255,255,.28),
    inset 0 -1px 0 rgba(255,255,255,.04);
  backdrop-filter: blur(18px) saturate(1.35);
  -webkit-backdrop-filter: blur(18px) saturate(1.35);
  border-radius: 18px;
}
.glass-soft {
  background: rgba(18, 12, 32, .38);
  border: 1px solid rgba(255,255,255,.16);
  box-shadow: 0 4px 18px rgba(10, 4, 24, .25);
  backdrop-filter: blur(14px) saturate(1.25);
  -webkit-backdrop-filter: blur(14px) saturate(1.25);
  border-radius: 14px;
}

.h {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 14px;
  padding: 14px 16px;
}
.brand .eyebrow {
  font-size: 12px;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: #f9a8d4;
  font-weight: 750;
  margin-bottom: 4px;
  text-shadow: 0 0 12px rgba(249,168,212,.45);
}
.h h1 {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -.03em;
  color: #fff;
  text-shadow: 0 2px 12px rgba(0,0,0,.35);
}
.h .sub {
  font-size: 14px;
  color: rgba(255,255,255,.72);
  margin-top: 4px;
  text-shadow: 0 1px 6px rgba(0,0,0,.3);
}
.pills { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.pill {
  padding: 9px 14px;
  border-radius: 14px;
  background: rgba(255,255,255,.14);
  border: 1px solid rgba(255,255,255,.26);
  text-align: center;
  min-width: 70px;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.25);
}
.pill b {
  display: block;
  font-size: 21px;
  font-weight: 800;
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
  color: #fff;
  text-shadow: 0 1px 8px rgba(0,0,0,.25);
}
.pill span {
  font-size: 12px;
  color: rgba(255,255,255,.7);
  margin-top: 2px;
  display: block;
}
.pill.g b { color: #86efac; text-shadow: 0 0 10px rgba(134,239,172,.4); }
.pill.r b { color: #fda4af; text-shadow: 0 0 10px rgba(253,164,175,.4); }
.pill.c b { color: #7dd3fc; text-shadow: 0 0 10px rgba(125,211,252,.45); }
.pill.p b { color: #d8b4fe; text-shadow: 0 0 10px rgba(216,180,254,.45); }
.pill.y b { color: #fde68a; text-shadow: 0 0 10px rgba(253,230,138,.4); }

.ggrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.gcard {
  padding: 14px 16px;
  position: relative;
  overflow: hidden;
}
.gcard::before {
  content: "";
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: linear-gradient(180deg, #f9a8d4, #67e8f9);
  border-radius: 3px;
}
.gcard .n {
  font-size: 17px;
  font-weight: 760;
  margin-bottom: 8px;
  color: #fff;
  padding-left: 8px;
  text-shadow: 0 1px 8px rgba(0,0,0,.3);
}
.gcard .m {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: rgba(255,255,255,.72);
  margin-bottom: 6px;
  padding-left: 8px;
}
.gcard .avg {
  font-size: 13px;
  color: #a5f3fc;
  font-weight: 680;
  margin-bottom: 8px;
  padding-left: 8px;
  text-shadow: 0 0 8px rgba(165,243,252,.35);
}
.bar {
  height: 7px;
  border-radius: 99px;
  background: rgba(255,255,255,.14);
  overflow: hidden;
  margin-left: 8px;
  border: 1px solid rgba(255,255,255,.12);
}
.bar i {
  display: block;
  height: 100%;
  border-radius: 99px;
  background: linear-gradient(90deg, #f9a8d4, #67e8f9 55%, #c4b5fd);
  box-shadow: 0 0 10px rgba(249,168,212,.45);
}

.table-wrap { padding: 8px 12px 6px; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th {
  text-align: left;
  font-size: 12px;
  color: rgba(255,255,255,.62);
  font-weight: 680;
  padding: 0 6px 9px;
  border-bottom: 1px solid rgba(255,255,255,.14);
  letter-spacing: .03em;
}
td {
  padding: 9px 6px;
  font-size: 14px;
  border-bottom: 1px solid rgba(255,255,255,.07);
  vertical-align: middle;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(255,255,255,.92);
}
tr:last-child td { border-bottom: none; }
.num {
  width: 28px;
  color: rgba(255,255,255,.5);
  font-variant-numeric: tabular-nums;
  font-size: 13px;
}
.name-cell { min-width: 0; }
.name {
  font-weight: 720;
  color: #fff;
  font-size: 14px;
  text-shadow: 0 1px 6px rgba(0,0,0,.25);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.name-sub {
  margin-top: 2px;
  font-size: 12px;
  color: rgba(255,255,255,.58);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.grp { color: rgba(255,255,255,.68); font-size: 13px; }
.metric-col { text-align: right; width: 60px; }
th.metric-col { text-align: right; }
.dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-right: 5px;
  vertical-align: middle;
}
.dot.on {
  background: #4ade80;
  box-shadow: 0 0 0 3px rgba(74,222,128,.22), 0 0 10px rgba(74,222,128,.55);
}
.dot.off {
  background: #fb7185;
  box-shadow: 0 0 0 3px rgba(251,113,133,.18), 0 0 10px rgba(251,113,133,.4);
}
.pct {
  font-variant-numeric: tabular-nums;
  font-weight: 740;
  color: #f1e9ff;
}
.pct.warn { color: #fcd34d; }
.pct.crit { color: #fb7185; }
.off-txt { color: rgba(255,255,255,.38); }

.sec {
  margin-top: 14px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 4px;
}
.sec:first-of-type { margin-top: 2px; }
.sec h2 {
  font-size: 17px;
  font-weight: 760;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 8px;
  text-shadow: 0 1px 8px rgba(0,0,0,.3);
}
.sec h2::before {
  content: "";
  width: 4px; height: 16px;
  border-radius: 2px;
  background: linear-gradient(180deg, #f9a8d4, #67e8f9);
  display: inline-block;
  box-shadow: 0 0 8px rgba(249,168,212,.5);
}
.sec .meta { font-size: 13px; color: rgba(255,255,255,.7); }
.sec-box { padding: 6px 8px 4px; margin-bottom: 10px; }

.dhead {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
  gap: 14px;
  padding: 18px 20px;
}
.dhead h1 {
  font-size: 38px;
  font-weight: 820;
  color: #fff;
  letter-spacing: -.02em;
  text-shadow: 0 2px 14px rgba(0,0,0,.35);
}
.dhead .sub {
  margin-top: 8px;
  font-size: 23px;
  color: rgba(255,255,255,.78);
  line-height: 1.5;
  font-weight: 520;
}
.badge {
  font-size: 21px;
  font-weight: 760;
  padding: 9px 18px;
  border-radius: 999px;
  white-space: nowrap;
  flex: 0 0 auto;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.badge.on {
  color: #bbf7d0;
  background: rgba(34,197,94,.22);
  border: 1px solid rgba(134,239,172,.45);
  box-shadow: 0 0 14px rgba(74,222,128,.25);
}
.badge.off {
  color: #fecdd3;
  background: rgba(244,63,94,.2);
  border: 1px solid rgba(251,113,133,.4);
}
.tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.tag {
  font-size: 20px;
  padding: 6px 14px;
  border-radius: 999px;
  background: rgba(249,168,212,.18);
  color: #fbcfe8;
  border: 1px solid rgba(249,168,212,.35);
  font-weight: 600;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}
.metric {
  padding: 18px 18px 16px;
  min-height: 124px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.metric .l {
  font-size: 22px;
  color: rgba(255,255,255,.78);
  margin-bottom: 8px;
  font-weight: 680;
  letter-spacing: .04em;
}
.metric .v {
  font-size: 42px;
  font-weight: 860;
  font-variant-numeric: tabular-nums;
  line-height: 1.0;
  text-shadow: 0 0 20px currentColor;
  letter-spacing: -.02em;
}
.metric .h {
  margin-top: 10px;
  font-size: 21px;
  color: rgba(255,255,255,.72);
  line-height: 1.4;
  font-weight: 550;
}
.section-title {
  font-size: 21px;
  font-weight: 760;
  color: #f9a8d4;
  letter-spacing: .1em;
  text-transform: uppercase;
  margin: 6px 2px 12px;
  text-shadow: 0 0 10px rgba(249,168,212,.35);
}
.panel { padding: 16px 18px; margin-bottom: 14px; }
.rows { display: flex; flex-direction: column; gap: 12px; }
.row {
  display: grid;
  grid-template-columns: 58px 1fr 64px;
  gap: 12px;
  align-items: center;
  font-size: 22px;
}
.row .k { color: rgba(255,255,255,.75); font-weight: 680; }
.row .v {
  text-align: right;
  font-weight: 760;
  font-variant-numeric: tabular-nums;
  color: #fff;
  font-size: 22px;
}
.track {
  height: 11px;
  border-radius: 99px;
  background: rgba(255,255,255,.14);
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.1);
}
.fill {
  height: 100%;
  border-radius: 99px;
  background: linear-gradient(90deg, #f9a8d4, #67e8f9 60%, #c4b5fd);
  box-shadow: 0 0 12px rgba(249,168,212,.4);
}
.fill.warn { background: linear-gradient(90deg, #fbbf24, #fb923c); box-shadow: 0 0 10px rgba(251,191,36,.4); }
.fill.crit { background: linear-gradient(90deg, #fb7185, #f43f5e); box-shadow: 0 0 10px rgba(251,113,133,.45); }
.kv {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
}
.kv .item {
  border-radius: 12px;
  padding: 14px 15px;
  background: rgba(255,255,255,.1);
  border: 1px solid rgba(255,255,255,.16);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.kv .item .k {
  font-size: 20px;
  color: rgba(255,255,255,.68);
  margin-bottom: 5px;
  font-weight: 650;
}
.kv .item .v {
  font-size: 22px;
  font-weight: 700;
  color: #fff;
  word-break: break-all;
  line-height: 1.4;
  text-shadow: 0 1px 6px rgba(0,0,0,.2);
}
.empty {
  text-align: center;
  padding: 32px 12px;
  color: rgba(255,255,255,.7);
  font-size: 15px;
}
"""


def _doc(width: int, body: str) -> str:
    """二次元玻璃卡片：随机二次元底图 + 毛玻璃内容层。

    渲染时使用 CSP 限制：
    - default-src 'none'：默认拒绝所有
    - img-src https: data:：背景图仅允许 https 或 data
    - style-src 'unsafe-inline'：内联样式
    - 禁止 script / iframe / 等
    模板里 {{ bg_url }} 必须是经过 safe_bg_url 校验的 https URL 或空串。
    """
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width={width}, height=480">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https: data:; style-src 'unsafe-inline'; font-src https: data:;">
<style>
{CSS}
html, body {{ width: {width}px; max-width: {width}px; }}
.page {{ width: {width}px; max-width: {width}px; }}
</style>
</head>
<body>
<div class="page">
  <div class="bg-fallback"></div>
  {{% if bg_url %}}<img class="bg-img" src="{{{{ bg_url }}}}" alt="" />{{% endif %}}
  <div class="veil"></div>
  <div class="content">
{body}
  </div>
</div>
</body>
</html>"""


TMPL_SUMMARY = _doc(
    WIDTH_SUMMARY,
    """
  <div class="h glass" style="flex-direction:column;align-items:stretch;gap:12px;">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
      <div class="brand">
        <div class="eyebrow">MyGO · Server</div>
        <h1>服务器概况</h1>
        <div class="sub">{{ group_count }} 个分组 · {{ total }} 台节点 · 在线均 CPU {{ avg_cpu }}% / 内存 {{ avg_ram }}% / 磁盘 {{ avg_disk }}%</div>
      </div>
      <div class="pills">
        <div class="pill"><b>{{ total }}</b><span>总计</span></div>
        <div class="pill g"><b>{{ online }}</b><span>在线</span></div>
        <div class="pill r"><b>{{ offline }}</b><span>离线</span></div>
      </div>
    </div>
    <div class="pills" style="justify-content:flex-start;">
      <div class="pill c"><b>{{ total_cores_label }}</b><span>CPU 总数</span></div>
      <div class="pill p"><b>{{ total_mem }}</b><span>内存总数</span></div>
      <div class="pill y"><b>{{ total_disk }}</b><span>硬盘总数</span></div>
      <div class="pill"><b>{{ used_mem }}</b><span>内存已用</span></div>
      <div class="pill"><b>{{ used_disk }}</b><span>硬盘已用</span></div>
    </div>
  </div>
  {% if groups %}
  <div class="ggrid">
    {% for g in groups %}
    <div class="gcard glass-soft">
      <div class="n">{{ g.name }}</div>
      <div class="m">
        <span>在线 {{ g.online }}/{{ g.total }}</span>
        <span>离线 {{ g.offline }}</span>
      </div>
      <div class="avg">{{ g.cores_label }} · 内存 {{ g.mem_label }} · 盘 {{ g.disk_label }} · 均CPU {{ g.avg_cpu }}%</div>
      <div class="bar"><i style="width:{{ g.online_pct }}%"></i></div>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty glass-soft">暂无服务器</div>
  {% endif %}
""",
)

TMPL_LIST = _doc(
    WIDTH_LIST,
    """
  <div class="h glass">
    <div class="brand">
      <div class="eyebrow">MyGO · Server</div>
      <h1>服务器列表</h1>
      <div class="sub">共 {{ total }} 台</div>
    </div>
    <div class="pills">
      <div class="pill g"><b>{{ online }}</b><span>在线</span></div>
      <div class="pill r"><b>{{ offline }}</b><span>离线</span></div>
    </div>
  </div>
  {% if rows %}
  <div class="table-wrap glass-soft">
  <table>
    <colgroup>
      <col style="width:28px">
      <col style="width:42%">
      <col style="width:58px">
      <col style="width:54px">
      <col style="width:54px">
      <col style="width:54px">
      <col style="width:78px">
    </colgroup>
    <thead>
      <tr>
        <th class="num">#</th>
        <th>名称 / 分组</th>
        <th>状态</th>
        <th class="metric-col">负载</th>
        <th class="metric-col">内存</th>
        <th class="metric-col">磁盘</th>
        <th class="metric-col">网速↓</th>
      </tr>
    </thead>
    <tbody>
    {% for r in rows %}
      <tr>
        <td class="num">{{ r.index }}</td>
        <td class="name-cell">
          <div class="name">{{ r.region }} {{ r.name }}</div>
          <div class="name-sub">{{ r.group }}</div>
        </td>
        <td>{% if r.online %}<span class="dot on"></span>在线{% else %}<span class="dot off"></span>离线{% endif %}</td>
        {% if r.online %}
        <td class="pct metric-col {% if r.cpu >= 90 %}crit{% elif r.cpu >= 70 %}warn{% endif %}">{{ r.cpu }}%</td>
        <td class="pct metric-col {% if r.ram_p >= 90 %}crit{% elif r.ram_p >= 75 %}warn{% endif %}">{{ r.ram_p }}%</td>
        <td class="pct metric-col {% if r.disk_p >= 90 %}crit{% elif r.disk_p >= 80 %}warn{% endif %}">{{ r.disk_p }}%</td>
        <td class="grp metric-col">{{ r.net_in }}</td>
        {% else %}
        <td class="off-txt metric-col">—</td>
        <td class="off-txt metric-col">—</td>
        <td class="off-txt metric-col">—</td>
        <td class="off-txt metric-col">—</td>
        {% endif %}
      </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
  {% else %}
  <div class="empty glass-soft">暂无服务器</div>
  {% endif %}
""",
)

TMPL_DETAIL = _doc(
    WIDTH_DETAIL,
    """
  <div class="dhead glass">
    <div>
      <div class="eyebrow" style="font-size:20px;letter-spacing:.18em;text-transform:uppercase;color:#f9a8d4;font-weight:750;margin-bottom:5px;text-shadow:0 0 12px rgba(249,168,212,.45);">MyGO · Node</div>
      <h1>{{ node.region }} {{ node.name }}</h1>
      <div class="sub">{{ node.group }} · {{ node.os }} · {{ node.arch }} / {{ node.virt }}</div>
      {% if node.tags %}
      <div class="tags">{% for t in node.tags %}<span class="tag">{{ t }}</span>{% endfor %}</div>
      {% endif %}
    </div>
    {% if node.online %}
    <span class="badge on">● 在线</span>
    {% else %}
    <span class="badge off">● 离线</span>
    {% endif %}
  </div>

  {% if node.online %}
  <div class="metrics">
    <div class="metric glass-soft">
      <div class="l">CPU 使用率</div>
      <div class="v" style="color:#7dd3fc">{{ node.cpu }}%</div>
      <div class="h">{{ node.cores_label }}</div>
    </div>
    <div class="metric glass-soft">
      <div class="l">内存</div>
      <div class="v" style="color:#d8b4fe">{{ node.ram_p }}%</div>
      <div class="h">{{ node.ram_label }}</div>
    </div>
    <div class="metric glass-soft">
      <div class="l">磁盘</div>
      <div class="v" style="color:#86efac">{{ node.disk_p }}%</div>
      <div class="h">{{ node.disk_label }}</div>
    </div>
  </div>

  <div class="panel glass-soft">
    <div class="section-title">负载</div>
    <div class="rows">
      <div class="row">
        <div class="k">CPU</div>
        <div class="track"><div class="fill {% if node.cpu >= 90 %}crit{% elif node.cpu >= 70 %}warn{% endif %}" style="width:{{ node.cpu_w }}%"></div></div>
        <div class="v">{{ node.cpu }}%</div>
      </div>
      <div class="row">
        <div class="k">内存</div>
        <div class="track"><div class="fill {% if node.ram_p >= 90 %}crit{% elif node.ram_p >= 75 %}warn{% endif %}" style="width:{{ node.ram_w }}%"></div></div>
        <div class="v">{{ node.ram_p }}%</div>
      </div>
      <div class="row">
        <div class="k">磁盘</div>
        <div class="track"><div class="fill {% if node.disk_p >= 90 %}crit{% elif node.disk_p >= 80 %}warn{% endif %}" style="width:{{ node.disk_w }}%"></div></div>
        <div class="v">{{ node.disk_p }}%</div>
      </div>
      {% if node.has_swap %}
      <div class="row">
        <div class="k">交换</div>
        <div class="track"><div class="fill {% if node.swap_p >= 80 %}warn{% endif %}" style="width:{{ node.swap_w }}%"></div></div>
        <div class="v">{{ node.swap_p }}%</div>
      </div>
      {% endif %}
    </div>
  </div>

  <div class="panel glass-soft">
    <div class="section-title">硬件 · CPU</div>
    <div class="kv">
      <div class="item"><div class="k">型号</div><div class="v">{{ node.cpu_name }}</div></div>
      <div class="item"><div class="k">核心</div><div class="v">{{ node.cores_label }} · {{ node.arch }}</div></div>
      <div class="item"><div class="k">虚拟化</div><div class="v">{{ node.virt }}</div></div>
      <div class="item"><div class="k">系统负载</div><div class="v">{{ node.load }}{% if node.temp %} · {{ node.temp }}{% endif %}</div></div>
      {% if node.gpu %}
      <div class="item"><div class="k">GPU</div><div class="v">{{ node.gpu }}</div></div>
      {% endif %}
      <div class="item"><div class="k">系统 / 内核</div><div class="v">{{ node.os }} · {{ node.kernel }}</div></div>
    </div>
  </div>

  <div class="panel glass-soft">
    <div class="section-title">网络 · 运行</div>
    <div class="kv">
      <div class="item"><div class="k">网速</div><div class="v">↓ {{ node.net_in }} · ↑ {{ node.net_out }}</div></div>
      <div class="item"><div class="k">累计流量</div><div class="v">↓ {{ node.traffic_down }} · ↑ {{ node.traffic_up }}</div></div>
      <div class="item"><div class="k">进程 / 连接</div><div class="v">{% if node.process is not none %}{{ node.process }} 进程{% else %}-{% endif %} · TCP {{ node.tcp if node.tcp is not none else '-' }} / UDP {{ node.udp if node.udp is not none else '-' }}</div></div>
      <div class="item"><div class="k">运行时间</div><div class="v">{{ node.uptime }}</div></div>
      {% if node.has_swap %}
      <div class="item"><div class="k">交换分区</div><div class="v">{{ node.swap_label }}</div></div>
      {% endif %}
      {% if node.remark %}
      <div class="item"><div class="k">备注</div><div class="v">{{ node.remark }}</div></div>
      {% endif %}
    </div>
  </div>
  {% else %}
  <div class="panel glass-soft">
    <div class="kv" style="margin-bottom:8px;">
      <div class="item"><div class="k">CPU</div><div class="v">{{ node.cpu_name }} · {{ node.cores_label }}</div></div>
      <div class="item"><div class="k">规格</div><div class="v">内存 {{ node.mem_total }} · 磁盘 {{ node.disk_total }}</div></div>
      <div class="item"><div class="k">系统</div><div class="v">{{ node.os }}</div></div>
      <div class="item"><div class="k">架构</div><div class="v">{{ node.arch }} / {{ node.virt }}</div></div>
    </div>
    <div class="empty">该服务器当前离线，暂无实时负载</div>
  </div>
  {% endif %}
""",
)

TMPL_GROUP = _doc(
    WIDTH_GROUP,
    """
  <div class="h glass">
    <div class="brand">
      <div class="eyebrow">MyGO · Server</div>
      <h1>{{ title }}</h1>
      <div class="sub">{{ section_count }} 个分组 · {{ total }} 台</div>
    </div>
  </div>
  {% if sections %}
    {% for s in sections %}
    <div class="sec">
      <h2>{{ s.name }}</h2>
      <div class="meta">在线 {{ s.online }}/{{ s.total }}{% if s.offline %} · 离线 {{ s.offline }}{% endif %}</div>
    </div>
    <div class="sec-box glass-soft">
      <table>
        <colgroup>
          <col style="width:28px">
          <col style="width:48%">
          <col style="width:58px">
          <col style="width:54px">
          <col style="width:54px">
          <col style="width:54px">
        </colgroup>
        <thead>
          <tr>
            <th class="num">#</th>
            <th>名称</th>
            <th>状态</th>
            <th class="metric-col">负载</th>
            <th class="metric-col">内存</th>
            <th class="metric-col">磁盘</th>
          </tr>
        </thead>
        <tbody>
        {% for r in s.rows %}
          <tr>
            <td class="num">{{ r.index }}</td>
            <td class="name-cell"><div class="name">{{ r.region }} {{ r.name }}</div></td>
            <td>{% if r.online %}<span class="dot on"></span>在线{% else %}<span class="dot off"></span>离线{% endif %}</td>
            {% if r.online %}
            <td class="pct metric-col {% if r.cpu >= 90 %}crit{% elif r.cpu >= 70 %}warn{% endif %}">{{ r.cpu }}%</td>
            <td class="pct metric-col {% if r.ram_p >= 90 %}crit{% elif r.ram_p >= 75 %}warn{% endif %}">{{ r.ram_p }}%</td>
            <td class="pct metric-col {% if r.disk_p >= 90 %}crit{% elif r.disk_p >= 80 %}warn{% endif %}">{{ r.disk_p }}%</td>
            {% else %}
            <td class="off-txt metric-col">—</td>
            <td class="off-txt metric-col">—</td>
            <td class="off-txt metric-col">—</td>
            {% endif %}
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    {% endfor %}
  {% else %}
  <div class="empty glass-soft">未找到分组</div>
  {% endif %}
""",
)
