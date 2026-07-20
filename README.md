# Komari 探针

[![Version](https://img.shields.io/badge/version-v2.0.0-blue.svg)](https://github.com/beiqi7/astrbot_plugin_komari)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-6c5ce7.svg)](https://github.com/AstrBotDevs/AstrBot)

适用于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的 [Komari](https://github.com/komari-monitor/komari) 服务器监控插件，可在 QQ 等聊天平台中查询服务器概况、节点列表、单机状态和分组信息，并生成高清监控卡片。

> 默认仅 AstrBot 管理员可用。插件优先通过 JSON-RPC2 获取数据，失败时自动回退至 REST API。

## 功能亮点

- **服务器概况**：汇总在线状态、CPU 核心、内存、磁盘和分组在线率
- **节点列表**：展示负载、内存、磁盘、实时网速等关键指标
- **单机详情**：展示 CPU 型号与核心数、系统、负载、网络、流量、连接数和运行时间
- **分组统计**：按 Komari 分组查看节点状态与资源使用情况
- **模糊搜索**：支持节点名称、标签、分组、备注、系统、CPU 型号和 UUID
- **候选选择**：搜索结果存在多个同分节点时，可在 5 分钟内使用序号选择
- **双输出模式**：支持高清图片卡片和纯文本输出
- **玻璃拟态卡片**：默认使用二次元随机背景，支持三档清晰度
- **权限控制**：支持所有人、仅管理员、用户白名单三种模式
- **缓存与冷却**：减少高频指令对 Komari 后端的压力
- **安全加固**：包含 URL 校验、响应体限制、并发限制、HTML 转义、CSP 和日志脱敏

## 效果与数据范围

| 视图 | 展示内容 |
|---|---|
| 概况 | 节点在线数、CPU 核心总数、内存与磁盘用量、分组在线率 |
| 列表 | 节点状态、负载、内存、磁盘、实时上传与下载速度 |
| 单机 | CPU、内存、磁盘、Swap、负载、系统、网络、流量、连接数、运行时间等 |
| 分类 | 各分组节点状态及负载、内存、磁盘使用率 |

CPU 型号与核心信息仅在单机详情卡片中展示。

## 快速开始

### 环境要求

- 已部署并正常运行的 AstrBot
- 可从 AstrBot 所在环境访问的 Komari 面板
- Python 依赖：`aiohttp>=3.9,<4`

### 安装插件

将插件目录复制到 AstrBot 插件目录：

```bash
cp -r astrbot_plugin_komari /path/to/AstrBot/data/plugins/
```

也可以将插件打包为 ZIP，通过 AstrBot WebUI 上传。安装后重载插件或重启 AstrBot。

如依赖未自动安装，可手动执行：

```bash
pip install "aiohttp>=3.9,<4"
```

### 基础配置

在 AstrBot WebUI 中进入：

```text
插件 → Komari 探针 → 插件配置
```

至少填写 Komari 面板地址：

```text
base_url = https://komari.example.com
```

私有面板或需要访问隐藏节点时，可同时填写：

```text
api_key = your_api_key
```

> 配置 API Key 后，`base_url` 必须使用 HTTPS。

### 测试指令

```text
/km
```

配置正确时，机器人会返回服务器概况卡片。

## 指令说明

主指令为 `/km`，也可使用 `/komari`。

| 指令 | 别名 | 功能 |
|---|---|---|
| `/km` | `/km summary`、`/km overview`、`/km 概况` | 查看服务器概况 |
| `/km list` | `/km ls`、`/km 列表` | 查看服务器列表 |
| `/km <关键词>` | — | 模糊搜索并查看单机详情 |
| `/km info <关键词>` | `status`、`st`、`i`、`s`、`信息`、`状态` | 查看单机详情 |
| `/km <序号>` | — | 选择上一次模糊搜索产生的候选节点 |
| `/km group [分组]` | `分类`、`grp`、`g`、`groups` | 查看全部分组或指定分组 |
| `/km help` | `帮助`、`h`、`?` | 查看帮助 |

### 使用示例

```text
/km
/km list
/km DMIT
/km info dmit
/km group
/km group Japan
/km help
```

### 模糊搜索与候选选择

插件可按以下内容搜索节点：

- 节点名称
- 标签
- 分组与区域
- 公开备注或内部备注
- 操作系统
- CPU 型号
- UUID

当搜索到多个同分候选时，机器人会返回候选列表：

```text
1. Tokyo-DMIT
2. LosAngeles-DMIT
```

请在 5 分钟内回复：

```text
/km 1
```

这里的序号优先对应上一次搜索产生的候选列表，而不是 `/km list` 中的全局序号。选择成功后，候选缓存会被清除。

## 配置说明

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| `base_url` | 空 | Komari 面板地址，例如 `https://komari.example.com` |
| `api_key` | 空 | Komari API Key；配置后强制要求 HTTPS |
| `allow_insecure` | `false` | 是否允许 HTTP 或不安全地址，仅建议在可信内网环境使用 |
| `timeout` | `10` | 请求超时，范围 `1～60` 秒 |
| `cache_ttl` | `5` | 节点与状态缓存时间，范围 `0～300` 秒 |
| `cooldown_seconds` | `5` | 同一会话的指令冷却时间，范围 `0～60` 秒；管理员免冷却 |
| `show_hidden` | `false` | 是否显示 Komari 隐藏节点 |
| `output_mode` | `card` | 输出模式：`card` 图片卡片或 `text` 纯文本 |
| `permission_mode` | `admin` | 权限模式：`all`、`admin` 或 `whitelist` |
| `allowed_users` | 空 | 白名单用户 ID，使用英文逗号或换行分隔 |
| `image_quality` | `ultra` | 卡片清晰度：`normal`、`high` 或 `ultra` |
| `bg_url` | `https://mygo.pp.ua/` | 卡片背景图地址，必须使用 HTTPS |

### 输出模式

#### 图片卡片

```text
output_mode = card
```

插件通过 AstrBot 的 HTML 渲染能力生成玻璃拟态图片卡片。若卡片渲染失败，会自动回退为纯文本结果。

#### 纯文本

```text
output_mode = text
```

适合不支持图片卡片、希望减少流量或排查渲染问题的环境。

### 卡片清晰度

| 取值 | 缩放倍率 | 适用场景 |
|---|---:|---|
| `normal` | 1× | 节省流量、快速响应 |
| `high` | 1.3× | 清晰度与体积平衡 |
| `ultra` | 1.8× | 默认值，适合高清查看 |

清晰度越高，生成图片越大，渲染时间与流量占用也会相应增加。

### 背景图

默认背景地址：

```text
https://mygo.pp.ua/
```

自定义 `bg_url` 时需满足：

- 必须使用 HTTPS
- 不得指向内网或本机地址
- 禁止 `file:`、`data:`、`javascript:` 等协议
- 校验失败时自动回退到默认背景或纯色背景

## 权限控制

### `all`

所有用户均可调用插件指令：

```text
permission_mode = all
```

### `admin`

仅 AstrBot 管理员可用，也是默认值：

```text
permission_mode = admin
```

管理员 ID 可在 AstrBot 的管理员配置中设置。

### `whitelist`

仅管理员和白名单用户可用：

```text
permission_mode = whitelist
allowed_users = 123456789,987654321
```

用户可使用 `/sid` 查看自己的 ID。多个 ID 可用英文逗号、空格、分号或换行分隔。

未知的 `permission_mode` 会按 **fail-closed** 处理：仅管理员可用，避免配置错误意外开放权限。

## 缓存与限流

### 短期缓存

`cache_ttl` 控制节点和状态数据的缓存时间：

```text
cache_ttl = 5
```

适当提高缓存时间可降低 Komari 后端压力；设置为 `0` 可关闭缓存。

### 会话冷却

`cooldown_seconds` 控制同一会话两次指令之间的最短间隔：

```text
cooldown_seconds = 5
```

- 管理员不受冷却限制
- 设置为 `0` 可关闭冷却
- 冷却按用户或会话维度生效

## 安全设计

插件默认采用较保守的安全策略：

- 默认 `permission_mode=admin`，避免公开指令放大后端请求
- 配置 API Key 时强制要求 Komari 地址使用 HTTPS
- 禁止在 `base_url` 中使用 `user:pass@host` 形式的认证信息
- HTTP 响应体最大限制为 5 MiB
- 节点列表最多处理 200 个节点
- RPC 失败回退 REST 时，单次最多请求 60 个节点
- REST 状态请求并发上限为 8
- 列表卡片单页最多 100 行，分组内最多 80 行
- HTML 模板中的远端字符串统一转义
- 卡片模板启用严格 CSP
- 背景图仅允许安全的 HTTPS 公网地址
- HTTP 请求禁用环境代理继承
- 禁止 HTTP 重定向，降低被诱导访问内网的风险
- RPC 失败后进入 30 秒冷却，避免重复请求异常接口
- 群聊中只返回简短错误，详细信息写入脱敏日志

不建议在公网环境开启 `allow_insecure`。

## 数据获取机制

插件会优先使用 Komari JSON-RPC2 接口获取节点与状态数据。在 RPC 不可用或请求失败时，会自动回退至 REST API：

```text
JSON-RPC2 → 失败 → REST API
```

节点信息与状态数据会根据 `cache_ttl` 进行短期缓存，以减少重复请求。

## 常见问题

### 提示“未配置面板地址”

检查插件配置中的 `base_url`，确认已填写完整协议和域名：

```text
https://komari.example.com
```

### 配置 API Key 后无法连接

确认：

1. `base_url` 使用 HTTPS
2. API Key 与 Komari 后台配置一致
3. AstrBot 所在服务器能够访问 Komari 面板
4. 地址中没有 `user:pass@` 形式的认证信息

### 内网 HTTP 面板无法访问

仅在可信环境中开启：

```text
allow_insecure = true
```

如果同时配置了 API Key，即使开启该选项仍必须使用 HTTPS。

### 卡片无法生成

可以先切换为纯文本模式排查数据连接：

```text
output_mode = text
```

如果纯文本正常，请检查 AstrBot 的 HTML 渲染环境、背景图连通性和相关日志。

### 背景图片不显示

- 确认 `bg_url` 使用 HTTPS
- 确认地址未指向本机或内网
- 确认图片服务允许 AstrBot 所在服务器访问
- 校验失败时插件会自动使用默认背景或纯色背景

### 找不到节点

插件支持模糊搜索。可以先查看完整列表：

```text
/km list
```

然后使用节点名称、标签、分组或 UUID 搜索。

### 指令提示操作太快

等待提示中的剩余时间，或由管理员调整：

```text
cooldown_seconds = 5
```

管理员不受冷却限制。

## 项目结构

```text
astrbot_plugin_komari/
├── main.py             # 插件入口、指令、权限与响应流程
├── komari_client.py    # Komari REST / JSON-RPC2 客户端
├── cards.py            # 卡片数据与 HTML 模板
├── formatter.py        # 纯文本格式化
├── utils.py            # 校验、缓存、冷却和通用工具
├── _conf_schema.json   # AstrBot WebUI 配置定义
├── metadata.yaml       # 插件元数据
├── requirements.txt    # Python 依赖
└── LICENSE             # MIT 许可证
```

## 版本信息

- 当前版本：`v2.0.0`
- 作者：`serenite`
- 项目地址：[beiqi7/astrbot_plugin_komari](https://github.com/beiqi7/astrbot_plugin_komari)

## License

本项目基于 [MIT License](./LICENSE) 开源。
