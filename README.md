# Budget Tracker MCP (FastAPI + SQLite)

This project is a **Budget Tracker MCP server** that:
- exposes a simple expense database (SQLite by default)
- provides REST endpoints (FastAPI)
- **automatically exposes those endpoints as MCP tools** via `fastapi-mcp` at `/mcp`

## Features
- Add expense
- List expenses (filter by date range / category)
- Delete expense
- Monthly summary (totals by category + grand total)
- Health check

## Endpoints (REST)
- `GET /health`
- `POST /expenses`
- `GET /expenses?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&category=food`
- `DELETE /expenses/{id}`
- `GET /summary/monthly?year=2025&month=12`

## MCP
- MCP endpoint is mounted at:
  - `GET/POST /mcp`

Your MCP-compatible client/agent connects to `/mcp` and will see the above endpoints as tools.

## Local Run

### 1) Create venv & install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run server
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 3) Test quickly
```bash
curl http://localhost:8000/health
```

Add an expense:
```bash
curl -X POST http://localhost:8000/expenses \
  -H "Content-Type: application/json" \
  -d '{"amount":75000,"category":"food","description":"lunch","expense_date":"2025-12-23"}'
```

## Configure Database
By default the server creates/uses `budget.db` in the project directory.

You can override:
- `DB_PATH` (e.g. `/data/budget.db` on Railway persistent volume)

Example:
```bash
export DB_PATH=/tmp/budget.db
```

## Deploy to Railway

1. Create a new Railway project from this repo / zip upload.
2. Set Start Command:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
3. (Optional) Add a **Volume** and set:
   - `DB_PATH=/data/budget.db`

### Procfile
A Procfile is included for convenience:
- `web: uvicorn main:app --host 0.0.0.0 --port $PORT`

## Next Up (optional enhancements)
- Add `user_id` for multi-user tracking
- Add `income` table
- Add budgets per category
- Add receipt OCR ingestion (Telegram bot + LLM parsing)
