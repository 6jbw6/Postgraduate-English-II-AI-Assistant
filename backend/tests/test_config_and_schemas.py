import base64
import os
import unittest

from pydantic import ValidationError

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/test.db")

from backend.config import Settings
from backend.auth import UserProfileUpdate, UserRegister
from backend.middleware import RequestContextMiddleware
from backend.schemas import ChatRequest
from backend.storage import decode_data_url, storage


class ConfigAndSchemaTests(unittest.TestCase):
    def test_production_requires_explicit_jwt_secret(self):
        with self.assertRaises(RuntimeError):
            Settings(
                app_env="production",
                jwt_secret_key="dev-only-change-me-please-32-characters-min",
            )

    def test_wildcard_cors_disables_credentials(self):
        settings = Settings(cors_origins=["*"], cors_allow_credentials=True)

        self.assertEqual(settings.cors_origins, ["*"])
        self.assertFalse(settings.cors_allow_credentials)

    def test_chat_request_strips_message_and_accepts_base64_image(self):
        image = base64.b64encode(b"fake-image").decode("ascii")
        request = ChatRequest(message="  hello  ", images=[image])

        self.assertEqual(request.message, "hello")
        self.assertEqual(request.images, [image])

    def test_chat_request_rejects_invalid_base64_image(self):
        with self.assertRaises(ValidationError):
            ChatRequest(message="", images=["not valid base64"])

    def test_user_register_accepts_common_email_domain(self):
        user = UserRegister(username="student", email="Student@QQ.COM", password="password123")

        self.assertEqual(user.email, "student@qq.com")

    def test_user_register_accepts_common_email_domain_without_provider_specific_rule(self):
        user = UserRegister(username="student", email="2432@qq.com", password="password123")

        self.assertEqual(user.email, "2432@qq.com")

    def test_user_register_rejects_invalid_email_format(self):
        with self.assertRaises(ValidationError):
            UserRegister(username="student", email="student@123.123", password="password123")

    def test_user_register_rejects_uncommon_email_domain(self):
        with self.assertRaises(ValidationError):
            UserRegister(username="student", email="student@example.org", password="password123")

    def test_profile_target_score_accepts_integer_between_0_and_100(self):
        profile = UserProfileUpdate(target_score=" 100 ")

        self.assertEqual(profile.target_score, "100")

    def test_profile_target_score_rejects_out_of_range_or_non_integer(self):
        for value in ("101", "-1", "75+", "80.5"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    UserProfileUpdate(target_score=value)

    def test_avatar_data_url_allows_larger_image_under_limit(self):
        image = base64.b64encode(b"x" * (1024 * 1024)).decode("ascii")
        profile = UserProfileUpdate(avatar_url=f"data:image/png;base64,{image}")

        self.assertTrue(profile.avatar_url.startswith("data:image/png;base64,"))

    def test_avatar_data_url_rejects_image_over_limit(self):
        image = base64.b64encode(b"x" * (2 * 1024 * 1024 + 1)).decode("ascii")

        with self.assertRaises(ValidationError):
            UserProfileUpdate(avatar_url=f"data:image/png;base64,{image}")

    def test_avatar_url_accepts_local_upload_path(self):
        profile = UserProfileUpdate(avatar_url="/uploads/avatars/1/avatar.png")

        self.assertEqual(profile.avatar_url, "/uploads/avatars/1/avatar.png")

    def test_request_context_middleware_can_be_constructed(self):
        self.assertIsNotNone(RequestContextMiddleware)

    def test_data_url_can_be_decoded_for_object_storage(self):
        image = base64.b64encode(b"fake-image").decode("ascii")
        content, mime_type = decode_data_url(f"data:image/png;base64,{image}")

        self.assertEqual(content, b"fake-image")
        self.assertEqual(mime_type, "image/png")

    def test_local_storage_saves_bytes_and_returns_url(self):
        stored = storage.save_bytes(b"avatar", "image/png", prefix="tests")

        self.assertTrue(stored.key.startswith("tests/"))
        self.assertIn("/uploads/tests/", stored.url)


if __name__ == "__main__":
    unittest.main()
