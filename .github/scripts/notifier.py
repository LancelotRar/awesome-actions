"""Telegram notification via Telethon — send release alerts with APK assets."""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from telethon import TelegramClient, errors as tg_errors
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename

from github_api import get_apk_assets, stream_asset


@dataclass
class TelegramConfig:
    """Credentials and display settings for Telegram notification."""

    bot_token: str
    chat_ids: list[int] = field(default_factory=list)
    api_id: int = 0
    api_hash: str = ""
    notify_title: str = ""
    notify_group_url: str = ""


def _build_message(asset_name: str, pub_date: str, html_url: str,
                   title: str, group_url: str) -> str:
    """Build the HTML notification text."""
    name = escape(asset_name)
    return (
        f"🚀<b>{title}新版本发布！</b>\n"
        f'📢<a href="{group_url}">TG讨论群</a>\n'
        f"🌀<b>版本：</b><code>{name}</code>\n"
        f"🍾<b>发布时间：</b>{pub_date}\n"
        f'🔗<a href="{html_url}">查看完整Release日志</a>'
    )


async def notify(release_data: dict, cfg: TelegramConfig,
                 github_token: str = "") -> bool:
    """Send a release notification (with APK assets) to every chat in *cfg*.

    Files are streamed from GitHub straight to Telegram CDN (no local
    disk write).  The upload is performed **once** and the same
    ``InputFile`` handles are reused for every target chat.

    Returns ``True`` when all chats were notified successfully.
    """
    # --- build message text ---
    asset_name = release_data.get("name") or release_data["tag_name"]
    pub_date = release_data["published_at"][:10]
    rel_url = release_data["html_url"]
    text = _build_message(asset_name, pub_date, rel_url,
                          cfg.notify_title, cfg.notify_group_url)

    # --- Telethon client ---
    # NOTE: Do NOT use ``async with TelegramClient(…)`` — its
    # ``__aenter__`` calls ``self.start()`` with *no* arguments,
    # which would fall back to interactive phone/token input
    # (impossible in CI).  Manage start/disconnect explicitly.
    print("Starting Telethon client …")
    client = TelegramClient(
        StringSession(), cfg.api_id, cfg.api_hash,
        connection_retries=3,
    )
    try:
        await client.start(bot_token=cfg.bot_token)  # type: ignore[misc]
    except tg_errors.RPCError as e:
        raise RuntimeError(
            f"Telegram auth failed — check TG_API_ID / TG_API_HASH / TG_BOT_TOKEN: {e}"
        ) from e
    print("Telethon client started")

    all_ok = True

    # --- Upload assets once (shared across all chats) ---
    apk_assets = get_apk_assets(release_data)
    uploaded_medias: list | None = None
    file_attrs: list | None = None
    upload_ok = False

    if apk_assets:
        print(f"Fetching & uploading {len(apk_assets)} APK assets …", flush=True)

        async def _fetch_and_upload(asset: dict):
            name = asset["name"]
            size = asset["size"]
            size_mb = round(size / 1_048_576, 1)

            print(f"Fetching  {name}  ({size_mb} MB) …", flush=True)
            try:
                resp = await asyncio.to_thread(stream_asset, asset, github_token)
                data = await asyncio.to_thread(resp.read)

                last_pct = [0]

                def _progress(sent: int, total: int) -> None:
                    pct = sent * 100 // total
                    if pct - last_pct[0] < 10 and sent != total:
                        return
                    last_pct[0] = pct
                    sent_mb = sent / 1_048_576
                    total_mb = total / 1_048_576
                    print(f"  Upload: {sent_mb:.1f}/{total_mb:.1f} MB ({pct}%)", flush=True)

                uploaded = await client.upload_file(
                    io.BytesIO(data), file_name=name, file_size=size,
                    progress_callback=_progress,
                )
                print(f"Uploaded  {name}", flush=True)
                return uploaded, [DocumentAttributeFilename(name)]
            except Exception as e:
                print(f"::warning::Failed to process {name}: {e}")
                return None, None

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[_fetch_and_upload(a) for a in apk_assets]),
                timeout=3600,
            )
            medias = [r[0] for r in results if r[0] is not None]
            attrs = [r[1] for r in results if r[1] is not None]
            if medias:
                uploaded_medias = medias
                file_attrs = attrs
                upload_ok = True
                print("All assets ready, sending as album …", flush=True)
        except asyncio.TimeoutError:
            print("::error::Asset processing timeout — skipped", flush=True)
            all_ok = False
    # -------------------------------------------------------------------

    try:
        for raw_cid in cfg.chat_ids:
            try:
                if upload_ok and uploaded_medias:
                    caption_list = [""] * (len(uploaded_medias) - 1) + [text]
                    await client.send_file(
                        raw_cid, list(uploaded_medias),
                        caption=caption_list,
                        parse_mode="html",
                        force_document=True,
                        attributes=file_attrs or [],
                    )
                    print(f"Album sent to  {raw_cid}", flush=True)
                else:
                    await client.send_message(raw_cid, text, parse_mode="html")
                    print(f"Notification sent to  {raw_cid} (no assets)", flush=True)

            except tg_errors.FloodWaitError as e:
                print(
                    f"::error::Flood wait {e.seconds}s on {raw_cid}"
                    " — skipping remaining chats"
                )
                all_ok = False
                break
            except tg_errors.RPCError as e:
                print(f"::error::Telegram RPC error for {raw_cid}: {e}")
                all_ok = False
                continue
            except ValueError as e:
                print(f"::error::Invalid chat ID '{raw_cid}': {e}")
                all_ok = False
                continue
            except Exception as e:
                print(f"::error::Failed to send to {raw_cid}: {e}")
                all_ok = False
                continue
    finally:
        await client.disconnect()  # type: ignore[misc]
        print("Telethon client disconnected")

    return all_ok
