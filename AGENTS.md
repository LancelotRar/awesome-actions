# Awesome-actions — AGENTS.md

## 仓库用途

GitHub Actions 工作流集合，用于监控第三方仓库 Release 并通过 Telegram 推送通知。
当前只有一个活跃工作流：`check-release-webhtv.yml`（监控 fish2018/webhtv）。

## 目录结构

```
.github/
├── workflows/
│   └── check-release-webhtv.yml       # 活跃工作流
├── scripts/
│   ├── check_release_telethon.py       # 活跃脚本（Telethon/MTProto）
│   └── requirements.txt                # 当前仅依赖 telethon
├── data/
│   └── last-release-webhtv.txt         # 持久化最后检查的 release updated_at
└── old/                                # 从旧仓库迁移的存档，不要启用或删除
    ├── workflows/
    │   ├── check-release-webhtv.yml         # 旧版 HTTP Bot API 方案
    │   └── check-release-silent1566.yml
    ├── scripts/check_release.py             # 旧版 HTTP Bot API 脚本
    └── data/
```

**权限要求**：`contents: write` — 工作流需要 push data 文件回仓库。

**.gitignore 忽略项**：`__pycache__/`, `*.pyc`, `*.egg-info/`, `dist/`, `build/`, `.venv/`, `Thumbs.db`, `.DS_Store`, `.vscode/`, `.idea/`

## 关键约束

### 1. Telethon 版本敏感

当前脚本 `check_release_telethon.py` 使用 Telethon **v1 API**（`TelegramClient`, `StringSession`, `client.start(bot_token=...)`）。
Telethon 已于 2026-02 从 GitHub 迁移至 [Codeberg](https://codeberg.org/Lonami/Telethon)。
PyPI 上的最新版本可能已是 v2（含 breaking changes）。

- 修改依赖或脚本前，**必须先确认当前 PyPI `telethon` 版本是否与 v1 API 兼容**。
- 如果因 Telethon 升级导致脚本报错，降级或适配 API。

### 2. Action 版本号可能不存在

工作流使用 `actions/checkout@v6`、`actions/setup-python@v6`、`actions/cache@v6`。
这些不是官方发布的版本——如果 workflow run 报 "not found"，降级到实际的最新稳定版。

### 3. 新旧两套脚本共存

| 脚本 | 方案 | 所需密钥 |
|---|---|---|
| `check_release_telethon.py`（当前） | Telethon MTProto | TG_BOT_TOKEN + TG_API_ID + TG_API_HASH |
| `old/scripts/check_release.py`（旧） | HTTP Bot API | 仅 TG_BOT_TOKEN |

不要混用。新增 monitor 时按需选方案。

### 4. 新增 monitor 的模式

每个 monitor = 1 个 workflow + 1 个 Python 脚本 + 1 个 data 文件，外加对应的 GitHub Secrets。

## 运行方式

当前工作流仅通过 **`workflow_dispatch`** 手动触发（无定时调度）。
在 GitHub UI → Actions → "Check fish2018/webhtv Release" → Run workflow。
可选传入 `force: true` 强制重复通知已检查过的版本。

## 脚本行为

1. 从 `last-release-*.txt` 读取上次检查的 `updated_at`
2. 调用 GitHub API 获取对应仓库的最新 release
3. 对比时间戳，无新 release 则 exit(0)
4. 有新版时：下载 APK asset → 通过 Telethon 发送到 TG 群（多群逗号分隔）
5. 将最新 `updated_at` 写回 data 文件并 push 到仓库

## Secrets

| 名称 | 用途 | 所属 |
|---|---|---|
| `TG_BOT_TOKEN_03BOT` | WebHTV 通知的 Bot Token | LancelotRar |
| `TG_CHAT_ID_WEBHTV` | WebHTV 通知的目标群 ID（逗号分隔） | LancelotRar |
| `TG_API_ID` | Telegram API ID | LancelotRar |
| `TG_API_HASH` | Telegram API Hash | LancelotRar |
