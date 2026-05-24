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
