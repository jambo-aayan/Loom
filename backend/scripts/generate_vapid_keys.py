"""One-time setup for Web Push (ticket #39): generates a VAPID key pair in the raw,
base64url-encoded form both `pywebpush` (backend) and `PushManager.subscribe` (browser)
expect. Run once, then paste the output into `.env`:

    python scripts/generate_vapid_keys.py
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )

    print(f"VAPID_PRIVATE_KEY={_b64url(private_raw)}")
    print(f"VAPID_PUBLIC_KEY={_b64url(public_raw)}")


if __name__ == "__main__":
    main()
