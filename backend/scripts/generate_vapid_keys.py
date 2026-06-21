"""Generate a VAPID keypair for Web Push and print .env-ready lines.

Generates the EC key directly with `cryptography` (rather than py_vapid's
generate_keys(), which is incompatible with current cryptography releases).

Usage:
    python scripts/generate_vapid_keys.py
"""
import base64
from cryptography.hazmat.primitives.asymmetric import ec


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())

    private_value = private_key.private_numbers().private_value
    private_raw = private_value.to_bytes(32, "big")
    private_b64 = base64.urlsafe_b64encode(private_raw).rstrip(b"=").decode()

    public_numbers = private_key.public_key().public_numbers()
    x = public_numbers.x.to_bytes(32, "big")
    y = public_numbers.y.to_bytes(32, "big")
    public_b64 = base64.urlsafe_b64encode(b"\x04" + x + y).rstrip(b"=").decode()

    print("# Paste these into backend/.env")
    print(f"VAPID_PRIVATE_KEY={private_b64}")
    print(f"VAPID_PUBLIC_KEY={public_b64}")
    print("VAPID_CLAIM_EMAIL=mailto:you@example.com")
    print()
    print("# Paste this into frontend/.env as VITE_VAPID_PUBLIC_KEY")
    print(public_b64)


if __name__ == "__main__":
    main()
