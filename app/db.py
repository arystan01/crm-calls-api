import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def connect():
    path = os.environ.get("DB_PATH", "crm.db")
    # isolation_level=None значит, что транзакции открываем сами через BEGIN IMMEDIATE
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction():
    """Транзакция на запись.

    BEGIN IMMEDIATE сразу берет блокировку на запись всей базы.
    Пока один запрос проверяет слот и вставляет встречу, второй ждет своей очереди,
    поэтому два одновременных запроса не могут оба пройти проверку.
    """
    conn = connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


@contextmanager
def reading():
    """Соединение только для чтения."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def migrate():
    """Применяет SQL-файлы из migrations/, которые еще не применены."""
    conn = connect()
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
    done = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}
    for file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if file.name not in done:
            conn.executescript(file.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (name) VALUES (?)", (file.name,))
    conn.close()
