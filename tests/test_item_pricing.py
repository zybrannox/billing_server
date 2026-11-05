"""An item's rate and minimum charges can be set, and bills come out exact."""
import pytest
from passlib.hash import bcrypt

from app.entities import ListOption, User, UserRole
from app.invoices.calculations import compute_line
from app.security import create_access_token

FLEX_TIERS = [{"up_to_sq_ft": 15, "amount": 150}, {"up_to_sq_ft": 20, "amount": 200}]


def _sign_in(client, db, name, role=UserRole.USER, permissions=()):
    db.add(User(username=name, email=f"{name}@example.com", phone="9" + str(abs(hash(name)))[:9].zfill(9),
                hashed_password=bcrypt.hash("x" * 12), role=role, is_active=True, permissions=list(permissions)))
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": name, "role": role.value, "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"


def _option(db, category="item_type", value="Flex"):
    option = ListOption(category=category, value=value, sort_order=1, is_active=True)
    db.add(option)
    db.commit()
    return option


@pytest.fixture
def admin(client, db):
    _sign_in(client, db, "boss", UserRole.ADMIN)


def test_rate_and_minimums_can_be_saved_and_read_back(client, db, admin):
    option = _option(db)
    res = client.patch(f"/list-options/{option.id}/pricing", json={"rate": 12, "min_charges": FLEX_TIERS})
    assert res.status_code == 200, res.text
    listed = client.get("/list-options/", params={"category": "item_type"}).json()[0]
    assert listed["rate"] == 12
    assert listed["min_charges"] == FLEX_TIERS


def test_minimums_can_be_changed_and_removed(client, db, admin):
    option = _option(db)
    client.patch(f"/list-options/{option.id}/pricing", json={"min_charges": FLEX_TIERS})
    changed = client.patch(f"/list-options/{option.id}/pricing", json={"min_charges": [{"up_to_sq_ft": 10, "amount": 175}]})
    assert changed.json()["min_charges"] == [{"up_to_sq_ft": 10, "amount": 175}]
    assert client.patch(f"/list-options/{option.id}/pricing", json={"min_charges": []}).json()["min_charges"] is None


@pytest.mark.parametrize("tiers", [
    [{"up_to_sq_ft": 20, "amount": 200}, {"up_to_sq_ft": 15, "amount": 150}],
    [{"up_to_sq_ft": 15, "amount": 150}, {"up_to_sq_ft": 15, "amount": 200}],
    [{"up_to_sq_ft": 0, "amount": 150}],
    [{"up_to_sq_ft": 15, "amount": -1}],
])
def test_nonsense_minimums_are_refused(client, db, admin, tiers):
    assert client.patch(f"/list-options/{_option(db).id}/pricing", json={"min_charges": tiers}).status_code == 422


def test_project_types_have_no_price(client, db, admin):
    option = _option(db, "project_type", "Banner")
    assert client.patch(f"/list-options/{option.id}/pricing", json={"rate": 5}).status_code == 400


def test_a_missing_option_is_not_found(client, db, admin):
    assert client.patch("/list-options/999/pricing", json={"rate": 5}).status_code == 404


@pytest.mark.parametrize("permissions,expected", [((), 403), (("workspace.manage",), 200)])
def test_changing_prices_needs_workspace_access(client, db, permissions, expected):
    option = _option(db)
    _sign_in(client, db, "ravi", permissions=permissions)
    assert client.patch(f"/list-options/{option.id}/pricing", json={"rate": 5}).status_code == expected


@pytest.mark.parametrize("width,height,pieces,minimum", [
    (2, 3, 1, 150), (3.3, 2.1, 1, 150), (1, 1, 7, 150), (4, 4, 1, 200), (2.7, 7, 1, 200),
])
def test_a_minimum_sent_as_a_derived_rate_bills_exactly_the_minimum(width, height, pieces, minimum):
    # What the form sends: rate = minimum / (area x pieces), to 6 decimal places.
    sq_ft = round(width * height, 2)
    rate = round(minimum / (sq_ft * pieces), 6)
    assert compute_line(width, height, rate, pieces, "ft", True)[1] == minimum


def test_a_price_change_reads_plainly_in_the_activity_log(client, db, admin):
    option = _option(db)
    client.patch(f"/list-options/{option.id}/pricing", json={"min_charges": FLEX_TIERS})
    entries = client.get("/audit-log/", params={"entity_type": "list_option"}).json()["items"]
    change = next(c for c in entries[0]["detail"]["changes"] if c["field"] == "min_charges")
    assert change["label"] == "Minimum charges"
    assert change["to"] == "Rs 150 up to 15 sq ft, Rs 200 up to 20 sq ft"
