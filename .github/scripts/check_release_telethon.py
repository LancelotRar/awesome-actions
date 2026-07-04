#!/usr/bin/env python3
"""
check_release_telethon — Unified entry point for GitHub release monitoring.

Environment variables
---------------------
REPO                  GitHub repo (e.g. "fish2018/webhtv")
DATA_FILE             Path to persist last release updated_at
NOTIFY_TITLE          Display title for notification
NOTIFY_GROUP_URL      Telegram group invite URL
GITHUB_TOKEN          GitHub token (optional, for API auth)
TG_BOT_TOKEN          Telegram bot token (from @BotFather)
TG_CHAT_ID            Target chat ID(s), comma-separated (numeric only)
TG_API_ID             Telegram API ID
TG_API_HASH           Telegram API hash
FORCE                 "true" to re-notify even if already notified (optional)
ASSET_INCLUDE         Include filter: comma=OR, plus=AND (e.g. ".apk,.exe+bettbox")
                      Empty = include all assets (optional)
ASSET_EXCLUDE         Exclude filter (same syntax, takes priority) (optional)

Design
------
Thin orchestrator.  All domain logic lives in sibling modules
(``github_client``, ``telegram_client``, ``storage``) so that
additional workflows can be added without duplicating code.
"""

import asyncio
import os
import sys

from persist import read_last_updated, write_last_updated
from github_api import fetch_latest_release
from notifier import notify, TelegramConfig

# ---------------------------------------------------------------------------
# Config (read from environment)
# ---------------------------------------------------------------------------

REPO = os.environ["REPO"]
DATA_FILE = os.environ["DATA_FILE"]
NOTIFY_TITLE = os.environ["NOTIFY_TITLE"]
NOTIFY_GROUP_URL = os.environ["NOTIFY_GROUP_URL"]
FORCE = os.environ.get("FORCE", "").lower() == "true"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
ASSET_INCLUDE = os.environ.get("ASSET_INCLUDE", "")
ASSET_EXCLUDE = os.environ.get("ASSET_EXCLUDE", "")

for var in ("TG_BOT_TOKEN", "TG_CHAT_ID", "TG_API_ID", "TG_API_HASH"):
    if not os.environ.get(var):
        print(f"::error::Missing required env var: {var}")
        sys.exit(1)

chat_ids = [c.strip() for c in os.environ["TG_CHAT_ID"].split(",") if c.strip()]
if not chat_ids:
    print("::error::TG_CHAT_ID is empty after splitting")
    sys.exit(1)

# Convert to int early so malformed values fail fast.
try:
    TG_CHAT_IDS: list[int] = [int(c) for c in chat_ids]
except ValueError as e:
    print(f"::error::TG_CHAT_ID contains non-numeric value: {e}")
    sys.exit(1)

TG_CONFIG = TelegramConfig(
    bot_token=os.environ["TG_BOT_TOKEN"],
    chat_ids=TG_CHAT_IDS,
    api_id=int(os.environ["TG_API_ID"]),
    api_hash=os.environ["TG_API_HASH"],
    notify_title=NOTIFY_TITLE,
    notify_group_url=NOTIFY_GROUP_URL,
)

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def main() -> None:
    try:
        last_updated = read_last_updated(DATA_FILE)
        release = fetch_latest_release(REPO, GITHUB_TOKEN)

        if release is None:
            print("No releases yet — exiting normally")
            sys.exit(0)

        latest_updated = release.get("updated_at", "")
        rel_name = release.get("name") or release["tag_name"]

        print(
            f"Last Updated: {last_updated}  |  "
            f"Latest Updated: {latest_updated}  |  "
            f"Release: {rel_name}  |  Force: {FORCE}"
        )

        if not FORCE and latest_updated == last_updated:
            print("No new release — exiting")
            sys.exit(0)

        print("New release found, proceeding …")

        ok = await notify(release, TG_CONFIG, GITHUB_TOKEN,
                              ASSET_INCLUDE, ASSET_EXCLUDE)
        if not ok:
            print("::error::Notification failed — will retry on next run")
            sys.exit(1)

        write_last_updated(DATA_FILE, latest_updated)
        print(f"Release data persisted: {latest_updated[:19]}")
    except (RuntimeError, ValueError) as e:
        print(f"::error::{e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
