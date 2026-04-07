"""
Integration tests for login flow with ABDM HPR verification.

Tests the full login pipeline with ABDM verification enabled/disabled.
"""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.domain.auth.service import (
    AuthenticationError,
    authenticate_and_create_session,
)
from app.domain.integrations.abdm_hpr_use_cases import DoctorNotVerifiedError
from app.schemas.auth import UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_user_row(user_id=1, role="doctor", is_active=True, password_hash="$2b$12$dummy"):
    """Create a mock user row from the database."""
    return {
        "id": user_id,
        "username": "dr_test",
        "password_hash": password_hash,
        "role": role,
        "is_active": is_active,
    }


def _mock_settings(
    abdm_enabled=True,
    abdm_enforcement=True,
    session_hours=12,
):
    """Create a mock settings object."""
    mock = MagicMock()
    mock.abdm_hpr_enabled = abdm_enabled
    mock.abdm_hpr_login_enforcement_enabled = abdm_enforcement
    mock.auth_session_hours = session_hours
    return mock


def _verification_result(verified=True, status="Active"):
    """Create a standard verification result."""
    return {
        "hpr_id": "HPR-12345",
        "name": "Dr. Test User",
        "registration_number": "REG-12345",
        "status": status,
        "qualifications": ["MBBS"],
        "speciality": "General",
        "verified": verified,
        "raw": {},
    }


class FakeDb:
    """Minimal fake database for testing."""
    def commit(self):
        pass
    
    def execute(self, *args, **kwargs):
        """Mock execute that returns an empty result."""
        from unittest.mock import MagicMock
        mock = MagicMock()
        mock.mappings.return_value.first.return_value = None
        return mock


# ---------------------------------------------------------------------------
# Tests: Doctor login with ABDM enabled
# ---------------------------------------------------------------------------

class TestDoctorLoginWithAbdmEnabled:
    def setup_method(self):
        """Clear cache and reset infrastructure state."""
        from app.infrastructure.cache import cache
        cache.clear()
        
    def test_verified_doctor_login_succeeds(self):
        """Test that a verified doctor can login successfully."""
        mock_settings = _mock_settings(abdm_enabled=True, abdm_enforcement=True)
        fake_db = FakeDb()

        user_row = _mock_user_row(role="doctor")
        # Use a real bcrypt hash for "TestPass123"
        from app.domain.auth.service import hash_password
        user_row["password_hash"] = hash_password("TestPass123")

        with patch("app.domain.auth.service.settings", mock_settings):
            with patch("app.domain.auth.service.is_abdm_hpr_enabled", return_value=True):
                with patch("app.domain.auth.service.is_abdm_login_enforcement_enabled", return_value=True):
                    with patch("app.domain.auth.service.users_repo") as mock_users_repo:
                        mock_users_repo.get_user_by_username.return_value = user_row
                        mock_users_repo.get_user_hpr_id.return_value = "HPR-12345"

                        with patch("app.domain.auth.service.verify_doctor_for_login") as mock_verify:
                            mock_verify.return_value = _verification_result(verified=True)

                            with patch("app.domain.auth.service.user_sessions_repo.create_session"):
                                with patch("app.domain.auth.service.auth_logs_repo.log_auth_attempt"):
                                    user, token, expires_at, abdm_details = authenticate_and_create_session(
                                        db=fake_db,
                                        username="dr_test",
                                        password="TestPass123",
                                        ip_address="127.0.0.1",
                                        user_agent="test-agent",
                                    )

        assert user.role == UserRole.doctor
        assert token is not None
        assert abdm_details is not None
        assert abdm_details["verified"] is True

    def test_unverified_doctor_login_blocked(self):
        """Test that an unverified doctor is blocked when enforcement is enabled."""
        mock_settings = _mock_settings(abdm_enabled=True, abdm_enforcement=True)
        fake_db = FakeDb()

        user_row = _mock_user_row(role="doctor")
        from app.domain.auth.service import hash_password
        user_row["password_hash"] = hash_password("TestPass123")

        with patch("app.domain.auth.service.settings", mock_settings):
            with patch("app.domain.auth.service.is_abdm_hpr_enabled", return_value=True):
                with patch("app.domain.auth.service.is_abdm_login_enforcement_enabled", return_value=True):
                    with patch("app.domain.auth.service.users_repo") as mock_users_repo:
                        mock_users_repo.get_user_by_username.return_value = user_row
                        mock_users_repo.get_user_hpr_id.return_value = "HPR-12345"

                        with patch("app.domain.auth.service.verify_doctor_for_login") as mock_verify:
                            mock_verify.side_effect = DoctorNotVerifiedError("Not verified")

                            with patch("app.domain.auth.service.auth_logs_repo.log_auth_attempt"):
                                with pytest.raises(AuthenticationError, match="(?i)not.*(active|verified)"):
                                    authenticate_and_create_session(
                                        db=fake_db,
                                        username="dr_test",
                                        password="TestPass123",
                                        ip_address="127.0.0.1",
                                        user_agent="test-agent",
                                    )

    def test_doctor_without_hpr_id_blocked(self):
        """Test that a doctor without HPR ID is blocked when enforcement is enabled."""
        mock_settings = _mock_settings(abdm_enabled=True, abdm_enforcement=True)
        fake_db = FakeDb()

        user_row = _mock_user_row(role="doctor")
        from app.domain.auth.service import hash_password
        user_row["password_hash"] = hash_password("TestPass123")

        with patch("app.domain.auth.service.settings", mock_settings):
            with patch("app.domain.auth.service.is_abdm_hpr_enabled", return_value=True):
                with patch("app.domain.auth.service.is_abdm_login_enforcement_enabled", return_value=True):
                    with patch("app.domain.auth.service.users_repo") as mock_users_repo:
                        mock_users_repo.get_user_by_username.return_value = user_row
                        mock_users_repo.get_user_hpr_id.return_value = None  # No HPR ID

                        with patch("app.domain.auth.service.auth_logs_repo.log_auth_attempt"):
                            with pytest.raises(AuthenticationError, match="register your ABDM HPR ID"):
                                authenticate_and_create_session(
                                    db=fake_db,
                                    username="dr_test",
                                    password="TestPass123",
                                    ip_address="127.0.0.1",
                                    user_agent="test-agent",
                                )


