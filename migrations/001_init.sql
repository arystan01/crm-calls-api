-- Все время храним в UTC строкой вида 2030-01-07T05:00:00Z.
-- Такие строки сравниваются как обычный текст, поэтому проверки пересечения можно делать прямо в SQL.

CREATE TABLE managers (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE companies (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    bin        TEXT NOT NULL UNIQUE,
    phone      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'new',  -- new, no_answer, refused, meeting_set (результат последнего звонка)
    created_at TEXT NOT NULL
);

CREATE TABLE meetings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id        INTEGER NOT NULL REFERENCES companies(id),
    manager_id        INTEGER NOT NULL REFERENCES managers(id),
    start_at          TEXT NOT NULL,
    end_at            TEXT NOT NULL,
    original_start_at TEXT NOT NULL,                     -- на какое время встречу назначили в первый раз
    status            TEXT NOT NULL DEFAULT 'scheduled', -- scheduled, cancelled
    created_at        TEXT NOT NULL
);

-- Каждое действие со встречей: создание, перенос, отмена. Отсюда видна вся история.
CREATE TABLE meeting_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id),
    action     TEXT NOT NULL,  -- created, rescheduled, cancelled
    start_at   TEXT NOT NULL,  -- время встречи после этого действия
    created_at TEXT NOT NULL
);

CREATE TABLE calls (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    result     TEXT NOT NULL,  -- no_answer, refused, meeting_set
    meeting_id INTEGER REFERENCES meetings(id),
    comment    TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_meetings_manager ON meetings(manager_id, start_at);
CREATE INDEX idx_meetings_company ON meetings(company_id);
CREATE INDEX idx_companies_status ON companies(status);

-- Два менеджера, чтобы можно было сразу попробовать API.
INSERT INTO managers (name) VALUES ('Асель'), ('Нурлан');
