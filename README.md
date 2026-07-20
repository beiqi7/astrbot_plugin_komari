# astrbot_plugin_komari

AstrBot 插件：对接 [Komari](https://github.com/komari-monitor/komari) 探针，在 QQ 群发送**高清服务器监控卡片**。

**Author:** serenite  
**Version:** v2.0.0  
**Repo:** https://github.com/beiqi7/astrbot_plugin_komari

- 概况汇总 CPU 核心、内存、硬盘总数与已用量，按分组展示在线率  
- 列表显示 负载 / 内存 / 磁盘 百分比与网速；分类显示 负载 / 内存 / 磁盘 百分比  
- **CPU 型号与核心仅在单机卡片**展示  
- UI：**二次元玻璃拟态**，背景默认 `https://mygo.pp.ua/`（随机图，仅允许 HTTPS）  
- 模糊搜索名称 / 标签 / 分组 / UUID；多匹配时 `/km 1` 选候选（5 分钟有效）  
- **安全**：权限默认 `admin`；会话冷却 + 短期缓存；HTTP 响应体上限 5 MB；并发受限；HTML 转义 + CSP；URL 校验；错误脱敏

## 指令

| 指令 | 别名 | 功能 |
|------|------|------|
| `/km` | `komari` | 服务器概况（在线 + 硬件总量 + 分组在线率） |
| `/km list` | `ls` / `列表` | 服务器列表（负载/内存/磁盘/网速） |
| `/km <名称\|标签\|UUID>` | `info` / `status` / `st` / `i` / `s` | 单机详情（含 CPU 型号、核心、负载、网络、运行时间） |
| `/km <序号>` | — | 选择上次多匹配候选（5 分钟内有效） |
| `/km group [分组]` | `分类` / `grp` / `g` / `groups` | 分类信息（按分组聚合） |
| `/km help` | `帮助` / `h` / `?` | 帮助 |

子指令示例：

```
/km              # 概况
/km list         # 列表
/km DMIT         # 模糊搜索 DMIT 节点
/km 1            # 选择上次候选列表中的第 1 个
/km group Japan  # 查看分组名含 Japan 的分类
/km info dmit    # 等同 /km dmit
```

## 后台配置

| 项 | 说明 |
|----|------|
| `base_url` | Komari 面板地址（必填）；带 API Key 时强制 HTTPS，禁止 `user:pass@` |
| `api_key` | 可选；填写后 `base_url` 强制 HTTPS |
| `allow_insecure` | 允许 HTTP/内网地址（默认 `false`）；带 API Key 时仍强制 HTTPS |
| `timeout` | 请求超时，1~60 秒，默认 10 |
| `cache_ttl` | 节点/状态短期缓存秒数，0~300，默认 5（设 0 关闭） |
| `cooldown_seconds` | 会话冷却秒数，0~60，默认 5；管理员免冷却 |
| `output_mode` | `card` / `text` |
| `image_quality` | `normal` / `high` / **`ultra`（默认高清）** |
| `bg_url` | 背景图接口，**必须 HTTPS**，禁止内网/file/data/javascript 协议 |
| `permission_mode` | `all` 所有人 · **`admin` 仅管理员（默认）** · `whitelist` 白名单；未知值 fail-closed |
| `allowed_users` | 白名单用户 ID（逗号分隔，可用 `/sid` 查看） |
| `show_hidden` | 是否显示隐藏节点 |

### 权限说明

- **all**：群里所有人可用  
- **admin**（默认）：仅 AstrBot 管理员（配置 -> 其他 -> 管理员 ID）  
- **whitelist**：仅 `allowed_users` 中的 ID；**管理员始终可用**
- 未知值按 **fail-closed** 处理：仅管理员可用（避免配置错误导致权限放开）

## 安全

- 默认 `permission_mode=admin`，避免公开指令放大后端请求
- 会话级冷却 + 短期缓存，降低对 Komari 的请求量
- HTTP 响应体限制 5 MB，避免被恶意/异常响应拖垮内存
- 节点列表上限 200，REST recent 并发上限 8，单次最多 60 节点
- 列表单页 ≤100 行，分组每组 ≤80 行，防止生成超大图片
- 所有进入 HTML 模板的远端字符串经 `html.escape` 转义，并加严格 CSP
- `bg_url` 仅允许 HTTPS、拒绝内网/file/data/javascript 协议
- 群聊只回复简短错误信息；详细错误进日志并脱敏（屏蔽 Token/Bearer/敏感 query）
- `aiohttp.ClientSession` 设置 `trust_env=False`，避免宿主机代理意外生效
- 禁止 HTTP 重定向，避免被诱导到内网
- RPC 失败后 30 秒冷却，避免每条命令重试失败的 RPC

## 安装

```bash
# 放到 AstrBot 插件目录
cp -r astrbot_plugin_komari /path/to/AstrBot/data/plugins/
```

或在 WebUI 上传 zip。填写 `base_url` 后重载即可。

## License

MIT（见 [LICENSE](./LICENSE)）
