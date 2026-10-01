#!/usr/bin/env python3
"""Create a reviewer account entry for .env (standard library only).

    python3 scripts/hash_passcode.py "Priya Sharma"
    → prompts for a passcode, prints:  Priya Sharma=<salt>.<hash>

Join several entries with ";" in REVIEWERS=... in .env, then restart the
backend (docker compose up -d backend).
"""
import getpass
import hashlib
import secrets
import sys

# Must match backend/app/auth.py.
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print(__doc__)
        return 2
    name = sys.argv[1].strip()
    if "=" in name or ";" in name:
        print("Reviewer names cannot contain '=' or ';'.")
        return 2
    passcode = getpass.getpass(f"Passcode for {name}: ")
    if len(passcode) < 6:
        print("Use at least 6 characters.")
        return 2
    if getpass.getpass("Repeat passcode: ") != passcode:
        print("Passcodes did not match.")
        return 2
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(passcode.encode(), salt=salt, **_SCRYPT)
    print(f"{name}={salt.hex()}.{digest.hex()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
