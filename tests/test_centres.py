def make_test(client, admin_headers, name="CBC"):
    res = client.post("/tests/", json={"name": name}, headers=admin_headers)
    assert res.status_code == 201
    return res.json()["id"]


def make_centre(client, admin_headers, name="City Lab", location="Delhi"):
    res = client.post(
        "/centres/", json={"name": name, "location": location}, headers=admin_headers
    )
    assert res.status_code == 201
    return res.json()["id"]


def test_admin_can_create_centre_and_add_test_with_price(client, admin_headers):
    test_id = make_test(client, admin_headers)
    centre_id = make_centre(client, admin_headers)

    res = client.post(
        f"/centres/{centre_id}/tests",
        json={"test_id": test_id, "price": "450.50"},
        headers=admin_headers,
    )
    assert res.status_code == 201
    offered = res.json()["tests"]
    assert offered == [{"test_id": test_id, "name": "CBC", "price": "450.50"}]


def test_normal_user_cannot_create_centre(client, user_headers):
    res = client.post(
        "/centres/", json={"name": "X", "location": "Y"}, headers=user_headers
    )
    assert res.status_code == 403


def test_anonymous_cannot_create_centre(client):
    res = client.post("/centres/", json={"name": "X", "location": "Y"})
    assert res.status_code in (401, 403)


def test_anyone_can_list_and_get_centres(client, admin_headers):
    centre_id = make_centre(client, admin_headers)

    listing = client.get("/centres/")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    assert client.get(f"/centres/{centre_id}").json()["name"] == "City Lab"


def test_unknown_centre_returns_404(client):
    assert client.get("/centres/999").status_code == 404


def test_pagination(client, admin_headers):
    for i in range(3):
        make_centre(client, admin_headers, name=f"Lab {i}")

    res = client.get("/centres/?page=2&size=2").json()
    assert res["total"] == 3
    assert len(res["items"]) == 1
    assert res["page"] == 2


def test_location_filter(client, admin_headers):
    make_centre(client, admin_headers, name="A", location="Delhi")
    make_centre(client, admin_headers, name="B", location="Mumbai")

    res = client.get("/centres/?location=mum").json()
    assert [c["name"] for c in res["items"]] == ["B"]


def test_invalid_pagination_is_rejected(client):
    assert client.get("/centres/?page=0").status_code == 422
    assert client.get("/centres/?size=1000").status_code == 422


def test_price_must_be_positive(client, admin_headers):
    test_id = make_test(client, admin_headers)
    centre_id = make_centre(client, admin_headers)
    res = client.post(
        f"/centres/{centre_id}/tests",
        json={"test_id": test_id, "price": "-5"},
        headers=admin_headers,
    )
    assert res.status_code == 422


def test_same_test_cannot_be_added_twice(client, admin_headers):
    test_id = make_test(client, admin_headers)
    centre_id = make_centre(client, admin_headers)
    body = {"test_id": test_id, "price": "100"}
    client.post(f"/centres/{centre_id}/tests", json=body, headers=admin_headers)

    res = client.post(f"/centres/{centre_id}/tests", json=body, headers=admin_headers)
    assert res.status_code == 409


def test_add_unknown_test_returns_404(client, admin_headers):
    centre_id = make_centre(client, admin_headers)
    res = client.post(
        f"/centres/{centre_id}/tests",
        json={"test_id": 999, "price": "100"},
        headers=admin_headers,
    )
    assert res.status_code == 404


def test_duplicate_test_name_is_rejected(client, admin_headers):
    make_test(client, admin_headers, name="CBC")
    res = client.post("/tests/", json={"name": "CBC"}, headers=admin_headers)
    assert res.status_code == 409


def test_price_update_shows_in_listing_not_stale(client, admin_headers):
    # the list is cached, so this also checks the cache is cleared on change
    test_id = make_test(client, admin_headers)
    centre_id = make_centre(client, admin_headers)
    client.post(
        f"/centres/{centre_id}/tests",
        json={"test_id": test_id, "price": "100"},
        headers=admin_headers,
    )
    client.get("/centres/")  # fills the cache

    client.put(
        f"/centres/{centre_id}/tests/{test_id}",
        json={"price": "250"},
        headers=admin_headers,
    )
    listing = client.get("/centres/").json()
    assert listing["items"][0]["tests"][0]["price"] == "250.00"
