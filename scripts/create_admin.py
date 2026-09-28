#!/usr/bin/env python3
import sys
import os

# Add the src directory to the python path so we can import leetspice
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from sqlalchemy import select
from leetspice.db import SessionLocal
from leetspice.models import User
from leetspice.auth import hash_password

def create_admin(email, password, display_name):
    with SessionLocal() as session:
        existing = session.scalar(select(User).where(User.email == email))
        if existing:
            print(f"User {email} already exists. Upgrading to admin...")
            existing.is_admin = True
            session.commit()
            return
        
        user = User(
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
            is_admin=True
        )
        session.add(user)
        session.commit()
        print(f"Admin user {email} created successfully.")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python scripts/create_admin.py <email> <password> <display_name>")
        sys.exit(1)
    create_admin(sys.argv[1], sys.argv[2], sys.argv[3])