# ---------------------------------------------------------------------------
# Tests: Doctor login with ABDM enforcement disabled
# ---------------------------------------------------------------------------

class TestDoctorLoginWithAbdmEnforcementDisabled:
    def setup_method(self):
        """Clear cache and reset infrastructure state."""
        from app.infrastructure.cache import cache
        cache.clear()
        
    def test_unverified_doctor_login_allowed(self):
        """Test that an unverified doctor can login when enforcement is disabled."""
        mock_settings = _mock_settings(abdm_enabled=True, abdm_enforcement=False)
        fake_db = FakeDb()

        user_row = _mock_user_row(role="doctor")
        from app.domain.auth.service import hash_password
        user_row["password_hash"] = hash_password("TestPass123")

        with patch("app.domain.auth.service.settings", mock_settings):
            with patch("app.domain.auth.service.users_repo") as mock_users_repo:
                mock_users_repo.get_user_by_username.return_value = user_row
                mock_users_repo.get_user_hpr_id.return_value = "HPR-12345"

                with patch("app.domain.auth.service.verify_doctor_for_login") as mock_verify:
                    mock_verify.side_effect = DoctorNotVerifiedError("Not verified")

                    with patch("app.domain.auth.service.user_sessions_repo.create_session"):
                        with patch("app.domain.auth.service.auth_logs_repo.log_auth_attempt"):
                            user, token, expires_at, abdm_details = authenticate_and_create_session(
                                db=fake_db,
                                username="dr_test",
                                password="TestPass123",
                                ip_address="127.0.0.1",
                                user_agent="test-agent",
                            )

        assert user.role == UserRole.doctor
        assert token is not None
        # Should be None because verification failed but enforcement is disabled
        assert abdm_details is None

    def test_doctor_without_hpr_id_allowed(self):
        """Test that a doctor without HPR ID can login when enforcement is disabled."""
        mock_settings = _mock_settings(abdm_enabled=True, abdm_enforcement=False)
        fake_db = FakeDb()

        user_row = _mock_user_row(role="doctor")
        from app.domain.auth.service import hash_password
        user_row["password_hash"] = hash_password("TestPass123")

        with patch("app.domain.auth.service.settings", mock_settings):
            with patch("app.domain.auth.service.users_repo") as mock_users_repo:
                mock_users_repo.get_user_by_username.return_value = user_row
                mock_users_repo.get_user_hpr_id.return_value = None

                with patch("app.domain.auth.service.user_sessions_repo.create_session"):
                    with patch("app.domain.auth.service.auth_logs_repo.log_auth_attempt"):
                        user, token, expires_at, abdm_details = authenticate_and_create_session(
                            db=fake_db,
                            username="dr_test",
                            password="TestPass123",
                            ip_address="127.0.0.1",
                            user_agent="test-agent",
                        )

        assert user.role == UserRole.doctor
        assert token is not None
        assert abdm_details is None


