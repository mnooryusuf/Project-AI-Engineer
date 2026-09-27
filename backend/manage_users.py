"""
manage_users.py — Kelola akun dan role dari terminal server.

Pendaftaran lewat aplikasi selalu menghasilkan akun read_only (boleh
bertanya, belum boleh mengunggah). Admin memakai skrip ini untuk membuat akun
admin pertama dan menyetujui akun lain.

Role:
    admin      unggah dan hapus dokumen knowledge base
    user       unggah dokumen
    read_only  bertanya dan membaca riwayat sendiri saja

Jalankan dari direktori backend/:
    .venv/bin/python3 manage_users.py list
    .venv/bin/python3 manage_users.py create-admin <username> <email>   # password ditanya
    .venv/bin/python3 manage_users.py set-role <username> <admin|user|read_only>
    .venv/bin/python3 manage_users.py set-active <username> <yes|no>    # nonaktifkan akun uji/lama
"""
import getpass
import sys

import bcrypt

from database import SessionLocal
from models import User

ROLES = ("admin", "user", "read_only")
# Sama dengan BCRYPT_MAX_BYTES di main.py.
BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:BCRYPT_MAX_BYTES], bcrypt.gensalt()).decode("utf-8")


def list_users(db) -> int:
    for u in db.query(User).order_by(User.id):
        status = "aktif" if u.is_active else "nonaktif"
        print(f"{u.username:<24} {u.role:<10} {status:<9} {u.email}")
    return 0


def create_admin(db, username: str, email: str) -> int:
    if db.query(User).filter((User.username == username) | (User.email == email)).first():
        print(f"Username atau email sudah dipakai. Untuk akun yang sudah ada: set-role {username} admin")
        return 1
    password = getpass.getpass("Password admin: ")
    if len(password) < 8 or password != getpass.getpass("Ulangi password: "):
        print("Password minimal 8 karakter dan kedua isian harus sama.")
        return 1
    db.add(User(username=username, email=email, hashed_password=hash_password(password), role="admin"))
    db.commit()
    print(f"Admin '{username}' dibuat.")
    return 0


def set_role(db, username: str, role: str) -> int:
    if role not in ROLES:
        print(f"Role harus salah satu dari: {', '.join(ROLES)}")
        return 1
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        print(f"Akun '{username}' tidak ditemukan.")
        return 1
    old = user.role
    user.role = role
    db.commit()
    print(f"{username}: {old} -> {role}")
    return 0


def set_active(db, username: str, value: str) -> int:
    if value not in ("yes", "no"):
        print("Nilai harus yes atau no.")
        return 1
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        print(f"Akun '{username}' tidak ditemukan.")
        return 1
    user.is_active = value == "yes"
    db.commit()
    print(f"{username}: {'aktif' if user.is_active else 'nonaktif'}")
    return 0


def main(argv: list[str]) -> int:
    commands = {
        "list": (list_users, 0),
        "create-admin": (create_admin, 2),
        "set-role": (set_role, 2),
        "set-active": (set_active, 2),
    }
    if not argv or argv[0] not in commands or len(argv) - 1 != commands[argv[0]][1]:
        print(__doc__)
        return 1
    fn, _ = commands[argv[0]]
    db = SessionLocal()
    try:
        return fn(db, *argv[1:])
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
