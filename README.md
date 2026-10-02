# PLUXO

Flask backend with HTML storefront and Telegram admin tooling.

## Railway

Deploy steps, env vars, volumes, and Telegram constraints: **[RAILWAY.md](./RAILWAY.md)**

Config-as-code: [`railway.json`](./railway.json) · Dependencies: [`requirements.txt`](./requirements.txt) · Local env template: [`env.example`](./env.example)

## Local dev

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
# copy env.example → .env and fill secrets
python pluxo_backend.py
```

## Health

- **`GET /pluxo-ok`** — liveness probe
- **`GET /telegram-status`** — Telegram env/thread diagnostics

## Backup + purchase exports

- Backend writes account backup files to `data/backups/`:
  - `users_backup_latest.json`
  - `users_backup_latest.txt`
- Backup includes username, password hash, and balance fields.
- A background sender pushes `users_backup_latest.txt` to owner/admin Telegram chats every hour (`PLUXO_BACKUP_PUSH_INTERVAL_SECONDS`).
- On successful checkout, the web client auto-downloads a `.txt` receipt with purchased full lines so buyers can keep their own copy if the shop resets.
- Restore endpoint (admin protected): `POST /api/admin/backup/restore-users`
  - accepts multipart `file` (`.txt` / `.json`) or JSON `{ "users": [...] }`
  - optional `replace_all_users=true` to wipe+restore after a reset
- CLI helper: `python restore_users_backup.py --file data/backups/users_backup_latest.txt --webhook-secret <secret>`
