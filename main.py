import os
import sqlite3
from datetime import date, datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi_mcp import FastApiMCP

APP_NAME = "Budget Tracker MCP"
DB_PATH = os.getenv("DB_PATH", "budget.db")

app = FastAPI(title=APP_NAME, version="1.0.0")

# (Optional) CORS for easier local testing with web UIs
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          amount REAL NOT NULL,
          category TEXT NOT NULL,
          description TEXT,
          expense_date DATE NOT NULL,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    conn.close()

@app.on_event("startup")
def _startup():
    init_db()

class ExpenseCreate(BaseModel):
    amount: float = Field(..., gt=0, description="Expense amount (must be > 0)")
    category: str = Field(..., min_length=1, description="Category, e.g. food, transport")
    description: Optional[str] = Field("", description="Optional description")
    expense_date: Optional[str] = Field(None, description="YYYY-MM-DD; defaults to today")

class ExpenseOut(BaseModel):
    id: int
    amount: float
    category: str
    description: Optional[str]
    expense_date: str
    created_at: str

class DeleteResult(BaseModel):
    status: str
    deleted_id: int

class MonthlySummaryRow(BaseModel):
    category: str
    total: float

class MonthlySummary(BaseModel):
    year: int
    month: int
    currency: str = "IDR"
    grand_total: float
    by_category: List[MonthlySummaryRow]

@app.get("/health")
def health():
    return {"status": "ok", "app": APP_NAME, "db_path": DB_PATH}

@app.post("/expenses", response_model=ExpenseOut)
def add_expense(payload: ExpenseCreate):
    expense_date = payload.expense_date or date.today().isoformat()

    # Basic date validation
    try:
        datetime.strptime(expense_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="expense_date must be YYYY-MM-DD")

    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO expenses (amount, category, description, expense_date) VALUES (?, ?, ?, ?)",
        (payload.amount, payload.category.strip(), (payload.description or "").strip(), expense_date),
    )
    expense_id = cur.lastrowid
    conn.commit()

    row = cur.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    conn.close()

    return ExpenseOut(
        id=row["id"],
        amount=row["amount"],
        category=row["category"],
        description=row["description"],
        expense_date=row["expense_date"],
        created_at=row["created_at"],
    )

@app.get("/expenses", response_model=List[ExpenseOut])
def list_expenses(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (inclusive)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (inclusive)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    def _validate(d: Optional[str], field: str):
        if d is None:
            return
        try:
            datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail=f"{field} must be YYYY-MM-DD")

    _validate(start_date, "start_date")
    _validate(end_date, "end_date")

    sql = "SELECT * FROM expenses WHERE 1=1"
    params = []

    if start_date:
        sql += " AND expense_date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND expense_date <= ?"
        params.append(end_date)
    if category:
        sql += " AND lower(category) = lower(?)"
        params.append(category.strip())

    sql += " ORDER BY expense_date DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    conn = _connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    return [
        ExpenseOut(
            id=r["id"],
            amount=r["amount"],
            category=r["category"],
            description=r["description"],
            expense_date=r["expense_date"],
            created_at=r["created_at"],
        )
        for r in rows
    ]

@app.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense_by_id(expense_id: int):
    conn = _connect()
    cur = conn.cursor()
    row = cur.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    return ExpenseOut(
        id=row["id"],
        amount=row["amount"],
        category=row["category"],
        description=row["description"],
        expense_date=row["expense_date"],
        created_at=row["created_at"],
    )

@app.delete("/expenses/{expense_id}", response_model=DeleteResult)
def delete_expense(expense_id: int):
    conn = _connect()
    cur = conn.cursor()
    row = cur.execute("SELECT id FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Expense not found")

    cur.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
    return DeleteResult(status="deleted", deleted_id=expense_id)

@app.get("/summary/monthly", response_model=MonthlySummary)
def get_monthly_summary(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    currency: str = Query("IDR"),
):
    # Compute month date range in SQL using string formatting
    start = f"{year:04d}-{month:02d}-01"
    # end = last day of month (computed in python)
    if month == 12:
        end_date = date(year + 1, 1, 1) - datetime.resolution
    else:
        end_date = date(year, month + 1, 1) - datetime.resolution

    end = end_date.date().isoformat()

    conn = _connect()
    rows = conn.execute(
        """
        SELECT category, ROUND(SUM(amount), 2) AS total
        FROM expenses
        WHERE expense_date >= ? AND expense_date <= ?
        GROUP BY category
        ORDER BY total DESC;
        """,
        (start, end),
    ).fetchall()

    grand = conn.execute(
        "SELECT ROUND(COALESCE(SUM(amount), 0), 2) AS grand_total FROM expenses WHERE expense_date >= ? AND expense_date <= ?",
        (start, end),
    ).fetchone()
    conn.close()

    by_cat = [MonthlySummaryRow(category=r["category"], total=float(r["total"] or 0)) for r in rows]
    return MonthlySummary(
        year=year,
        month=month,
        currency=currency,
        grand_total=float(grand["grand_total"] or 0),
        by_category=by_cat,
    )

# ---- MCP Mount ----
# fastapi-mcp automatically converts your FastAPI endpoints into MCP tools.
# The MCP server will be available at /mcp
mcp = FastApiMCP(app)
mcp.mount()

# Local dev entrypoint
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
