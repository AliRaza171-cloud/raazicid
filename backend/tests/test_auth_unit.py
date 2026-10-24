"""Phase 2 checks that need no database."""

import pytest
from pydantic import ValidationError

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    normalize_phone,
    verify_password,
)
from app.schemas.auth import RegisterIn
from app.schemas.riders import DecisionIn
from app.services.uploads import sign_params


def test_password_hash_and_check():
    h = hash_password("secret-pass-1")
    assert h != "secret-pass-1"
    assert verify_password("secret-pass-1", h)
    assert not verify_password("wrong-pass", h)


def test_access_token_round_trip():
    import uuid
    uid = uuid.uuid4()
    payload = decode_access_token(create_access_token(uid, "donor"))
    assert payload["sub"] == str(uid) and payload["role"] == "donor"


def test_refresh_token_is_stored_hashed():
    raw, token_hash, _ = new_refresh_token()
    assert raw != token_hash and hash_refresh_token(raw) == token_hash


@pytest.mark.parametrize("raw", ["03001234567", "0300 1234567", "0300-1234567", "+92 300 1234567", "923001234567"])
def test_phone_formats_normalize(raw):
    assert normalize_phone(raw) == "03001234567"


@pytest.mark.parametrize("raw", ["12345", "0400123456", "02112345678", ""])
def test_bad_phones_rejected(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


def test_rider_must_give_vehicle():
    with pytest.raises(ValidationError):
        RegisterIn(role="rider", full_name="Usman Khan", phone="03001234567", password="password1")


def test_donor_ignores_rider_block():
    r = RegisterIn(role="donor", full_name="  Sana   Ahmed ", phone="0300 1234567", password="password1",
                   rider={"vehicle_type": "motorbike", "vehicle_number": "khi-1"})
    assert r.rider is None and r.full_name == "Sana Ahmed" and r.phone == "03001234567"


def test_admin_cannot_self_register():
    with pytest.raises(ValidationError):
        RegisterIn(role="admin", full_name="X Y", phone="03001234567", password="password1")


def test_reject_needs_note():
    with pytest.raises(ValidationError):
        DecisionIn(action="reject")
    assert DecisionIn(action="approve").note is None


def test_cloudinary_signature_matches_docs_example():
    # Example from Cloudinary's upload signature documentation (secret "abcd")
    params = {"eager": "w_400,h_300,c_pad|w_260,h_200,c_crop", "public_id": "sample_image", "timestamp": 1315060510}
    assert sign_params(params, "abcd") == "bfd09f95f331f558cbd1320e67aa8d488770583e"
