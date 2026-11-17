def test_company_validation(client):
    good = {"name": "ТОО Ромашка", "bin": "170340021554", "phone": "+7 701 123-45-67"}
    assert client.post("/companies", json=good).status_code == 201

    r = client.post("/companies", json=good)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "bin_exists"

    for bad_bin in ["12345", "17034002155A", "1703400215540"]:
        r = client.post("/companies", json={**good, "bin": bad_bin})
        assert r.status_code == 422, bad_bin
        assert "bin" in r.json()["error"]["message"]


def test_companies_filter_and_pagination(client, make_company):
    ids = [make_company() for _ in range(5)]
    client.post("/calls", json={"company_id": ids[0], "result": "refused"})
    client.post("/calls", json={"company_id": ids[1], "result": "refused"})

    r = client.get("/companies?status=refused").json()
    assert r["total"] == 2
    assert [c["id"] for c in r["items"]] == ids[:2]

    r = client.get("/companies?status=new&limit=2&offset=1").json()
    assert r["total"] == 3
    assert [c["id"] for c in r["items"]] == ids[3:5]

    assert client.get("/companies?status=wrong").status_code == 422
    assert client.get("/companies?limit=0").status_code == 422


def test_meeting_set_without_meeting_is_error(client, make_company):
    a = make_company()
    r = client.post("/calls", json={"company_id": a, "result": "meeting_set"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "meeting_required"

    r = client.post("/calls", json={"company_id": a, "result": "meeting_set", "meeting_id": 999})
    assert r.status_code == 422

    # статус организации не поменялся
    assert client.get("/companies?status=meeting_set").json()["total"] == 0


def test_meeting_set_with_other_company_meeting_is_error(client, make_company):
    a, b = make_company(), make_company()
    m = client.post("/meetings", json={"company_id": b, "manager_id": 1, "start_at": "2030-01-07T05:00:00Z"}).json()
    r = client.post("/calls", json={"company_id": a, "result": "meeting_set", "meeting_id": m["id"]})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "meeting_mismatch"


def test_meeting_set_ok(client, make_company):
    a = make_company()
    m = client.post("/meetings", json={"company_id": a, "manager_id": 1, "start_at": "2030-01-07T05:00:00Z"}).json()
    r = client.post("/calls", json={"company_id": a, "result": "meeting_set", "meeting_id": m["id"]})
    assert r.status_code == 201
    assert r.json()["meeting_id"] == m["id"]
    assert client.get("/companies?status=meeting_set").json()["items"][0]["id"] == a


def test_meeting_id_only_for_meeting_set(client, make_company):
    a = make_company()
    m = client.post("/meetings", json={"company_id": a, "manager_id": 1, "start_at": "2030-01-07T05:00:00Z"}).json()
    r = client.post("/calls", json={"company_id": a, "result": "no_answer", "meeting_id": m["id"]})
    assert r.status_code == 422
