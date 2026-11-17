"""Встречи через API. 2030-01-07 понедельник, время в UTC: 05:00Z = 10:00 Алматы."""
import threading


def book(client, company_id, start, manager_id=1):
    return client.post("/meetings", json={"company_id": company_id, "manager_id": manager_id, "start_at": start})


def test_manager_overlap(client, make_company):
    a, b, c = make_company(), make_company(), make_company()
    assert book(client, a, "2030-01-07T05:00:00Z").status_code == 201  # 10:00-11:00

    r = book(client, b, "2030-01-07T05:30:00Z")  # 10:30-11:30 пересекается
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "manager_busy"

    r = book(client, b, "2030-01-07T04:30:00Z")  # 09:30-10:30 тоже пересекается
    assert r.status_code == 409

    # 11:00-12:00 встык, это не конфликт
    assert book(client, b, "2030-01-07T06:00:00Z").status_code == 201
    # 09:00-10:00 встык с другой стороны
    assert book(client, c, "2030-01-07T04:00:00Z").status_code == 201


def test_other_manager_same_time_is_fine(client, make_company):
    a, b = make_company(), make_company()
    assert book(client, a, "2030-01-07T05:00:00Z", manager_id=1).status_code == 201
    assert book(client, b, "2030-01-07T05:00:00Z", manager_id=2).status_code == 201


def test_end_of_day_via_api(client, make_company):
    a = make_company()
    r = book(client, a, "2030-01-07T12:30:00Z")  # 17:30 Алматы
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "outside_working_hours"
    assert "17:00" in r.json()["error"]["message"]

    r = book(client, a, "2030-01-07T12:00:00Z")  # 17:00 Алматы, последний слот
    assert r.status_code == 201
    assert r.json()["end_at"] == "2030-01-07T13:00:00Z"


def test_time_with_offset_is_stored_in_utc(client, make_company):
    r = book(client, make_company(), "2030-01-07T10:00:00+05:00")
    assert r.status_code == 201
    assert r.json()["start_at"] == "2030-01-07T05:00:00Z"


def test_time_without_timezone_rejected(client, make_company):
    r = book(client, make_company(), "2030-01-07T10:00:00")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_past_rejected(client, make_company):
    r = book(client, make_company(), "2020-01-06T05:00:00Z")  # понедельник, но в прошлом
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "in_the_past"


def test_company_cannot_have_two_active_meetings(client, make_company):
    a = make_company()
    assert book(client, a, "2030-01-07T05:00:00Z", manager_id=1).status_code == 201
    # другой менеджер, другое время, но организация та же
    r = book(client, a, "2030-01-08T08:00:00Z", manager_id=2)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "company_has_meeting"


def test_cancel_frees_slot(client, make_company):
    a, b = make_company(), make_company()
    m = book(client, a, "2030-01-07T05:00:00Z").json()
    assert client.patch(f"/meetings/{m['id']}", json={"status": "cancelled"}).status_code == 200

    assert book(client, b, "2030-01-07T05:00:00Z").status_code == 201  # слот менеджера свободен
    assert book(client, a, "2030-01-08T05:00:00Z").status_code == 201  # и организация может назначить новую

    r = client.patch(f"/meetings/{m['id']}", json={"start_at": "2030-01-09T05:00:00Z"})
    assert r.status_code == 409  # отмененную встречу не переносим


def test_reschedule_keeps_history(client, make_company):
    m = book(client, make_company(), "2030-01-07T05:00:00Z").json()
    client.patch(f"/meetings/{m['id']}", json={"start_at": "2030-01-08T06:00:00Z"})
    r = client.patch(f"/meetings/{m['id']}", json={"start_at": "2030-01-09T07:00:00Z"})
    assert r.status_code == 200

    data = client.get(f"/meetings/{m['id']}").json()
    assert data["start_at"] == "2030-01-09T07:00:00Z"
    assert data["original_start_at"] == "2030-01-07T05:00:00Z"
    assert [h["action"] for h in data["history"]] == ["created", "rescheduled", "rescheduled"]
    assert [h["start_at"] for h in data["history"]] == [
        "2030-01-07T05:00:00Z", "2030-01-08T06:00:00Z", "2030-01-09T07:00:00Z",
    ]


def test_reschedule_into_conflict_changes_nothing(client, make_company):
    a, b = make_company(), make_company()
    book(client, a, "2030-01-07T05:00:00Z")
    m = book(client, b, "2030-01-07T07:00:00Z").json()

    r = client.patch(f"/meetings/{m['id']}", json={"start_at": "2030-01-07T05:30:00Z"})
    assert r.status_code == 409
    data = client.get(f"/meetings/{m['id']}").json()
    assert data["start_at"] == "2030-01-07T07:00:00Z"
    assert len(data["history"]) == 1


def test_reschedule_onto_own_time_is_not_conflict(client, make_company):
    # сдвиг на 30 минут пересекается сам с собой, это не должно считаться конфликтом
    m = book(client, make_company(), "2030-01-07T05:00:00Z").json()
    r = client.patch(f"/meetings/{m['id']}", json={"start_at": "2030-01-07T05:30:00Z"})
    assert r.status_code == 200


def test_patch_needs_exactly_one_field(client, make_company):
    m = book(client, make_company(), "2030-01-07T05:00:00Z").json()
    assert client.patch(f"/meetings/{m['id']}", json={}).status_code == 422
    both = {"start_at": "2030-01-08T05:00:00Z", "status": "cancelled"}
    assert client.patch(f"/meetings/{m['id']}", json=both).status_code == 422


def test_not_found(client, make_company):
    assert book(client, make_company(), "2030-01-07T05:00:00Z", manager_id=999).status_code == 404
    assert client.patch("/meetings/999", json={"status": "cancelled"}).status_code == 404
    assert client.get("/managers/999/schedule?date=2030-01-07").status_code == 404


def test_schedule_uses_almaty_day(client, make_company):
    a, b, c = make_company(), make_company(), make_company()
    book(client, a, "2030-01-07T04:00:00Z")  # пн 09:00 Алматы
    book(client, b, "2030-01-07T12:00:00Z")  # пн 17:00 Алматы
    book(client, c, "2030-01-08T04:00:00Z")  # вт 09:00, в понедельник не попадает

    r = client.get("/managers/1/schedule?date=2030-01-07")
    assert r.status_code == 200
    starts = [m["start_at"] for m in r.json()["meetings"]]
    assert starts == ["2030-01-07T04:00:00Z", "2030-01-07T12:00:00Z"]


def test_two_managers_book_same_slot_at_once(client, make_company):
    """Гонка: 10 запросов одновременно на один слот одного менеджера. Пройти должен ровно один."""
    companies = [make_company() for _ in range(10)]
    codes = []
    start_together = threading.Barrier(len(companies))  # все потоки стартуют в один момент

    def worker(company_id):
        start_together.wait()
        codes.append(book(client, company_id, "2030-01-07T05:00:00Z").status_code)

    threads = [threading.Thread(target=worker, args=(c,)) for c in companies]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(codes) == [201] + [409] * 9