# ---------------------------------------------------------------------------
# Tests: Non-doctor login (ABDM should not apply)
# ---------------------------------------------------------------------------

class TestNonDoctorLogin:
    def setup_method(self):
        """Clear cache and reset infrastructure state."""
        from app.infrastructure.cache import cache
        cache.clear()
        
    def test_super_admin_login_ignores_abdm(self):
        """Test that super_admin login does not trigger ABDM verification."""
        mock_settings = _mock_settings(abdm_enabled=True, abdm_enforcement=True)
        fake_db = FakeDb()

        user_row = _mock_user_row(role="super_admin")
        from app.domain.auth.service import hash_password
        user_row["password_hash"] = hash_password("TestPass123")

        with patch("app.domain.auth.service.settings", mock_settings):
            with patch("app.domain.auth.service.users_repo") as mock_users_repo:
                mock_users_repo.get_user_by_username.return_value = user_row

                # verify_doctor_for_login should NOT be called
                with patch("app.domain.auth.service.verify_doctor_for_login") as mock_verify:
                    with patch("app.domain.auth.service.user_sessions_repo.create_session"):
                        with patch("app.domain.auth.service.auth_logs_repo.log_auth_attempt"):
                            user, token, expires_at, abdm_details = authenticate_and_create_session(
                                db=fake_db,
                                username="admin",
                                password="TestPass123",
                                ip_address="127.0.0.1",
                                user_agent="test-agent",
                            )

        assert user.role == UserRole.super_admin
        mock_verify.assert_not_called()
        assert abdm_details is None

    def test_user_login_ignores_abdm(self):
        """Test that regular user login does not trigger ABDM verification."""
        mock_settings = _mock_settings(abdm_enabled=True, abdm_enforcement=True)
        fake_db = FakeDb()

        user_row = _mock_user_row(role="user")
        from app.domain.auth.service import hash_password
        user_row["password_hash"] = hash_password("TestPass123")

        with patch("app.domain.auth.service.settings", mock_settings):
            with patch("app.domain.auth.service.users_repo") as mock_users_repo:
                mock_users_repo.get_user_by_username.return_value = user_row

                with patch("app.domain.auth.service.verify_doctor_for_login") as mock_verify:
                    with patch("app.domain.auth.service.user_sessions_repo.create_session"):
                        with patch("app.domain.auth.service.auth_logs_repo.log_auth_attempt"):
                            user, token, expires_at, abdm_details = authenticate_and_create_session(
                                db=fake_db,
                                username="regular_user",
                                password="TestPass123",
                                ip_address="127.0.0.1",
                                user_agent="test-agent",
                            )

        assert user.role == UserRole.user
        mock_verify.assert_not_called()
        assert abdm_details is None


# ---------------------------------------------------------------------------
# Tests: ABDM disabled entirely
# ---------------------------------------------------------------------------

class TestAbdmDisabled:
    def setup_method(self):
        """Clear cache and reset infrastructure state."""
        from app.infrastructure.cache import cache
        cache.clear()
        
    def test_doctor_login_skips_abdm_when_disabled(self):
        """Test that doctor login skips ABDM verification when disabled."""
        mock_settings = _mock_settings(abdm_enabled=False)
        fake_db = FakeDb()

        user_row = _mock_user_row(role="doctor")
        from app.domain.auth.service import hash_password
        user_row["password_hash"] = hash_password("TestPass123")

        with patch("app.domain.auth.service.settings", mock_settings):
            with patch("app.domain.auth.service.users_repo") as mock_users_repo:
                mock_users_repo.get_user_by_username.return_value = user_row

                with patch("app.domain.auth.service.verify_doctor_for_login") as mock_verify:
                    with patch("app.domain.auth.service.user_sessions_repo.create_session"):
                        with patch("app.domain.auth.service.auth_logs_repo.log_auth_attempt"):
                            user, token, expires_at, abdm_details = authenticate_and_create_session(
                                db=fake_db,
                                username="dr_test",
                                password="TestPass123",
                                ip_address="127.0.0.1",
                                user_agent="test-agent",
                            )

        assert user.role == UserRole.doctor
        mock_verify.assert_not_called()
        assert abdm_details is None
