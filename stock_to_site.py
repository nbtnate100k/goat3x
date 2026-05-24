#!/usr/bin/env python3
"""
Upload stock lines from your laptop to the live Pluxo site API.

Example:
  python stock_to_site.py --file stock.txt --price 2.25

Defaults are tuned for your Railway backend:
  API: https://web-production-0e4f1.up.railway.app
  Username: NBTNate
  Base: BLACKJACK_BASE
  Country: US
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_API_BASE = "https://web-production-0e4f1.up.railway.app"
DEFAULT_USERNAME = "NBTNate"
DEFAULT_BASE = "BLACKJACK_BASE"
DEFAULT_COUNTRY = "US"
MAX_LINES_PER_REQUEST = 5000


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload stock lines to Pluxo site admin API."
    )
    parser.add_argument(
        "--api",
        default=os.environ.get("PLUXO_API_URL", DEFAULT_API_BASE),
        help="API base URL (default: Railway backend)",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("PLUXO_ADMIN_USER", DEFAULT_USERNAME),
        help="Admin username",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("PLUXO_ADMIN_PASS", ""),
        help="Admin password (if omitted, prompt securely)",
    )
    parser.add_argument(
        "--show-password-input",
        action="store_true",
        help="Use visible password input instead of hidden getpass prompt",
    )
    parser.add_argument(
        "--file",
        default="",
        help="Path to text file with one card line per row",
    )
    parser.add_argument(
        "--price",
        type=float,
        default=None,
        help="Price per line (example: 2.25)",
    )
    parser.add_argument(
        "--base",
        default=os.environ.get("PLUXO_STOCK_BASE", DEFAULT_BASE),
        help="Base id (BLACKJACK_BASE, MONEYJR_BASE, UHQ_USA_BASE, FOREIGN_RICH_FUCKERS_BASE)",
    )
    parser.add_argument(
        "--country",
        default=os.environ.get("PLUXO_STOCK_COUNTRY", DEFAULT_COUNTRY),
        help="Country code (US, GB, CA, ...)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=int(os.environ.get("PLUXO_CHUNK_SIZE", str(MAX_LINES_PER_REQUEST))),
        help=f"Lines per request (max {MAX_LINES_PER_REQUEST})",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.0,
        help="Seconds to wait between chunk uploads",
    )
    parser.add_argument(
        "--webhook-secret",
        default=os.environ.get("PLUXO_WEBHOOK_SECRET", "pluxo_secret_2024"),
        help="Optional X-Webhook-Secret header",
    )
    parser.add_argument(
        "--verify-products",
        action="store_true",
        help="After upload, fetch /api/products and print total product count",
    )
    return parser.parse_args()


def _api_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 45.0,
) -> tuple[int, dict[str, Any]]:
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    body_bytes: bytes | None = None
    if payload is not None:
        body_bytes = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = request.Request(url=url, data=body_bytes, method=method, headers=req_headers)

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
        return status, {"error": f"Non-JSON response from server (HTTP {status})"}


def _chunk_rows(rows: list[str], size: int) -> list[list[str]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def _read_rows(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    return rows


def _login(api_base: str, username: str, password: str, webhook_secret: str) -> str:
    headers = {"X-Webhook-Secret": webhook_secret} if webhook_secret else {}
    status, data = _api_json(
        f"{api_base}/api/auth/login",
        method="POST",
        payload={"username": username.strip().lower(), "password": password},
        headers=headers,
    )
    if status != 200 or not data.get("success"):
        msg = data.get("error") or f"Login failed (HTTP {status})"
        raise RuntimeError(msg)
    token = str(data.get("token") or "").strip()
    if not token:
        raise RuntimeError("Login succeeded but token is missing in response.")
    return token


def _upload_chunk(
    api_base: str,
    token: str,
    webhook_secret: str,
    rows: list[str],
    *,
    price: float,
    base: str,
    country: str,
) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    if webhook_secret:
        headers["X-Webhook-Secret"] = webhook_secret
    payload = {
        "price": round(float(price), 2),
        "bulk": "\n".join(rows),
        "country": country.upper().strip() or DEFAULT_COUNTRY,
        "system_base": base.upper().strip() or DEFAULT_BASE,
        "base": base.upper().strip() or DEFAULT_BASE,
    }
    status, data = _api_json(
        f"{api_base}/api/admin/stock-bulk",
        method="POST",
        payload=payload,
        headers=headers,
    )
    if status != 200 or not data.get("ok"):
        msg = data.get("error") or f"Upload failed (HTTP {status})"
        raise RuntimeError(msg)
    return int(data.get("added") or 0)


def _verify_products_count(api_base: str) -> int:
    status, data = _api_json(f"{api_base}/api/products", method="GET")
    if status != 200:
        raise RuntimeError(f"/api/products returned HTTP {status}")
    rows = data if isinstance(data, list) else data.get("data", [])
    if not isinstance(rows, list):
        return 0
    return len(rows)


def main() -> int:
    args = _parse_args()

    api_base = str(args.api or "").strip().rstrip("/")
    if not api_base:
        print("ERROR: --api is required", file=sys.stderr)
        return 1

    username = str(args.username or "").strip()
    if not username:
        print("ERROR: --username is required", file=sys.stderr)
        return 1

    password = str(args.password or "")
    if not password:
        if args.show_password_input:
            password = input("Admin password (visible): ").strip()
        else:
            try:
                password = getpass.getpass("Admin password (hidden): ").strip()
            except Exception:
                print("Hidden password prompt failed. Falling back to visible input.")
                password = input("Admin password (visible): ").strip()
    if not password:
        print("ERROR: password is required", file=sys.stderr)
        return 1

    file_path_raw = str(args.file or "").strip()
    if not file_path_raw:
        file_path_raw = input("Path to stock file: ").strip()
    if not file_path_raw:
        print("ERROR: stock file path is required", file=sys.stderr)
        return 1
    stock_file = Path(file_path_raw).expanduser()
    if not stock_file.is_file():
        print(f"ERROR: file not found: {stock_file}", file=sys.stderr)
        return 1

    price = args.price
    if price is None:
        raw_price = input("Price per line (example 2.25): ").strip()
        try:
            price = float(raw_price)
        except ValueError:
            price = None
    if price is None or price <= 0:
        print("ERROR: --price must be a positive number", file=sys.stderr)
        return 1

    chunk_size = int(args.chunk_size or MAX_LINES_PER_REQUEST)
    if chunk_size <= 0:
        print("ERROR: --chunk-size must be > 0", file=sys.stderr)
        return 1
    if chunk_size > MAX_LINES_PER_REQUEST:
        print(
            f"NOTE: chunk-size {chunk_size} is above API max; using {MAX_LINES_PER_REQUEST}."
        )
        chunk_size = MAX_LINES_PER_REQUEST

    rows = _read_rows(stock_file)
    if not rows:
        print("ERROR: no non-empty stock lines found in file", file=sys.stderr)
        return 1

    chunks = _chunk_rows(rows, chunk_size)
    print(f"Loaded {len(rows)} lines from {stock_file}")
    print(f"Uploading in {len(chunks)} chunk(s) to {api_base}")

    try:
        token = _login(api_base, username, password, str(args.webhook_secret or ""))
    except Exception as exc:
        print(f"ERROR: login failed: {exc}", file=sys.stderr)
        return 1

    total_added = 0
    for idx, chunk in enumerate(chunks, start=1):
        try:
            added = _upload_chunk(
                api_base,
                token,
                str(args.webhook_secret or ""),
                chunk,
                price=float(price),
                base=str(args.base or DEFAULT_BASE),
                country=str(args.country or DEFAULT_COUNTRY),
            )
        except Exception as exc:
            print(f"ERROR: chunk {idx}/{len(chunks)} failed: {exc}", file=sys.stderr)
            return 1
        total_added += added
        print(f"Chunk {idx}/{len(chunks)} -> added {added} line(s)")
        if args.pause > 0 and idx < len(chunks):
            time.sleep(float(args.pause))

    print(f"Done. Added total: {total_added} line(s).")

    if args.verify_products:
        try:
            count = _verify_products_count(api_base)
            print(f"Current /api/products total: {count}")
        except Exception as exc:
            print(f"WARNING: could not verify products count: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

