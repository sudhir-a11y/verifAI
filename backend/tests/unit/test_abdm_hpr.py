"""
Unit tests for ABDM HPR integration infrastructure layer.

Tests HTTP client functions with mocked responses.
"""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.infrastructure.integrations.abdm_hpr import (
    AbdmHprAuthError,
    AbdmHprConfigError,
    AbdmHprDisabledError,
    AbdmHprDoctorNotFoundError,
    AbdmHprNetworkError,
    AbdmHprServiceError,
    fetch_doctor_by_hpr_id,
    search_doctor_by_registration_number,
    verify_doctor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_settings(enabled=True, base_url="https://hpr.abdm.gov.in", token_url="https://hpr.abdm.gov.in/auth/token", client_id="test_client", client_secret="test_secret"):
    """Create a mock settings object."""
    mock = MagicMock()
    mock.abdm_hpr_enabled = enabled
    mock.abdm_hpr_base_url = base_url
    mock.abdm_hpr_auth_token_url = token_url
    mock.abdm_hpr_client_id = client_id
    mock.abdm_hpr_client_secret = client_secret
    mock.abdm_hpr_timeout_seconds = 10.0
    mock.abdm_hpr_token_ttl_seconds = 300
    mock.abdm_hpr_cache_ttl_seconds = 3600
    return mock


def _mock_httpx_response(status_code=200, json_data=None):
    """Create a mock httpx response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or {}
    mock.text = str(json_data) if json_data else ""
    return mock


# ---------------------------------------------------------------------------
# Tests for fetch_doctor_by_hpr_id
# ---------------------------------------------------------------------------

class TestFetchDoctorByHprId:
    def test_success(self):
        """Test successful doctor fetch by HPR ID."""
        mock_settings = _mock_settings()
        mock_response = _mock_httpx_response(
            status_code=200,
            json_data={
                "hprId": "HPR-12345",
                "name": "Dr. Ramesh Gupta",
                "registrationNumber": "REG-98765",
                "status": "Active",
                "qualifications": ["MBBS", "MD"],
                "speciality": "General Medicine",
            },
        )

        with patch("app.infrastructure.integrations.abdm_hpr.settings", mock_settings):
            with patch("app.infrastructure.integrations.abdm_hpr._token_manager") as mock_token_mgr:
                mock_token_mgr.get_token.return_value = "mock_token"
                with patch("app.infrastructure.integrations.abdm_hpr.httpx.Client") as mock_client_cls:
                    mock_client = MagicMock()
                    mock_client.get.return_value = mock_response
                    mock_client.__enter__ = MagicMock(return_value=mock_client)
                    mock_client.__exit__ = MagicMock(return_value=False)
                    mock_client_cls.return_value = mock_client

                    result = fetch_doctor_by_hpr_id("HPR-12345")

        assert result["hprId"] == "HPR-12345"
        assert result["name"] == "Dr. Ramesh Gupta"

    def test_disabled_raises_error(self):
        """Test that disabled ABDM raises AbdmHprDisabledError."""
        mock_settings = _mock_settings(enabled=False)

        with patch("app.infrastructure.integrations.abdm_hpr.settings", mock_settings):
            with pytest.raises(AbdmHprDisabledError, match="disabled"):
                fetch_doctor_by_hpr_id("HPR-12345")

    def test_not_found_raises_error(self):
        """Test that 404 raises AbdmHprDoctorNotFoundError."""
        mock_settings = _mock_settings()
        mock_response = _mock_httpx_response(status_code=404)

        with patch("app.infrastructure.integrations.abdm_hpr.settings", mock_settings):
            with patch("app.infrastructure.integrations.abdm_hpr._token_manager") as mock_token_mgr:
                mock_token_mgr.get_token.return_value = "mock_token"
                with patch("app.infrastructure.integrations.abdm_hpr.httpx.Client") as mock_client_cls:
                    mock_client = MagicMock()
                    mock_client.get.return_value = mock_response
                    mock_client.__enter__ = MagicMock(return_value=mock_client)
                    mock_client.__exit__ = MagicMock(return_value=False)
                    mock_client_cls.return_value = mock_client

                    with pytest.raises(AbdmHprDoctorNotFoundError, match="not found"):
                        fetch_doctor_by_hpr_id("HPR-NONEXISTENT")

    def test_empty_hpr_id_raises_error(self):
        """Test that empty HPR ID raises ValueError."""
        mock_settings = _mock_settings()
        
        with patch("app.infrastructure.integrations.abdm_hpr.settings", mock_settings):
            with patch("app.infrastructure.integrations.abdm_hpr._token_manager") as mock_token_mgr:
                mock_token_mgr.get_token.return_value = "mock_token"
                
                with pytest.raises(ValueError, match="must not be empty"):
                    fetch_doctor_by_hpr_id("")

    def test_network_error_raises_error(self):
        """Test that network error raises AbdmHprNetworkError."""
        import httpx
        mock_settings = _mock_settings()

        with patch("app.infrastructure.integrations.abdm_hpr.settings", mock_settings):
            with patch("app.infrastructure.integrations.abdm_hpr._token_manager") as mock_token_mgr:
                mock_token_mgr.get_token.return_value = "mock_token"
                with patch("app.infrastructure.integrations.abdm_hpr.httpx.Client") as mock_client_cls:
                    mock_client = MagicMock()
                    mock_client.get.side_effect = httpx.RequestError("Connection refused")
                    mock_client.__enter__ = MagicMock(return_value=mock_client)
                    mock_client.__exit__ = MagicMock(return_value=False)
                    mock_client_cls.return_value = mock_client

                    with pytest.raises(AbdmHprNetworkError, match="Unable to reach"):
                        fetch_doctor_by_hpr_id("HPR-12345")


# ---------------------------------------------------------------------------
# Tests for search_doctor_by_registration_number
# ---------------------------------------------------------------------------

class TestSearchDoctorByRegistrationNumber:
    def test_success_returns_list(self):
        """Test successful doctor search returns list."""
        mock_settings = _mock_settings()
        mock_response = _mock_httpx_response(
            status_code=200,
            json_data=[
                {
                    "hprId": "HPR-111",
                    "name": "Dr. Alice",
                    "registrationNumber": "REG-111",
                    "status": "Active",
                },
                {
                    "hprId": "HPR-222",
                    "name": "Dr. Bob",
                    "registrationNumber": "REG-111",
                    "status": "Inactive",
                },
            ],
        )

        with patch("app.infrastructure.integrations.abdm_hpr.settings", mock_settings):
            with patch("app.infrastructure.integrations.abdm_hpr._token_manager") as mock_token_mgr:
                mock_token_mgr.get_token.return_value = "mock_token"
                with patch("app.infrastructure.integrations.abdm_hpr.httpx.Client") as mock_client_cls:
                    mock_client = MagicMock()
                    mock_client.get.return_value = mock_response
                    mock_client.__enter__ = MagicMock(return_value=mock_client)
                    mock_client.__exit__ = MagicMock(return_value=False)
                    mock_client_cls.return_value = mock_client

                    result = search_doctor_by_registration_number("REG-111")

        assert len(result) == 2
        assert result[0]["hprId"] == "HPR-111"

    def test_dict_response_with_results_key(self):
        """Test dict response with 'results' key."""
        mock_settings = _mock_settings()
        mock_response = _mock_httpx_response(
            status_code=200,
            json_data={
                "results": [
                    {"hprId": "HPR-333", "name": "Dr. Charlie"},
                ]
            },
        )

        with patch("app.infrastructure.integrations.abdm_hpr.settings", mock_settings):
            with patch("app.infrastructure.integrations.abdm_hpr._token_manager") as mock_token_mgr:
                mock_token_mgr.get_token.return_value = "mock_token"
                with patch("app.infrastructure.integrations.abdm_hpr.httpx.Client") as mock_client_cls:
                    mock_client = MagicMock()
                    mock_client.get.return_value = mock_response
                    mock_client.__enter__ = MagicMock(return_value=mock_client)
                    mock_client.__exit__ = MagicMock(return_value=False)
                    mock_client_cls.return_value = mock_client

                    result = search_doctor_by_registration_number("REG-333")

        assert len(result) == 1
        assert result[0]["hprId"] == "HPR-333"

    def test_disabled_raises_error(self):
        """Test that disabled ABDM raises AbdmHprDisabledError."""
        mock_settings = _mock_settings(enabled=False)

        with patch("app.infrastructure.integrations.abdm_hpr.settings", mock_settings):
            with pytest.raises(AbdmHprDisabledError, match="disabled"):
                search_doctor_by_registration_number("REG-111")


# ---------------------------------------------------------------------------
# Tests for verify_doctor
# ---------------------------------------------------------------------------

class TestVerifyDoctor:
    def test_active_doctor_verified(self):
        """Test that active doctor is verified."""
        mock_settings = _mock_settings()
        mock_response = _mock_httpx_response(
            status_code=200,
            json_data={
                "hprId": "HPR-12345",
                "name": "Dr. Ramesh Gupta",
                "registrationNumber": "REG-98765",
                "status": "Active",
                "qualifications": ["MBBS", "MD"],
                "speciality": "General Medicine",
            },
        )

        with patch("app.infrastructure.integrations.abdm_hpr.fetch_doctor_by_hpr_id") as mock_fetch:
            mock_fetch.return_value = {
                "hprId": "HPR-12345",
                "name": "Dr. Ramesh Gupta",
                "registrationNumber": "REG-98765",
                "status": "Active",
                "qualifications": ["MBBS", "MD"],
                "speciality": "General Medicine",
            }

            result = verify_doctor("HPR-12345")

        assert result["hpr_id"] == "HPR-12345"
        assert result["name"] == "Dr. Ramesh Gupta"
        assert result["registration_number"] == "REG-98765"
        assert result["status"] == "Active"
        assert result["verified"] is True
        assert result["qualifications"] == ["MBBS", "MD"]
        assert result["speciality"] == "General Medicine"

    def test_inactive_doctor_not_verified(self):
        """Test that inactive doctor is not verified."""
        with patch("app.infrastructure.integrations.abdm_hpr.fetch_doctor_by_hpr_id") as mock_fetch:
            mock_fetch.return_value = {
                "hprId": "HPR-67890",
                "name": "Dr. Inactive",
                "registrationNumber": "REG-67890",
                "status": "Suspended",
                "qualifications": ["MBBS"],
            }

            result = verify_doctor("HPR-67890")

        assert result["verified"] is False
        assert result["status"] == "Suspended"

    def test_alternative_field_names(self):
        """Test alternative field names in response."""
        with patch("app.infrastructure.integrations.abdm_hpr.fetch_doctor_by_hpr_id") as mock_fetch:
            mock_fetch.return_value = {
                "fullName": "Dr. Alternate",
                "registrationNo": "REG-ALT",
                "registrationStatus": "Registered",
                "degrees": ["MBBS", "MS"],
                "specialization": "Surgery",
            }

            result = verify_doctor("HPR-ALT")

        assert result["name"] == "Dr. Alternate"
        assert result["registration_number"] == "REG-ALT"
        assert result["status"] == "Registered"
        assert result["verified"] is True
        assert result["qualifications"] == ["MBBS", "MS"]
        assert result["speciality"] == "Surgery"

    def test_missing_fields_handled_gracefully(self):
        """Test missing fields are handled gracefully."""
        with patch("app.infrastructure.integrations.abdm_hpr.fetch_doctor_by_hpr_id") as mock_fetch:
            mock_fetch.return_value = {}

            result = verify_doctor("HPR-MINIMAL")

        assert result["hpr_id"] == "HPR-MINIMAL"
        assert result["name"] == ""
        assert result["registration_number"] == ""
        assert result["status"] == "Unknown"
        assert result["verified"] is False
        assert result["qualifications"] == []
        assert result["speciality"] is None
