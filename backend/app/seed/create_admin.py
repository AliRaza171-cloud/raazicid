"""Create (or reset the password of) an admin account. Admins cannot sign up through the apps.

Run from backend/:
    python -m app.seed.create_admin --name "Ali Raza" --phone 03001234567 --email admin@raazicid.pk
It asks for the password without showing it.
"""

import argparse
import getpass

from sqlalchemy import select

from app.core.security import hash_password, normalize_phone
from app.db.session import SessionLocal
from app.models import User
from app.models.enums import Role


def main() -> None:
    ap = argparse.ArgumentParser(description="Create or update a RAAZICID admin")
    ap.add_argument("--name", required=True)
    ap.add_argument("--phone", required=True)
    ap.add_argument("--email", required=True)
    args = ap.parse_args()

    phone = normalize_phone(args.phone)
    email = args.email.strip().lower()
    password = getpass.getpass("Admin password (min 8 characters): ")
    if len(password) < 8 or len(password.encode()) > 72:
        raise SystemExit("Password must be 8 to 72 characters")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")

    with SessionLocal() as db:
        user = db.scalar(select(User).where((User.phone == phone) | (User.email == email)))
        if user is None:
            user = User(role=Role.admin, full_name=args.name, phone=phone, email=email,
                        password_hash=hash_password(password))
            db.add(user)
            action = "Created"
        else:
            if user.role != Role.admin:
                raise SystemExit(f"{phone} / {email} already belongs to a {user.role.value} account")
            user.password_hash = hash_password(password)
            user.full_name = args.name
            action = "Updated"
        db.commit()
        print(f"{action} admin {user.full_name} ({user.email})")


if __name__ == "__main__":
    main()
