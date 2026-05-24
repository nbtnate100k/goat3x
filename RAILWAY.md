# Deploy Pluxo on Railway

Pluxo is a **Flask** app exposed as **`pluxo_backend:app`**, served with **Gunicorn** at **`0.0.0.0:$PORT`**.

## Quick setup

1. **Create a Railway project** and connect this repo (or push from GitHub).
2. **Service root**: leave as the repo root (`pluxo_backend.py`, `requirements.txt`, and `railway.json` must be visible).
3. **Railway reads** [`railway.json`](./railway.json): Railpack builds from `requirements.txt`, then runs Gunicorn. The platform healthcheck uses **`GET /pluxo-ok`** (120s timeout).
4. **Set variables** in the service settings (minimum below). Copy from [`env.example`](./env.example) as a checklist.

### Required variables (production)

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot API token (@BotFather) |
| `OWNER_TELEGRAM_ID` | Numeric Telegram user ID of the owner |
| `AUTH_SECRET_KEY` | Secret for sessions / auth (set a long random string) |
| `PLUXO_WEBHOOK_SECRET` | Shared secret used by integrations / webhooks |

Do **not** commit real tokens.

### Recommended for Telegram + web sharing one database

Telegram polling and HTTP must agree on **`state.json`**.

- Attach a **[Railway Volume](https://docs.railway.com/guides/volumes)** to the service, mount path **`/app/data`**  
  **or**
- Set **`PLUXO_STATE_PATH=/app/data/state.json`** and ensure **`/app/data`** is on a persistent volume.

Without persistence, **`data/state.json`** is rebuilt on redeploy.

### Scaling and Telegram long polling

**Only one** process may poll `getUpdates` per bot token. If Telegram returns **409 Conflict**, stop the duplicate poller elsewhere.

- Use **one Gunicorn worker** (`railway.json` / `Procfile` already use `--workers 1`).
- If you scale to **more than one replica** with the same token, disable the bot on all but one (**`DISABLE_TELEGRAM_BOT=1`**) or keep **replicas = 1**.

Optional: **`PLUXO_TELEGRAM_POLL=never`** on extra workers when you deliberately run multiple workers later (normally avoid multiple workers here).

### Optional

- **`PORT`** — Railway sets `PORT` automatically; you normally **do not** need to define it.

## Sanity checks after deploy

- Open **`https://<your-domain>/pluxo-ok`** — JSON with `"pluxo": true`.
- Open **`https://<your-domain>/telegram-status`** — confirms token/owner/disabled flags and spawn result.

## Manual start (fallback)

Matches [`Procfile`](./Procfile):

```bash
pip install -r requirements.txt
gunicorn pluxo_backend:app --bind "0.0.0.0:${PORT:-5000}" --workers 1 --threads 4 --timeout 120 --access-logfile -
```

Python version for builds is pinned in [`runtime.txt`](./runtime.txt).
