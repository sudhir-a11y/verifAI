"""
Unit tests for ABDM HPR domain use cases.

Tests business logic with mocked infrastructure.
"""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.domain.integrations.abdm_hpr_use_cases import (
    DoctorNotVerifiedError,
    DoctorVerificationError,
    invalidate_hpr_cache,
    is_abdm_hpr_enabled,
    is_abdm_login_enforcement_enabled,
    verify_doctor_for_login,
    verify_doctor_with_fallback,
)
from app.infrastructure.integrations.abdm_hpr import (
    AbdmHprDisabledError,
    AbdmHprNetworkError,
    AbdmHprServiceError,
    AbdmHprDoctorNotFoundError,
    AbdmHprAuthError,
    AbdmHprConfigError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_settings(enabled=True, enforcement=True, cache_ttl=3600):
    """Create a mock settings object."""
    mock = MagicMock()
    mock.abdm_hpr_enabled = enabled
    mock.abdm_hpr_login_enforcement_enabled = enforcement
    mock.abdm_hpr_cache_ttl_seconds = cache_ttl
    return mock


def _verification_result(verified=True, status="Active", name="Dr. Test"):
    """Create a standard verification result."""
    return {
        "hpr_id": "HPR-TEST",
        "name": name,
        "registration_number": "REG-TEST",
        "status": status,
        "qualifications": ["MBBS"],
        "speciality": "General",
        "verified": verified,
        "raw": {},
    }


# ---------------------------------------------------------------------------
# Tests for verify_doctor_for_login
# ---------------------------------------------------------------------------

class TestVerifyDoctorForLogin:
    def setup_method(self):
        """Clear cache before each test."""
        from app.domain.integrations.abdm_hpr_use_cases import _cache
        _cache.clear()

    def test_success(self):
        """Test successful doctor verification."""
        mock_settings = _mock_settings(enabled=True)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            with patch("app.domain.integrations.abdm_hpr_use_cases.verify_doctor") as mock_verify:
                mock_verify.return_value = _verification_result(verified=True)

                result = verify_doctor_for_login("HPR-TEST")

        assert result["verified"] is True
        assert result["hpr_id"] == "HPR-TEST"

    def test_disabled_raises_error(self):
        """Test that disabled ABDM raises AbdmHprDisabledError."""
        mock_settings = _mock_settings(enabled=False)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            with pytest.raises(AbdmHprDisabledError, match="disabled"):
                verify_doctor_for_login("HPR-TEST")

    def test_empty_hpr_id_raises_error(self):
        """Test that empty HPR ID raises DoctorVerificationError."""
        mock_settings = _mock_settings(enabled=True)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            with pytest.raises(DoctorVerificationError, match="required"):
                verify_doctor_for_login("")

    def test_not_verified_raises_error(self):
        """Test that unverified doctor raises DoctorNotVerifiedError."""
        mock_settings = _mock_settings(enabled=True)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            with patch("app.domain.integrations.abdm_hpr_use_cases.verify_doctor") as mock_verify:
                mock_verify.return_value = _verification_result(
                    verified=False, status="Suspended"
                )

                with pytest.raises(DoctorNotVerifiedError, match="not active/verified"):
                    verify_doctor_for_login("HPR-SUSPENDED")

    def test_network_error_wrapped(self):
        """Test that network errors are wrapped in DoctorVerificationError."""
        mock_settings = _mock_settings(enabled=True)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            with patch("app.domain.integrations.abdm_hpr_use_cases.verify_doctor") as mock_verify:
                mock_verify.side_effect = AbdmHprNetworkError("Connection failed")

                with pytest.raises(DoctorVerificationError, match="Unable to connect"):
                    verify_doctor_for_login("HPR-TEST")

    def test_service_error_wrapped(self):
        """Test that service errors are wrapped in DoctorVerificationError."""
        mock_settings = _mock_settings(enabled=True)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            with patch("app.domain.integrations.abdm_hpr_use_cases.verify_doctor") as mock_verify:
                mock_verify.side_effect = AbdmHprServiceError("Service error")

                with pytest.raises(DoctorVerificationError, match="service returned an error"):
                    verify_doctor_for_login("HPR-TEST")

    def test_cache_hit_returns_cached(self):
        """Test that cached result is returned without API call."""
        mock_settings = _mock_settings(enabled=True)
        cached_result = _verification_result(verified=True, name="Dr. Cached")

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            with patch("app.domain.integrations.abdm_hpr_use_cases._get_cached") as mock_get_cached:
                mock_get_cached.return_value = cached_result

                with patch("app.domain.integrations.abdm_hpr_use_cases.verify_doctor") as mock_verify:
                    result = verify_doctor_for_login("HPR-TEST")

                    # verify_doctor should not be called on cache hit
                    mock_verify.assert_not_called()

        assert result["name"] == "Dr. Cached"


# ---------------------------------------------------------------------------
# Tests for verify_doctor_with_fallback
# ---------------------------------------------------------------------------

class TestVerifyDoctorWithFallback:
    def test_success_returns_result(self):
        """Test successful verification returns result."""
        mock_settings = _mock_settings(enabled=True)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            with patch("app.domain.integrations.abdm_hpr_use_cases.verify_doctor_for_login") as mock_verify:
                mock_verify.return_value = _verification_result(verified=True)

                result = verify_doctor_with_fallback("HPR-TEST")

        assert result is not None
        assert result["verified"] is True

    def test_disabled_returns_none(self):
        """Test that disabled ABDM returns None."""
        mock_settings = _mock_settings(enabled=False)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            result = verify_doctor_with_fallback("HPR-TEST")

        assert result is None

    def test_verification_failure_returns_none(self):
        """Test that verification failure returns None (non-blocking)."""
        mock_settings = _mock_settings(enabled=True)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            with patch("app.domain.integrations.abdm_hpr_use_cases.verify_doctor_for_login") as mock_verify:
                mock_verify.side_effect = DoctorNotVerifiedError("Not verified")

                result = verify_doctor_with_fallback("HPR-TEST")

        assert result is None

    def test_network_error_returns_none(self):
        """Test that network error returns None (non-blocking)."""
        mock_settings = _mock_settings(enabled=True)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            with patch("app.domain.integrations.abdm_hpr_use_cases.verify_doctor_for_login") as mock_verify:
                mock_verify.side_effect = DoctorVerificationError("Network error")

                result = verify_doctor_with_fallback("HPR-TEST")

        assert result is None

    def test_generic_exception_returns_none(self):
        """Test that any unexpected error returns None."""
        mock_settings = _mock_settings(enabled=True)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            with patch("app.domain.integrations.abdm_hpr_use_cases.verify_doctor_for_login") as mock_verify:
                mock_verify.side_effect = Exception("Unexpected error")

                result = verify_doctor_with_fallback("HPR-TEST")

        assert result is None


# ---------------------------------------------------------------------------
# Tests for cache helpers
# ---------------------------------------------------------------------------

class TestCacheHelpers:
    def test_invalidate_cache(self):
        """Test cache invalidation."""
        with patch("app.domain.integrations.abdm_hpr_use_cases._cache") as mock_cache:
            invalidate_hpr_cache("HPR-TEST")
            mock_cache.delete.assert_called_once_with("abdm_hpr:verify:HPR-TEST")


# ---------------------------------------------------------------------------
# Tests for configuration checks
# ---------------------------------------------------------------------------

class TestConfigChecks:
    def test_is_abdm_hpr_enabled_true(self):
        """Test ABDM enabled check returns True."""
        mock_settings = _mock_settings(enabled=True)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            assert is_abdm_hpr_enabled() is True

    def test_is_abdm_hpr_enabled_false(self):
        """Test ABDM disabled check returns False."""
        mock_settings = _mock_settings(enabled=False)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            assert is_abdm_hpr_enabled() is False

    def test_is_abdm_login_enforcement_enabled_true(self):
        """Test login enforcement enabled check returns True."""
        mock_settings = _mock_settings(enforcement=True)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            assert is_abdm_login_enforcement_enabled() is True

    def test_is_abdm_login_enforcement_enabled_false(self):
        """Test login enforcement disabled check returns False."""
        mock_settings = _mock_settings(enforcement=False)

        with patch("app.domain.integrations.abdm_hpr_use_cases.settings", mock_settings):
            assert is_abdm_login_enforcement_enabled() is False
