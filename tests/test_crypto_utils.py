import pytest
from cryptography.fernet import Fernet, InvalidToken

from trigerr import crypto_utils as cu


@pytest.fixture
def fernet():
    return cu.load_key(Fernet.generate_key().decode())


def test_value_round_trip_string(fernet):
    token = cu.encrypt_value("hunter2", fernet)
    assert token != "hunter2"
    assert cu.decrypt_value(token, fernet) == "hunter2"


def test_value_round_trip_int(fernet):
    token = cu.encrypt_value(1234, fernet)
    assert cu.decrypt_value(token, fernet) == 1234


def test_value_round_trip_none(fernet):
    token = cu.encrypt_value(None, fernet)
    assert cu.decrypt_value(token, fernet) is None


def test_input_round_trip(fernet):
    input_list = [
        {"key_name": "api_key", "key_value": "abc"},
        {"key_name": "client_id", "key_value": 42},
    ]
    encrypted = cu.encrypt_input(input_list, fernet)
    assert {d["key_name"] for d in encrypted} == {"api_key", "client_id"}
    for d in encrypted:
        assert d["key_value"] not in ("abc", 42)

    decrypted = cu.decrypt_input(encrypted, fernet)
    assert decrypted == {"api_key": "abc", "client_id": 42}


def test_is_encrypted():
    assert cu.is_encrypted({"cred_enc": "fernet-v1"}) is True
    assert cu.is_encrypted({"cred_enc": "something-else"}) is False
    assert cu.is_encrypted({}) is False


def test_multi_key_rotation_decrypts_old_token():
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    old_fernet = cu.load_key(old_key)
    token = cu.encrypt_value("secret", old_fernet)

    rotated_fernet = cu.load_key(f"{new_key},{old_key}")
    assert cu.decrypt_value(token, rotated_fernet) == "secret"

    # new encryptions use the first (newest) key
    new_token = cu.encrypt_value("secret2", rotated_fernet)
    new_only_fernet = cu.load_key(new_key)
    assert cu.decrypt_value(new_token, new_only_fernet) == "secret2"


def test_tamper_detection(fernet):
    token = cu.encrypt_value("secret", fernet)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(InvalidToken):
        cu.decrypt_value(tampered, fernet)
