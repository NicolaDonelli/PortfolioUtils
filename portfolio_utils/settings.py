"""Environment-backed settings for Investing.com credentials.

No dotenv file is loaded. Credential values are only read by
:meth:`InvestingSettings.from_environment` and are never included in the settings
representation.
"""

import os


class SettingsError(ValueError):
    """Raised when required environment settings are missing."""


class InvestingSettings:
    """Investing.com credentials sourced exclusively from environment variables.

    Credential attributes are exposed through properties and excluded from repr.
    """

    def __init__(self, email: str, password: str) -> None:
        """Store credentials without including them in representations.

        :param email: Investing.com account email.
        :param password: Investing.com account password.
        """
        self._email = email
        self._password = password

    @property
    def email(self) -> str:
        """Return the configured account email.

        :return: Account email.
        """
        return self._email

    @property
    def password(self) -> str:
        """Return the configured account password.

        :return: Account password.
        """
        return self._password

    @classmethod
    def from_environment(cls) -> "InvestingSettings":
        """Create settings from ``INVESTING_EMAIL`` and ``INVESTING_PASSWORD``.

        :raises SettingsError: If either environment variable is missing or empty.
        :return: Credential settings loaded only from process environment.
        """
        email = os.environ.get("INVESTING_EMAIL")
        password = os.environ.get("INVESTING_PASSWORD")
        if not email or not password:
            raise SettingsError(
                "Set INVESTING_EMAIL and INVESTING_PASSWORD in the process environment."
            )
        return cls(email=email, password=password)

    def __repr__(self) -> str:
        """Return a representation that does not reveal either credential."""
        return "InvestingSettings(email='[redacted]', password='[redacted]')"
