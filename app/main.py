import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, Field

from app import db
from app.rules import ALMATY, MEETING_LENGTH, fmt, now_utc, working_hours_error


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


# ---------- встречи ----------

class MeetingIn(BaseModel):
    company_id: int
    manager_id: int
    start_at: AwareDatetime  # время без часового пояса pydantic не примет


class MeetingPatch(BaseModel):
    start_at: AwareDatetime | None = None  # перенести на новое время
    status: Literal["cancelled"] | None = None  # или отменить


def get_or_404(conn, table, id, what):
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (id,)).fetchone()
    if row is None:
        raise ApiError(404, "not_found", f"{what} с id {id} не найден(а)")
    return row


def check_slot(conn, company_id, manager_id, start, skip_meeting_id=0):
    """Все проверки перед тем, как поставить встречу на время start.

    skip_meeting_id нужен при переносе, чтобы встреча не конфликтовала сама с собой.
    """
    error = working_hours_error(start)
    if error:
        raise ApiError(422, "outside_working_hours", error)

    now = now_utc()
    if start <= now:
        raise ApiError(422, "in_the_past", "Нельзя назначить встречу на прошедшее время")

    end = start + MEETING_LENGTH

    # Пересечение интервалов [start, end): встреча 10-11 и 11-12 не пересекаются.
    clash = conn.execute(
        """SELECT id, start_at FROM meetings
           WHERE manager_id = ? AND status = 'scheduled' AND id != ?
             AND start_at < ? AND end_at > ?""",
        (manager_id, skip_meeting_id, fmt(end), fmt(start)),
    ).fetchone()
    if clash:
        raise ApiError(
            409, "manager_busy",
            f"У менеджера уже есть встреча #{clash['id']} в {clash['start_at']}, время пересекается",
        )

    # У организации может быть только одна активная встреча (не отмененная и еще не прошедшая).
    active = conn.execute(
        """SELECT id, manager_id, start_at FROM meetings
           WHERE company_id = ? AND status = 'scheduled' AND id != ? AND end_at > ?""",
        (company_id, skip_meeting_id, fmt(now)),
    ).fetchone()
    if active:
        raise ApiError(
            409, "company_has_meeting",
            f"У организации уже есть активная встреча #{active['id']} в {active['start_at']} "
            f"(менеджер {active['manager_id']}). Перенесите или отмените ее.",
        )


def meeting_json(conn, meeting_id):
    row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    history = conn.execute(
        "SELECT action, start_at, created_at FROM meeting_history WHERE meeting_id = ? ORDER BY id",
        (meeting_id,),
    ).fetchall()
    result = dict(row)
    result["history"] = [dict(h) for h in history]
    return result


@app.post("/meetings", status_code=201)
def create_meeting(body: MeetingIn):
    with db.transaction() as conn:
        get_or_404(conn, "companies", body.company_id, "Организация")
        get_or_404(conn, "managers", body.manager_id, "Менеджер")
        check_slot(conn, body.company_id, body.manager_id, body.start_at)

        start = fmt(body.start_at)
        end = fmt(body.start_at + MEETING_LENGTH)
        now = fmt(now_utc())
        cur = conn.execute(
            """INSERT INTO meetings (company_id, manager_id, start_at, end_at, original_start_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (body.company_id, body.manager_id, start, end, start, now),
        )
        conn.execute(
            "INSERT INTO meeting_history (meeting_id, action, start_at, created_at) VALUES (?, 'created', ?, ?)",
            (cur.lastrowid, start, now),
        )
        return meeting_json(conn, cur.lastrowid)


@app.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: int):
    with db.reading() as conn:
        get_or_404(conn, "meetings", meeting_id, "Встреча")
        return meeting_json(conn, meeting_id)


@app.patch("/meetings/{meeting_id}")
def update_meeting(meeting_id: int, body: MeetingPatch):
    if (body.start_at is None) == (body.status is None):
        raise ApiError(422, "validation_error", "Передайте ровно одно поле: start_at (перенос) или status=cancelled (отмена)")

    with db.transaction() as conn:
        meeting = get_or_404(conn, "meetings", meeting_id, "Встреча")
        if meeting["status"] == "cancelled":
            raise ApiError(409, "meeting_cancelled", "Встреча уже отменена, ее нельзя менять")
        if meeting["end_at"] <= fmt(now_utc()):
            raise ApiError(409, "meeting_passed", "Встреча уже прошла, ее нельзя менять")

        now = fmt(now_utc())
        if body.status == "cancelled":
            conn.execute("UPDATE meetings SET status = 'cancelled' WHERE id = ?", (meeting_id,))
            conn.execute(
                "INSERT INTO meeting_history (meeting_id, action, start_at, created_at) VALUES (?, 'cancelled', ?, ?)",
                (meeting_id, meeting["start_at"], now),
            )
        else:
            check_slot(conn, meeting["company_id"], meeting["manager_id"], body.start_at, skip_meeting_id=meeting_id)
            start = fmt(body.start_at)
            end = fmt(body.start_at + MEETING_LENGTH)
            # original_start_at не трогаем, история пишется отдельной строкой
            conn.execute("UPDATE meetings SET start_at = ?, end_at = ? WHERE id = ?", (start, end, meeting_id))
            conn.execute(
                "INSERT INTO meeting_history (meeting_id, action, start_at, created_at) VALUES (?, 'rescheduled', ?, ?)",
                (meeting_id, start, now),
            )
        return meeting_json(conn, meeting_id)


@app.get("/managers/{manager_id}/schedule")
def manager_schedule(manager_id: int, date: date):
    """Встречи менеджера за день. День считаем по Алматы: с 00:00 до 24:00 местного времени."""
    day_start = datetime(date.year, date.month, date.day, tzinfo=ALMATY)
    day_end = day_start + timedelta(days=1)

    with db.reading() as conn:
        manager = get_or_404(conn, "managers", manager_id, "Менеджер")
        rows = conn.execute(
            """SELECT m.id, m.company_id, c.name AS company_name, m.start_at, m.end_at, m.original_start_at
               FROM meetings m JOIN companies c ON c.id = m.company_id
               WHERE m.manager_id = ? AND m.status = 'scheduled' AND m.start_at >= ? AND m.start_at < ?
               ORDER BY m.start_at""",
            (manager_id, fmt(day_start), fmt(day_end)),
        ).fetchall()
    return {
        "manager_id": manager_id,
        "manager_name": manager["name"],
        "date": date.isoformat(),
        "timezone": "Asia/Almaty",
        "meetings": [dict(r) for r in rows],
    }
