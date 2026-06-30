import os
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/test.db")

from backend.auth import get_current_user
from backend.database import User, get_db
from backend.main import app
from backend.middleware import RequestContextMiddleware


class EnterpriseHardeningTests(unittest.TestCase):
    def test_versioned_question_types_route_is_available(self):
        client = TestClient(app)

        response = client.get("/api/v1/question-types")

        self.assertEqual(response.status_code, 200)
        self.assertIn("types", response.json())

    def test_request_context_headers_are_added(self):
        test_app = FastAPI()
        test_app.add_middleware(RequestContextMiddleware)

        @test_app.get("/ping")
        async def ping():
            return {"status": "ok"}

        client = TestClient(test_app)
        response = client.get("/ping", headers={"X-Request-ID": "test-request-id"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Request-ID"], "test-request-id")
        self.assertIn("X-Response-Time-ms", response.headers)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")

    def test_request_body_size_limit_returns_413(self):
        test_app = FastAPI()
        test_app.add_middleware(RequestContextMiddleware)

        @test_app.post("/echo")
        async def echo():
            return {"status": "ok"}

        client = TestClient(test_app)
        response = client.post(
            "/echo",
            content=b"x",
            headers={"Content-Length": str(20 * 1024 * 1024)},
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["detail"], "请求体过大")

    def test_admin_audit_logs_requires_admin_role(self):
        async def fake_user():
            return User(id=1, username="student", email="s@example.com", role="student")

        async def fake_db():
            yield None

        app.dependency_overrides[get_current_user] = fake_user
        app.dependency_overrides[get_db] = fake_db
        try:
            client = TestClient(app)
            response = client.get("/api/admin/audit-logs")
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "权限不足")


if __name__ == "__main__":
    unittest.main()
