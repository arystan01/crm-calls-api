#!/usr/bin/env bash
# Примеры запросов. Запускать на пустой базе, когда API уже работает на localhost:8000:
#   bash examples.sh
# Даты взяты в 2030 году, чтобы примеры не устаревали. 2030-01-07 это понедельник.
# Время в API в UTC: 05:00Z = 10:00 по Алматы.
API=${API:-http://localhost:8000}

step() { echo; echo "### $1"; }
post()  { curl -s -X POST  "$API$1" -H 'Content-Type: application/json' -d "$2"; echo; }
patch() { curl -s -X PATCH "$API$1" -H 'Content-Type: application/json' -d "$2"; echo; }
get()   { curl -s "$API$1"; echo; }

step "Добавить организации"
post /companies '{"name": "ТОО Алматы Трейд Компани", "bin": "170340021554", "phone": "+77011234567"}'
post /companies '{"name": "ТОО Кокжиек Курылыс", "bin": "210640900180", "phone": "+77172555555"}'

step "Ошибка: БИН не из 12 цифр (422)"
post /companies '{"name": "ТОО Ошибка", "bin": "12345", "phone": "+77011234567"}'

step "Ошибка: такой БИН уже есть (409)"
post /companies '{"name": "Дубль", "bin": "170340021554", "phone": "+77011234567"}'

step "Добавить менеджера (двое уже есть после миграции, id 1 и 2)"
post /managers '{"name": "Дамир"}'

step "Звонок без ответа"
post /calls '{"company_id": 2, "result": "no_answer"}'

step "Ошибка: meeting_set без встречи (422)"
post /calls '{"company_id": 1, "result": "meeting_set"}'

step "Назначить встречу: пн 10:00-11:00 по Алматы, менеджер 1"
post /meetings '{"company_id": 1, "manager_id": 1, "start_at": "2030-01-07T05:00:00Z"}'

step "Теперь звонок meeting_set со ссылкой на встречу"
post /calls '{"company_id": 1, "result": "meeting_set", "meeting_id": 1, "comment": "Договорились на понедельник"}'

step "Ошибка: у менеджера 1 уже занято 10:30 (409)"
post /meetings '{"company_id": 2, "manager_id": 1, "start_at": "2030-01-07T05:30:00Z"}'

step "11:00 встык, это не конфликт"
post /meetings '{"company_id": 2, "manager_id": 1, "start_at": "2030-01-07T06:00:00Z"}'

step "Ошибка: начало в 17:30 по Алматы, встреча не умещается до 18:00 (422)"
post /meetings '{"company_id": 1, "manager_id": 2, "start_at": "2030-01-07T12:30:00Z"}'

step "Ошибка: суббота (422)"
post /meetings '{"company_id": 1, "manager_id": 2, "start_at": "2030-01-05T05:00:00Z"}'

step "Ошибка: у организации 1 уже есть активная встреча, даже с другим менеджером (409)"
post /meetings '{"company_id": 1, "manager_id": 2, "start_at": "2030-01-08T05:00:00Z"}'

step "Перенести встречу 1 на вторник 15:00 по Алматы"
patch /meetings/1 '{"start_at": "2030-01-08T10:00:00Z"}'

step "Посмотреть встречу с историей: original_start_at и history остались"
get /meetings/1

step "Расписание менеджера 1 на понедельник и на вторник"
get "/managers/1/schedule?date=2030-01-07"
get "/managers/1/schedule?date=2030-01-08"

step "Отменить встречу 2"
patch /meetings/2 '{"status": "cancelled"}'

step "Список организаций со статусом meeting_set и все с пагинацией"
get "/companies?status=meeting_set"
get "/companies?limit=1&offset=1"
