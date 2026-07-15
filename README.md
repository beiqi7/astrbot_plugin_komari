# astrbot_plugin_komari

AstrBot 插件：对接 [Komari](https://github.com/komari-monitor/komari) 探针，在 QQ 群发送**高清服务器监控卡片**。

**Author:** serenite  
**Version:** v1.4.9

- 列表/分类只显示负载百分比；**CPU 型号与核心仅在单机卡片**展示  
- UI：**二次元玻璃拟态**，背景默认 `https://mygo.pp.ua/`（随机图）  
- 模糊搜索名称 / 标签 / 分组；多匹配时 `/km 1` 选候选（5 分钟）  
- `/km` 概况汇总 CPU 核心、内存、硬盘总数  

## 指令

| 指令 | 功能 |
|------|------|
| `/km` | 服务器概况（在线 + 硬件总量 + 分组） |
| `/km list` | 服务器列表 |
| `/km <名称\|标签>` | 单机详情（含 CPU） |
| `/km group [分组]` | 分类信息 |
| `/km help` | 帮助 |

## 后台配置

| 项 | 说明 |
|----|------|
| `base_url` | Komari 面板地址（必填） |
| `api_key` | 可选 |
| `output_mode` | `card` / `text` |
| `image_quality` | `normal` / `high` / **`ultra`（默认高清）** |
| `bg_url` | 背景图接口，默认 `https://mygo.pp.ua/` |
| `permission_mode` | `all` 所有人 · `admin` 仅管理员 · `whitelist` 白名单 |
| `allowed_users` | 白名单用户 ID（逗号分隔，可用 `/sid` 查看） |
| `show_hidden` | 是否显示隐藏节点 |
| `timeout` | 请求超时 |

### 权限说明

- **all**：群里所有人可用  
- **admin**：仅 AstrBot 管理员（配置 → 其他 → 管理员 ID）  
- **whitelist**：仅 `allowed_users` 中的 ID；**管理员始终可用**

## 安装

```bash
# 放到 AstrBot 插件目录
cp -r astrbot_plugin_komari /path/to/AstrBot/data/plugins/
```

或在 WebUI 上传 zip。填写 `base_url` 后重载即可。

## License

MIT
