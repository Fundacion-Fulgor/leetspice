import re

import pytest
from fastapi.testclient import TestClient

from leetspice.config import Settings
from leetspice.main import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        secret_key="test-secret-key",
        seed_demo=True,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def csrf():
    def extract(response):
        match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
        assert match, "CSRF field was not rendered"
        return match.group(1)

    return extract


@pytest.fixture
def register(client, csrf):
    def create(email="designer@example.com", name="Ada"):
        token = csrf(client.get("/register"))
        return client.post(
            "/register",
            data={
                "email": email,
                "display_name": name,
                "password": "correct-horse-battery",
                "csrf_token": token,
            },
            follow_redirects=False,
        )

    return create
