"""Source records behind a citation, and the advanced read-only query."""


from fastapi import APIRouter, HTTPException, Request

from agent.core.db import read_rows
from agent.tools.warehouse_sql import run_sql
from agent.web.common import _KEYS

router = APIRouter()


@router.get("/api/record")
def record(table: str, key: str) -> dict:
    """The full source row(s) behind a citation, read as the read-only role from the source tables. A call session has
    one row per status event (CONNECTED, DISPOSED, ...): all of them are returned."""
    expr = _KEYS.get(table)
    if not expr:
        raise HTTPException(400, "Unknown source table")
    schema, name = table.split(".")
    rows = read_rows(f'SELECT * FROM "{schema}"."{name}" WHERE {expr} = %s ORDER BY 1 LIMIT 50', (key,))
    if not rows:
        raise HTTPException(404, "Record not found")
    return {"table": table, "key_column": expr.split("::")[0].split(" || ")[0] if "||" not in expr else "dialer_code:call_session_id", "record": rows[0], "rows": rows}


@router.post("/api/sql")
async def sql(request: Request) -> dict:
    """Ad-hoc read-only SELECT through the warehouse SQL tool (read-only role, keyword filter, timeout)."""
    body = await request.json()
    try:
        out = run_sql(str(body.get("query", "")), max_rows=int(body.get("max_rows", 500)))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:  # database errors: show the message, not a stack trace
        diag = getattr(exc, "diag", None)
        raise HTTPException(400, (diag.message_primary if diag and diag.message_primary else str(exc)))
    cols = list(out["rows"][0]) if out["rows"] else []
    return {"columns": cols, "rows": [list(r.values()) for r in out["rows"]], "truncated": out["truncated"]}

