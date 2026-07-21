"""Shared envelope encryption for broker credential values (`broker_credentials.input[].key_value`).

Used by trigerr-oms (encrypt-on-write / decrypt-on-read at its Mongo resolver
choke point) and trigerr-broker-automation (decrypt before use in its daily
token-refresh cron, re-encrypt before persisting). Both hold the same master
key material (env var `BROKER_CRED_MASTER_KEYS`, comma-separated for
rotation); this module never reads the environment itself — each repo's own
config module reads the env var and passes the string into load_key().

Usage:
    from trigerr.crypto_utils import load_key, encrypt_input, decrypt_input, is_encrypted, ENC_MARKER

    fernet = load_key(os.environ["BROKER_CRED_MASTER_KEYS"])
    encrypted_input = encrypt_input(doc["input"], fernet)
    # doc["cred_enc"] = ENC_MARKER, doc["input"] = encrypted_input

    if is_encrypted(doc):
        credentials = decrypt_input(doc["input"], fernet)
"""
import json

from cryptography.fernet import Fernet, MultiFernet

ENC_MARKER = "fernet-v1"


def load_key(keys_str):
    """Comma-separated Fernet keys -> MultiFernet. First key encrypts; all
    keys are tried on decrypt, so rotation is prepend-new-key/soak/drop-old
    with no flag day."""
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    return MultiFernet([Fernet(k) for k in keys])


def encrypt_value(value, fernet):
    return fernet.encrypt(json.dumps(value).encode()).decode()


def decrypt_value(token, fernet):
    return json.loads(fernet.decrypt(token.encode()).decode())


def encrypt_input(input_list, fernet):
    """[{key_name, key_value}, ...] -> same shape, key_value replaced by ciphertext."""
    return [{"key_name": d["key_name"], "key_value": encrypt_value(d["key_value"], fernet)}
            for d in input_list]


def decrypt_input(input_list, fernet):
    """[{key_name, key_value}, ...] (ciphertext) -> flat {key_name: plain_value} dict."""
    return {d["key_name"]: decrypt_value(d["key_value"], fernet) for d in input_list}


def is_encrypted(doc):
    return doc.get("cred_enc") == ENC_MARKER
