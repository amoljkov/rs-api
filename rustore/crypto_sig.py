import base64
import datetime as dt
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA512

def iso_timestamp_with_ms_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")

def generate_signature_b64(key_id: str, private_key_b64: str, timestamp: str) -> str:
    private_key_der = base64.b64decode(private_key_b64)
    private_key = RSA.import_key(private_key_der)

    msg = (key_id + timestamp).encode("utf-8")
    h = SHA512.new(msg)
    sig = pkcs1_15.new(private_key).sign(h)
    return base64.b64encode(sig).decode("utf-8")