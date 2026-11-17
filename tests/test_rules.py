"""Граница рабочего дня. Чистая функция, без базы.

2030-01-07 это понедельник. Алматы живет по UTC+5, значит 09:00 Алматы = 04:00 UTC.
"""
from datetime import datetime, timezone

import pytest

from app.rules import ALMATY, working_hours_error


def almaty(day, hour, minute=0):
    return datetime(2030, 1, day, hour, minute, tzinfo=ALMATY)


@pytest.mark.parametrize("hour, minute, ok", [
    (8, 59, False),   # на минуту раньше начала дня
    (9, 0, True),     # ровно начало дня
    (16, 59, True),
    (17, 0, True),    # 17:00-18:00, последняя встреча дня
    (17, 1, False),   # закончится в 18:01
    (17, 30, False),  # пример из ТЗ
    (18, 0, False),
])
def test_end_of_working_day(hour, minute, ok):
    error = working_hours_error(almaty(7, hour, minute))
    assert (error is None) == ok


def test_weekend_rejected():
    assert working_hours_error(almaty(5, 10)) is not None  # суббота
    assert working_hours_error(almaty(6, 10)) is not None  # воскресенье


def test_utc_is_converted_to_almaty():
    # 04:00 UTC = 09:00 Алматы, можно. 03:59 UTC = 08:59 Алматы, нельзя.
    assert working_hours_error(datetime(2030, 1, 7, 4, 0, tzinfo=timezone.utc)) is None
    assert working_hours_error(datetime(2030, 1, 7, 3, 59, tzinfo=timezone.utc)) is not None
    # Воскресенье 23:00 UTC это уже понедельник 04:00 по Алматы, все равно нерабочее время
    assert working_hours_error(datetime(2030, 1, 6, 23, 0, tzinfo=timezone.utc)) is not None


def test_almaty_offset_is_plus_5():
    # С 1 марта 2024 Казахстан на UTC+5. Если tzdata старая, этот тест упадет.
    assert almaty(7, 9).utcoffset().total_seconds() == 5 * 3600
