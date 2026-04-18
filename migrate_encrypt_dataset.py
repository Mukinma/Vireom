"""Migrate plain-text biometric data to encrypted storage (one-time).

Run BEFORE setting CAMERAPI_STORAGE_ENCRYPTED=1 in .env.

What it does
------------
1. Encrypts every .jpg image in dataset/ using the key derived from
   CAMERAPI_SECRET.
2. Encrypts models/lbph_model.xml if present.
3. Writes a migration receipt to dataset/.encrypted_v1 so the script is
   idempotent (safe to re-run — already-encrypted files are skipped).

Usage
-----
    python migrate_encrypt_dataset.py [--dry-run] [--decrypt]

    --dry-run  : list what would be changed, no writes.
    --decrypt  : reverse the migration (emergency rollback).

Requirements
------------
    CAMERAPI_SECRET must match the value used (or to be used) at runtime.
    The dataset/ directory and models/ must be accessible.

WARNING: back up your dataset/ and models/ before running.
"""

import argparse
import sys
from pathlib import Path

from cryptography.fernet import InvalidToken


def _build_fernet(secret: str):
    import base64
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    raw = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"vireom-biometric-v1",
        info=b"storage",
    ).derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(raw))


def _is_already_encrypted(data: bytes, fernet) -> bool:
    """Try to decrypt; if it succeeds, file is already encrypted."""
    try:
        fernet.decrypt(data)
        return True
    except (InvalidToken, Exception):
        return False


def _encrypt_file(path: Path, fernet, dry_run: bool) -> str:
    data = path.read_bytes()
    if _is_already_encrypted(data, fernet):
        return "already_encrypted"
    if dry_run:
        return "would_encrypt"
    path.write_bytes(fernet.encrypt(data))
    return "encrypted"


def _decrypt_file(path: Path, fernet, dry_run: bool) -> str:
    data = path.read_bytes()
    try:
        plain = fernet.decrypt(data)
    except InvalidToken:
        return "not_encrypted"
    if dry_run:
        return "would_decrypt"
    path.write_bytes(plain)
    return "decrypted"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing")
    parser.add_argument("--decrypt", action="store_true",
                        help="Reverse migration (decrypt back to plain)")
    args = parser.parse_args()

    # Load config (sets up env vars from .env)
    from config import config

    if not config.secret_key:
        print("ERROR: CAMERAPI_SECRET is empty. Set it in .env first.", file=sys.stderr)
        sys.exit(1)

    fernet = _build_fernet(config.secret_key)

    receipt = Path(config.dataset_dir) / ".encrypted_v1"
    if args.decrypt and receipt.exists() and not args.dry_run:
        receipt.unlink()

    # ── Collect targets ────────────────────────────────────────────────────────
    targets: list[Path] = []

    dataset_root = Path(config.dataset_dir)
    if dataset_root.exists():
        targets.extend(dataset_root.rglob("*.jpg"))

    model_path = Path(config.model_path)
    if model_path.exists():
        targets.append(model_path)

    if not targets:
        print("Nothing to process (dataset/ empty, no model file).")
        return

    # ── Process ───────────────────────────────────────────────────────────────
    counts: dict[str, int] = {}
    action_fn = _decrypt_file if args.decrypt else _encrypt_file
    action_verb = "decrypt" if args.decrypt else "encrypt"

    for path in sorted(targets):
        status = action_fn(path, fernet, args.dry_run)
        counts[status] = counts.get(status, 0) + 1
        symbol = {"encrypted": "✓", "decrypted": "✓",
                  "already_encrypted": "–", "not_encrypted": "–",
                  "would_encrypt": "→", "would_decrypt": "→"}.get(status, "?")
        print(f"  {symbol} {status:<20} {path}")

    print()
    for k, v in sorted(counts.items()):
        print(f"  {v:4d}  {k}")

    # ── Receipt ───────────────────────────────────────────────────────────────
    if not args.dry_run and not args.decrypt:
        import time
        receipt.write_text(
            f"encrypted_at={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            f"files={counts.get('encrypted', 0)}\n"
            f"version=1\n"
        )
        print(f"\nReceipt written to {receipt}")
        print("\nNext steps:")
        print("  1. Verify the system works: python main.py (test login + recognize)")
        print("  2. Set CAMERAPI_STORAGE_ENCRYPTED=1 in .env")
        print("  3. Restart the service")
    elif args.dry_run:
        print("\n(dry-run — no files modified)")


if __name__ == "__main__":
    main()
