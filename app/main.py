import sqlite3
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import db
from app.rules import now_utc, fmt


@asynccontextmanager
async def lifespan(app):
    db.migrate()
    yield


app = FastAPI(title="CRM: звонки и встречи", lifespan=lifespan)


# ---------- ошибки ----------

class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status = status
        self.code = code
        self.message = message


def error_response(status, code, message):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(ApiError)
def handle_api_error(request: Request, exc: ApiError):
    return error_response(exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError):
    parts = []
    for e in exc.errors():
        field = ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path"))
        parts.append(f"{field}: {e['msg']}")
    return error_response(422, "validation_error", "; ".join(parts))


@app.exception_handler(sqlite3.IntegrityError)
def handle_integrity_error(request: Request, exc: sqlite3.IntegrityError):
    # Страховка: если проверку в коде что-то пропустило, база все равно не даст записать мусор.
    return error_response(409, "conflict", f"Конфликт данных: {exc}")


# ---------- менеджеры ----------

class ManagerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@app.post("/managers", status_code=201)
def create_manager(body: ManagerIn):
    with db.transaction() as conn:
        cur = conn.execute("INSERT INTO managers (name) VALUES (?)", (body.name.strip(),))
        return {"id": cur.lastrowid, "name": body.name.strip()}


# ---------- организации ----------

CompanyStatus = Literal["new", "no_answer", "refused", "meeting_set"]


class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    bin: str = Field(pattern=r"^\d{12}$", description="БИН, ровно 12 цифр")
    phone: str = Field(pattern=r"^\+?[0-9 ()-]{7,20}$")


@app.post("/companies", status_code=201)
def create_company(body: CompanyIn):
    with db.transaction() as conn:
        same_bin = conn.execute("SELECT id FROM companies WHERE bin = ?", (body.bin,)).fetchone()
        if same_bin:
            raise ApiError(409, "bin_exists", f"Организация с БИН {body.bin} уже есть (id {same_bin['id']})")
        cur = conn.execute(
            "INSERT INTO companies (name, bin, phone, created_at) VALUES (?, ?, ?, ?)",
            (body.name.strip(), body.bin, body.phone.strip(), fmt(now_utc())),
        )
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


@app.get("/companies")
def list_companies(
    status: CompanyStatus | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    where = ""
    params = []
    if status:
        where = "WHERE status = ?"
        params.append(status)

    with db.reading() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM companies {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM companies {where} ORDER BY id LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}
