"""Бизнес-правила про время. Здесь нет базы, только расчеты, поэтому их легко тестировать."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ALMATY = ZoneInfo("Asia/Almaty")
MEETING_LENGTH = timedelta(minutes=60)
WORK_START_HOUR = 9
WORK_END_HOUR = 18


def now_utc():
    return datetime.now(timezone.utc)


def fmt(dt):
    """datetime -> строка UTC, например 2030-01-07T05:00:00Z"""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def working_hours_error(start):
    """Проверяет, что встреча целиком попадает в пн-пт 09:00-18:00 по Алматы.

    start: datetime с часовым поясом (любым, переводим сами).
    Возвращает текст ошибки или None, если все хорошо.
    """
    local_start = start.astimezone(ALMATY)
    local_end = local_start + MEETING_LENGTH

    if local_start.weekday() >= 5:  # 5 = суббота, 6 = воскресенье
        return f"Встречи назначаются только в будни. {local_start:%d.%m.%Y} по Алматы это выходной."

    day_start = local_start.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    day_end = local_start.replace(hour=WORK_END_HOUR, minute=0, second=0, microsecond=0)
    if local_start < day_start or local_end > day_end:
        return (
            f"Встреча {local_start:%H:%M}-{local_end:%H:%M} по Алматы не умещается в рабочее время 09:00-18:00. "
            f"Последнее возможное начало 17:00."
        )
    return None
