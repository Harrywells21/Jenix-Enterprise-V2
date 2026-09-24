"""Tests for the REAL license module (top-level license.py) -- no patching.

Regression for the Sept 24 finding: generate_license() upper-cased the whole
key, including the case-sensitive base64 payload, so no generated key could
ever validate. These tests exercise generate -> validate for real, plus the
same flow end-to-end through /api/license/generate and /api/license/activate.
"""
import base64
from conftest import auth_headers
from license import generate_license, validate_license, check_node_limit


def split_key(key):
    encoded, sig = key[6:].rsplit("-", 1)
    return encoded, sig


def test_generated_key_validates_round_trip():
    r = validate_license(generate_license("Acme Corp", 50))
    assert r["valid"] is True
    assert (r["company"], r["max_nodes"], r["perpetual"]) == ("Acme Corp", 50, True)
    assert isinstance(r["issued_at"], str) and r["issued_at"]


def test_round_trip_preserves_unlimited_and_non_perpetual():
    r = validate_license(generate_license("Globex Ltd", is_perpetual=False))
    assert r["valid"] is True
    assert (r["company"], r["max_nodes"], r["perpetual"]) == ("Globex Ltd", -1, False)


def test_key_format_prefix_and_uppercase_hex_signature():
    key = generate_license("Acme Corp", 5)
    assert key.startswith("JENIX-")
    _, sig = split_key(key)
    assert len(sig) == 16 and sig == sig.upper()
    assert all(c in "0123456789ABCDEF" for c in sig)


def test_validate_tolerates_surrounding_whitespace():
    key = generate_license("Acme Corp", 5)
    assert validate_license("  " + key + "\n")["valid"] is True


def test_tampered_payload_is_rejected():
    key = generate_license("Acme Corp", 5)
    encoded, sig = split_key(key)
    data = base64.b64decode(encoded)
    assert b'"max_nodes": 5' in data
    forged = data.replace(b'"max_nodes": 5', b'"max_nodes": -1')
    forged_key = "JENIX-" + base64.b64encode(forged).decode() + "-" + sig
    r = validate_license(forged_key)
    assert r["valid"] is False and r["error"] == "Invalid signature"


def test_wrong_signature_is_rejected():
    encoded, _ = split_key(generate_license("Acme Corp", 5))
    r = validate_license("JENIX-" + encoded + "-" + "0" * 16)
    assert r["valid"] is False and r["error"] == "Invalid signature"


def test_bad_prefix_and_malformed_keys_rejected():
    assert validate_license("ABC-123-DEF") == {"valid": False, "error": "Invalid key format"}
    assert validate_license("JENIX-nodashes") == {"valid": False, "error": "Malformed key"}
    assert validate_license("")["valid"] is False


def test_check_node_limit():
    assert check_node_limit(-1, 9999) is True
    assert check_node_limit(5, 5) is True
    assert check_node_limit(5, 6) is False


def test_generate_then_activate_end_to_end_through_routes(client, db_session, admin_user):
    h = auth_headers(admin_user)
    g = client.post("/api/license/generate",
                    json={"company_name": "Acme Corp", "max_nodes": 25}, headers=h)
    assert g.status_code == 200
    a = client.post("/api/license/activate", json={"key": g.json()["key"]}, headers=h)
    assert a.status_code == 200
    assert a.json() == {"ok": True, "company": "Acme Corp", "max_nodes": 25}
    got = client.get("/api/license", headers=h).json()
    assert got["activated"] is True and got["company_name"] == "Acme Corp"
