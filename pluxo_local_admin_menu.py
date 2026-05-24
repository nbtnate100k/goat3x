#!/usr/bin/env python3
"""
Local admin menu for PLUXO state.json.

Runs entirely on your laptop (no Railway / Telegram required) and updates
the same local `data/state.json` using pluxo_backend's own helpers so the
logic matches your bot/server behavior.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_backend():
    # Local menu mode should never start Telegram polling.
    os.environ.setdefault("DISABLE_TELEGRAM_BOT", "1")
    os.environ.setdefault("PLUXO_TELEGRAM_POLL", "never")
    try:
        return importlib.import_module("pluxo_backend")
    except Exception as exc:
        print(f"Failed to import pluxo_backend.py: {exc}")
        raise


def _ask(prompt: str) -> str:
    return input(prompt).strip()


def _ask_float(prompt: str, *, min_value: float | None = None) -> float | None:
    raw = _ask(prompt)
    if not raw:
        return None
    try:
        val = float(raw)
    except ValueError:
        print("Invalid number.")
        return None
    if min_value is not None and val < min_value:
        print(f"Value must be >= {min_value}.")
        return None
    return val


def _pause() -> None:
    input("\nPress Enter to continue...")


def _clean_pasted_path(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    # Support pasted quoted Windows paths:
    # "C:\Users\motod\Downloads\cards_with_bin_details.txt"
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    return s


def _prompt_existing_file(prompt: str) -> Path | None:
    while True:
        raw = _ask(prompt)
        if not raw:
            print("Cancelled.")
            return None
        if raw.lower() in {"0", "q", "quit", "cancel"}:
            print("Cancelled.")
            return None
        cleaned = _clean_pasted_path(raw)
        p = Path(cleaned).expanduser()
        if p.is_file():
            return p
        print(f"File not found: {p}")
        print('Try again, or type "0" to cancel.')


def _choose_stock_base(pb) -> str:
    catalog = list(getattr(pb, "STOCK_BASE_CATALOG", []) or [])
    if not catalog:
        return "BLACKJACK_BASE"
    print("\nPick stock base:")
    for i, row in enumerate(catalog, start=1):
        bid = str(row.get("id") or "").strip().upper()
        lab = str(row.get("label") or bid)
        print(f"{i}. {lab} ({bid})")
    while True:
        raw = _ask("Base number [1]: ")
        if not raw:
            return str(catalog[0].get("id") or "BLACKJACK_BASE").strip().upper()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(catalog):
                return str(catalog[idx - 1].get("id") or "BLACKJACK_BASE").strip().upper()
        # Also allow typing the base id directly.
        typed = raw.strip().upper()
        for row in catalog:
            if typed == str(row.get("id") or "").strip().upper():
                return typed
        print("Invalid base. Choose 1-4 (or type base id).")


def _count_pending_topups(state_obj: dict[str, Any]) -> int:
    tops = state_obj.get("crypto_topups") or {}
    if not isinstance(tops, dict):
        return 0
    n = 0
    for row in tops.values():
        if isinstance(row, dict) and str(row.get("status") or "") == "pending":
            n += 1
    return n


def menu_status(pb) -> None:
    with pb.state_lock:
        users = pb.state.get("users") or {}
        stock = pb.state.get("stock") or []
        topups = pb.state.get("crypto_topups") or {}
        print("\n=== STATUS ===")
        print(f"State path: {pb.STATE_PATH}")
        print(f"Users: {len(users) if isinstance(users, dict) else 0}")
        print(f"Stock rows: {len(stock) if isinstance(stock, list) else 0}")
        print(f"Topups: {len(topups) if isinstance(topups, dict) else 0}")
        print(f"Pending topups: {_count_pending_topups(pb.state)}")


def menu_users(pb) -> None:
    rows: list[tuple[str, float, float, bool]] = []
    with pb.state_lock:
        users = pb.state.get("users") or {}
        if isinstance(users, dict):
            for uname, rec in users.items():
                if not isinstance(rec, dict):
                    continue
                u = pb.norm_user(str(uname))
                bal = float(rec.get("balance", 0) or 0)
                tr = float(rec.get("totalRecharge", 0) or 0)
                registered = bool(rec.get("pwd_hash"))
                rows.append((u, bal, tr, registered))
    rows.sort(key=lambda x: (-x[1], x[0]))
    print("\n=== USERS (top 200 by balance) ===")
    if not rows:
        print("No users yet.")
        return
    for u, bal, tr, reg in rows[:200]:
        mark = "Y" if reg else "N"
        print(f"{u:20}  balance=${bal:8.2f}  totalRecharge=${tr:8.2f}  registered={mark}")
    if len(rows) > 200:
        print(f"... +{len(rows) - 200} more")


def menu_load_user(pb) -> None:
    username = pb.norm_user(_ask("Username: "))
    if not username:
        print("Username required.")
        return
    amt = _ask_float("Amount to add (empty to view only): ", min_value=0.0)
    if amt is None:
        with pb.state_lock:
            rec = pb.get_balance_record(username)
            bal = float(rec.get("balance", 0) or 0)
            tr = float(rec.get("totalRecharge", 0) or 0)
            reg = bool(rec.get("pwd_hash"))
        print(f"{username} -> balance=${bal:.2f}, totalRecharge=${tr:.2f}, registered={reg}")
        return
    if amt <= 0:
        print("Amount must be greater than 0.")
        return
    with pb.state_lock:
        out = pb.credit_user_deposit_unlocked(
            username,
            amt,
            log_line=f"[local-menu] /load {username} +${amt:.2f}",
            uid=None,
        )
        pb.save_state()
    bonus = float(out.get("referral_bonus") or 0)
    extra = f" (+${bonus:.2f} referral bonus)" if bonus > 0 else ""
    print(f"Loaded ${amt:.2f}{extra} -> {username}. New balance=${float(out['balance']):.2f}")


def menu_set_balance(pb) -> None:
    username = pb.norm_user(_ask("Username: "))
    if not username:
        print("Username required.")
        return
    amt = _ask_float("Set balance to: ", min_value=0.0)
    if amt is None:
        return
    with pb.state_lock:
        rec = pb.get_balance_record(username)
        rec["balance"] = round(float(amt), 2)
        pb._action_log_unlocked(f"[local-menu] /setbalance {username} -> ${float(amt):.2f}")
        pb.save_state()
    print(f"{username} balance set to ${float(amt):.2f}")


def menu_remove_balance(pb) -> None:
    username = pb.norm_user(_ask("Username: "))
    if not username:
        print("Username required.")
        return
    amt = _ask_float("Amount to remove: ", min_value=0.0)
    if amt is None:
        return
    with pb.state_lock:
        rec = pb.get_balance_record(username)
        rec["balance"] = round(max(0.0, float(rec.get("balance", 0) or 0) - float(amt)), 2)
        nb = float(rec["balance"])
        pb._action_log_unlocked(
            f"[local-menu] /removebalance {username} -${float(amt):.2f} -> ${nb:.2f}"
        )
        pb.save_state()
    print(f"{username}: removed ${float(amt):.2f} -> ${nb:.2f}")


def menu_add_stock_bulk(pb) -> None:
    p = _prompt_existing_file('Paste stock file path (or drag file here), or "0" to cancel: ')
    if p is None:
        return
    raw = p.read_text(encoding="utf-8", errors="replace")
    cards = pb.parse_stock_cards_bulk(raw)
    if not cards:
        print("No card lines found.")
        return
    print(f"Loaded {len(cards)} card line(s) from {p}")
    # Requested flow: paste stock -> ask price -> ask base (numbered 1..4)
    price = _ask_float("Price per line (e.g. 2.25): ", min_value=0.01)
    if price is None:
        return
    base = _choose_stock_base(pb)
    # User requested no country prompt; stock already carries that context in workflow.
    country = "US"
    if len(cards) > int(pb.STOCK_BATCH_MAX):
        print(f"Too many lines ({len(cards)}). Max is {pb.STOCK_BATCH_MAX}. Split the file.")
        return
    with pb.state_lock:
        known = pb.all_known_stock_bases_unlocked()
        if base not in known:
            print(f"Unknown base '{base}'. Falling back to {pb.default_stock_base_id()}.")
            base = pb.default_stock_base_id()
        added = pb._commit_stock_cards_unlocked(
            cards,
            round(float(price), 2),
            base,
            pb.normalize_stock_upload_country(country),
            log_line=f"[local-menu] stock-bulk +{len(cards)} @ ${float(price):.2f} base={base} country={country}",
            uid=None,
        )
    print(f"Added {added} line(s) -> {base}")


def menu_import_stock_document(pb) -> None:
    p = _prompt_existing_file('Paste inventory document path (.txt), or "0" to cancel: ')
    if p is None:
        return
    forced_base = (_ask("Forced base (optional, Enter to auto): ") or "").strip().upper()
    country = (_ask("Country code [US]: ") or "US").strip().upper()
    price_in = _ask("Price override (optional, Enter to auto/default): ")
    req_price: float | None = None
    if price_in:
        try:
            req_price = round(float(price_in), 2)
        except ValueError:
            print("Invalid price override.")
            return
    doc = p.read_text(encoding="utf-8", errors="replace")
    with pb.state_lock:
        known = set(pb.all_known_stock_bases_unlocked())
        entries, doc_price, perr = pb.parse_stock_inventory_document(
            doc, known, forced_base=forced_base
        )
        if perr:
            print(f"Import error: {perr}")
            return
        if not entries:
            print("No card lines found.")
            return
        if len(entries) > int(pb.STOCK_BATCH_MAX):
            print(f"Too many lines ({len(entries)}). Max is {pb.STOCK_BATCH_MAX}. Split the file.")
            return
        price = req_price if req_price and req_price > 0 else None
        if price is None and doc_price is not None and float(doc_price) > 0:
            price = round(float(doc_price), 2)
        if price is None:
            price = 10.0
        stock = pb.state.setdefault("stock", [])
        stock.clear()
        nid = int(pb.state.get("next_product_id", 1))
        ctry = pb.normalize_stock_upload_country(country)
        sold_pans = pb._load_sold_card_pans()
        skipped_sold = 0
        for base_sel, card in entries:
            if pb._is_card_line_already_sold(card, sold_pans):
                skipped_sold += 1
                continue
            row = pb.build_stock_row_from_line(
                card,
                nid,
                float(price),
                base_sel,
                country_override=ctry,
            )
            stock.append(row)
            nid += 1
        pb.state["next_product_id"] = nid
        try:
            pb.DATA_DIR.mkdir(parents=True, exist_ok=True)
            pb.SHOP_STOCK_DOCUMENT_PATH.write_text(
                doc.replace("\r\n", "\n"), encoding="utf-8"
            )
        except OSError as exc:
            print(f"Could not save shop_stock.txt: {exc}")
            return
        log_line = (
            f"[local-menu] stock-document import {len(stock)} lines @ ${float(price):.2f} country={ctry}"
        )
        if skipped_sold:
            log_line += f" skipped_already_sold={skipped_sold}"
        pb._action_log_unlocked(log_line, uid=None)
        pb.save_state()
    msg = f"Imported {len(stock)} lines @ ${float(price):.2f} (full replace)."
    if skipped_sold:
        msg += f" ({skipped_sold} already-sold skipped â€” see data/sold.txt)"
    print(msg)


def _pending_topups(pb) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pb.state_lock:
        tops = pb.state.get("crypto_topups") or {}
        if isinstance(tops, dict):
            for pid, row in tops.items():
                if not isinstance(row, dict):
                    continue
                if str(row.get("status") or "") != "pending":
                    continue
                rec = dict(row)
                rec["id"] = str(rec.get("id") or pid)
                rows.append(rec)
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


def menu_list_pending_topups(pb) -> None:
    rows = _pending_topups(pb)
    print("\n=== PENDING TOPUPS ===")
    if not rows:
        print("No pending topups.")
        return
    for r in rows[:200]:
        pid = str(r.get("id") or "")
        user = pb.norm_user(str(r.get("site_username") or ""))
        amt = float(r.get("amount_usd", 0) or 0)
        method = str(r.get("method") or "").upper()
        created = str(r.get("created_at") or "")
        print(f"{pid}  user={user:16}  amount=${amt:8.2f}  method={method:3}  created={created}")
    if len(rows) > 200:
        print(f"... +{len(rows)-200} more")


def menu_resolve_topup(pb, accept: bool) -> None:
    pid = _ask("Topup ID (16 chars): ").lower()
    if len(pid) != 16:
        print("Invalid topup id.")
        return
    with pb.state_lock:
        tops = pb.state.get("crypto_topups") or {}
        if not isinstance(tops, dict):
            print("Topup store missing.")
            return
        row = tops.get(pid)
        if not isinstance(row, dict):
            print("Topup not found.")
            return
        if str(row.get("status") or "") != "pending":
            print(f"Topup already {row.get('status')}.")
            return
        user = pb.norm_user(str(row.get("site_username") or ""))
        amt = float(row.get("amount_usd", 0) or 0)
        if accept:
            pb.credit_user_deposit_unlocked(
                user,
                amt,
                log_line=f"[local-menu] topup accept {user} ${amt:.2f} id={pid}",
                uid=None,
            )
            row["status"] = "accepted"
        else:
            row["status"] = "rejected"
            pb._action_log_unlocked(
                f"[local-menu] topup reject {user} ${amt:.2f} id={pid}",
                uid=None,
            )
        row["resolved_at"] = pb._utc_now_z()
        row["resolved_by_tg"] = 0
        pb.save_state()
    print(f"{'Accepted' if accept else 'Rejected'} topup {pid}.")


def menu_clear_stock(pb) -> None:
    yn = _ask("Clear ALL stock? Type YES to confirm: ")
    if yn != "YES":
        print("Cancelled.")
        return
    with pb.state_lock:
        pb.state["stock"] = []
        pb._action_log_unlocked("[local-menu] clearstock")
        pb.save_state(merge_stock_from_disk=False)
    print("All stock cleared.")


def menu_reparse_stock_rows(pb) -> None:
    """
    Rebuild state/zip/brand/etc from each row.full_info using current parser logic.
    Keeps id/price/base/refundable, replaces parsed metadata fields.
    """
    yn = _ask("Reparse all current stock rows now? Type YES to confirm: ")
    if yn != "YES":
        print("Cancelled.")
        return
    fixed = 0
    skipped = 0
    with pb.state_lock:
        stock = pb.state.get("stock") or []
        if not isinstance(stock, list) or not stock:
            print("No stock rows to reparse.")
            return
        new_rows: list[dict[str, Any]] = []
        for row in stock:
            if not isinstance(row, dict):
                skipped += 1
                continue
            full_info = str(row.get("full_info") or "").strip()
            if not full_info:
                new_rows.append(row)
                skipped += 1
                continue
            try:
                rid = int(row.get("id"))
            except (TypeError, ValueError):
                skipped += 1
                continue
            base = str(row.get("base") or pb.default_stock_base_id())
            try:
                price = float(row.get("price", 0) or 0)
            except (TypeError, ValueError):
                price = 0.0
            country_override = None
            c_obj = row.get("country")
            if isinstance(c_obj, dict):
                country_override = str(c_obj.get("code") or "").strip().upper() or None
            reparsed = pb.build_stock_row_from_line(
                full_info,
                rid,
                price,
                base,
                country_override=country_override,
            )
            # Preserve explicit flags from existing row if present.
            if "refundable" in row:
                reparsed["refundable"] = bool(row.get("refundable"))
            new_rows.append(reparsed)
            fixed += 1
        pb.state["stock"] = new_rows
        pb._action_log_unlocked(f"[local-menu] reparsed stock rows fixed={fixed} skipped={skipped}")
        pb.save_state()
    print(f"Reparsed stock rows: fixed={fixed}, skipped={skipped}")


def menu_recent_logs(pb) -> None:
    with pb.state_lock:
        logs = list(pb.state.get("action_logs") or [])
    print("\n=== RECENT LOGS ===")
    if not logs:
        print("No logs yet.")
        return
    for row in logs[:60]:
        if not isinstance(row, dict):
            continue
        print(f"{row.get('t','')}  {row.get('line','')}")


def run_menu(pb) -> None:
    actions = {
        "1": ("Status", menu_status),
        "2": ("List users + balances", menu_users),
        "3": ("Load user balance (/load)", menu_load_user),
        "4": ("Set user balance (/setbalance)", menu_set_balance),
        "5": ("Remove user balance (/removebalance)", menu_remove_balance),
        "6": ("Add stock from file (append)", menu_add_stock_bulk),
        "7": ("Import stock document (replace all)", menu_import_stock_document),
        "8": ("List pending topups", menu_list_pending_topups),
        "9": ("Accept pending topup", lambda x: menu_resolve_topup(x, True)),
        "10": ("Reject pending topup", lambda x: menu_resolve_topup(x, False)),
        "11": ("Reparse current stock metadata", menu_reparse_stock_rows),
        "12": ("Clear all stock", menu_clear_stock),
        "13": ("Recent action logs", menu_recent_logs),
    }
    while True:
        print("\n" + "=" * 66)
        print("PLUXO LOCAL ADMIN MENU (offline-safe)")
        print(f"State file: {pb.STATE_PATH}")
        print("=" * 66)
        for k in sorted(actions.keys(), key=lambda x: int(x)):
            print(f"{k:>2}. {actions[k][0]}")
        print(" 0. Exit")
        choice = _ask("\nSelect: ")
        if choice == "0":
            print("Bye.")
            return
        action = actions.get(choice)
        if not action:
            print("Invalid choice.")
            continue
        try:
            action[1](pb)
        except KeyboardInterrupt:
            print("\nCancelled.")
        except Exception as exc:
            print(f"Error: {exc}")
        _pause()


def main() -> int:
    pb = _load_backend()
    # Ensure local state is loaded from disk before menu starts.
    pb.load_state()
    run_menu(pb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

