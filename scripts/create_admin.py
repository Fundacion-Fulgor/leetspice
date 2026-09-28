#!/usr/bin/env python3
"""Create or promote a user to admin. Runs inside the container."""

import sys
from sqlalchemy import select
from leetspice.db import SessionLocal
from leetspice.models import User
from leetspice.auth import hash_password


def create_admin(email: str, password: str, display_name: str) -> None:
    with SessionLocal() as session:
        existing = session.scalar(select(User).where(User.email == email))
        if existing:
            print(f"User '{email}' already exists (id={existing.id}). Promoting to admin...")
            existing.is_admin = True
            session.commit()
            print("Done. User is now admin.")
            return

        user = User(
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
            is_admin=True,
        )
        session.add(user)
        session.commit()
        print(f"Admin user '{email}' created successfully (id={user.id}).")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python -m scripts.create_admin <email> <password> <display_name>")
        print("  e.g. python scripts/create_admin.py admin@uni.edu S3cur3Pass! 'Admin User'")
        sys.exit(1)
    create_admin(sys.argv[1], sys.argv[2], sys.argv[3])
