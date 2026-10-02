#!/usr/bin/env python3
"""
Restore PLUXO users from a backup file through admin API.

Examples:
  python restore_users_backup.py --file data/backups/users_backup_latest.txt --webhook-secret "$PLUXO_WEBHOOK_SECRET"
  python restore_users_backup.py --file users_backup_latest.json --username NBTNate --password '...'
  python restore_users_backup.py --file users_backup_latest.txt --replace-all-users --send-telegram-backup --webhook-secret "$PLUXO_WEBHOOK_SECRET"
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib import error, request

DEFAULT_API_BASE = "https://web-production-0e4f1.up.railway.app"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Restore users from backup (.txt/.json) via Pluxo admin API."
    )
    p.add_argument(
        "--api",
        default=os.environ.get("PLUXO_API_URL", DEFAULT_API_BASE),
        help="API base URL",
    )
    p.add_argument(
        "--file",
        required=True,
        help="Path to users backup file (.txt or .json)",
    )
    p.add_argument(
        "--webhook-secret",
        default=os.environ.get("PLUXO_WEBHOOK_SECRET", ""),
        help="Optional X-Webhook-Secret (recommended for direct admin access)",
    )
    p.add_argument(
        "--username",
        default=os.environ.get("PLUXO_ADMIN_USER", ""),
        help="Optional site admin username (if not using webhook secret)",
    )
    p.add_argument(
        "--password",
        default=os.environ.get("PLUXO_ADMIN_PASS", ""),
        help="Optional site admin password (if not using webhook secret)",
    )
    p.add_argument(
        "--show-password-input",
        action="store_true",
        help="Use visible password input instead of hidden getpass prompt",
    )
    p.add_argument(
        "--replace-all-users",
        action="store_true",
        help="Dangerous: clear existing users before restore",
    )
    p.add_argument(
        "--send-telegram-backup",
        action="store_true",
        help="After restore, push fresh backup to Telegram now",
    )
    return p.parse_args()


def _api_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> tuple[int, dict[str, Any]]:
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    body: bytes | None = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = request.Request(url=url, data=body, method=method, headers=req_headers)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200))
            raw = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace")
    except error.URLError as exc:
        raise RuntimeError(f"Network error calling {url}: {exc.reason}") from exc
    if not raw.strip():
        return status, {}
    try:
        parsed = json.loads(raw)
        return status, parsed if isinstance(parsed, dict) else {"data": parsed}
    except json.JSONDecodeError:
        return status, {"error": f"Non-JSON response (HTTP {status})"}


def _multipart_form_data(
    fields: dict[str, str],
    files: list[tuple[str, str, str, bytes]],
) -> tuple[str, bytes]:
    boundary = f"----pluxo-restore-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, val in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8")
        )
        chunks.append(val.encode("utf-8"))
        chunks.append(b"\r\n")
    for field_name, filename, content_type, data in files:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{filename}"\r\n'
            ).encode("utf-8")
        )
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return f"multipart/form-data; boundary={boundary}", b"".join(chunks)


def _api_multipart(
    url: str,
    *,
    fields: dict[str, str],
    files: list[tuple[str, str, str, bytes]],
    headers: dict[str, str] | None = None,
    timeout: float = 90.0,
) -> tuple[int, dict[str, Any]]:
    content_type, body = _multipart_form_data(fields, files)
    req_headers = {"Accept": "application/json", "Content-Type": content_type}
    if headers:
        req_headers.update(headers)
    req = request.Request(url=url, data=body, method="POST", headers=req_headers)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200))
            raw = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace")
    except error.URLError as exc:
        raise RuntimeError(f"Network error calling {url}: {exc.reason}") from exc
    if not raw.strip():
        return status, {}
    try:
        parsed = json.loads(raw)
        return status, parsed if isinstance(parsed, dict) else {"data": parsed}
    except json.JSONDecodeError:
        return status, {"error": f"Non-JSON response (HTTP {status})"}


def _login_token(
    api_base: str, username: str, password: str, webhook_secret: str
) -> str:
    headers = {"X-Webhook-Secret": webhook_secret} if webhook_secret else {}
    status, data = _api_json(
        f"{api_base}/api/auth/login",
        method="POST",
        payload={"username": username.strip().lower(), "password": password},
        headers=headers,
    )
    if status != 200 or not data.get("success"):
        raise RuntimeError(data.get("error") or f"Login failed (HTTP {status})")
    tok = str(data.get("token") or "").strip()
    if not tok:
        raise RuntimeError("Login succeeded but token missing.")
    return tok


def main() -> int:
    args = _parse_args()
    api_base = str(args.api or "").strip().rstrip("/")
    if not api_base:
        print("ERROR: --api is required", file=sys.stderr)
        return 1

    backup_file = Path(str(args.file or "").strip()).expanduser()
    if not backup_file.is_file():
        print(f"ERROR: backup file not found: {backup_file}", file=sys.stderr)
        return 1

    headers: dict[str, str] = {}
    webhook_secret = str(args.webhook_secret or "").strip()
    if webhook_secret:
        headers["X-Webhook-Secret"] = webhook_secret

    username = str(args.username or "").strip()
    password = str(args.password or "")
    if username and not password:
        if args.show_password_input:
            password = input("Admin password (visible): ").strip()
        else:
            try:
                password = getpass.getpass("Admin password (hidden): ").strip()
            except Exception:
                password = input("Admin password (visible): ").strip()
    if username and password:
        try:
            token = _login_token(api_base, username, password, webhook_secret)
        except Exception as exc:
            print(f"ERROR: login failed: {exc}", file=sys.stderr)
            return 1
        headers["Authorization"] = f"Bearer {token}"

    try:
        raw = backup_file.read_bytes()
    except OSError as exc:
        print(f"ERROR: could not read backup file: {exc}", file=sys.stderr)
        return 1

    status, data = _api_multipart(
        f"{api_base}/api/admin/backup/restore-users",
        fields={
            "replace_all_users": "true" if args.replace_all_users else "false",
            "send_telegram_backup": "true" if args.send_telegram_backup else "false",
        },
        files=[
            (
                "file",
                backup_file.name,
                "application/json" if backup_file.suffix.lower() == ".json" else "text/plain",
                raw,
            )
        ],
        headers=headers,
    )

    print(json.dumps(data, indent=2))
    if status != 200 or not data.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

