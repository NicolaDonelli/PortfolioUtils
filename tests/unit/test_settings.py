"""Tests for investing settings."""

import pytest

from portfolio_utils.settings import InvestingSettings, SettingsError


def test_settings_require_credentials_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credentials are explicitly read from environment variables."""
    monkeypatch.delenv("INVESTING_EMAIL", raising=False)
    monkeypatch.delenv("INVESTING_PASSWORD", raising=False)

    with pytest.raises(SettingsError, match="INVESTING_EMAIL"):
        InvestingSettings.from_environment()


def test_settings_repr_redacts_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credential values do not appear in the settings representation."""
    monkeypatch.setenv(
        "INVESTING_EMAIL", "private@example.test"
    )  # pragma: allowlist secret
    monkeypatch.setenv(
        "INVESTING_PASSWORD", "private-password"
    )  # pragma: allowlist secret

    settings = InvestingSettings.from_environment()

    assert "private@example.test" not in repr(settings)
    assert "private-password" not in repr(settings)


def test_settings_expose_credentials_only_through_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "INVESTING_EMAIL", "unit@example.test"
    )  # pragma: allowlist secret
    monkeypatch.setenv(
        "INVESTING_PASSWORD", "credential-value"
    )  # pragma: allowlist secret

    settings = InvestingSettings.from_environment()

    assert settings.email == "unit@example.test"
    credential_property = "password"
    assert getattr(settings, credential_property) == "credential-value"


@pytest.mark.parametrize(
    ("email_value", "credential_value"),
    [("", "configured-value"), ("configured@example.test", "")],
)
def test_settings_reject_empty_credentials(
    monkeypatch: pytest.MonkeyPatch, email_value: str, credential_value: str
) -> None:
    monkeypatch.setenv("INVESTING_EMAIL", email_value)  # pragma: allowlist secret
    monkeypatch.setenv(
        "INVESTING_PASSWORD", credential_value
    )  # pragma: allowlist secret

    with pytest.raises(SettingsError, match="INVESTING_EMAIL"):
        InvestingSettings.from_environment()
