"""WordPress site configuration and authentication."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config"


@dataclass
class SiteConfig:
    """Configuration for a single WordPress site."""

    name: str
    base_url: str
    username: str
    application_password: str
    default_author_id: int | None = None
    default_status: str = "draft"

    @property
    def api_url(self) -> str:
        """Full REST API base URL (e.g. https://example.com/wp/wp-json/wp/v2)."""
        return f"{self.base_url.rstrip('/')}/wp-json/wp/v2"

    @property
    def auth_tuple(self) -> tuple[str, str]:
        """HTTP Basic Auth credentials tuple for requests."""
        return (self.username, self.application_password)

    @classmethod
    def from_env(cls, name: str = "default") -> SiteConfig:
        """Load site config from environment variables.

        Reads: WP_BASE_URL, WP_USERNAME, WP_APP_PASSWORD
        Optional: WP_DEFAULT_AUTHOR_ID, WP_DEFAULT_STATUS
        """
        base_url = os.environ.get("WP_BASE_URL", "")
        username = os.environ.get("WP_USERNAME", "")
        password = os.environ.get("WP_APP_PASSWORD", "")

        if not all([base_url, username, password]):
            raise ValueError(
                "Missing WordPress env vars. Set WP_BASE_URL, "
                "WP_USERNAME, and WP_APP_PASSWORD."
            )

        author_id_str = os.environ.get("WP_DEFAULT_AUTHOR_ID")
        author_id = int(author_id_str) if author_id_str else None

        return cls(
            name=name,
            base_url=base_url,
            username=username,
            application_password=password,
            default_author_id=author_id,
            default_status=os.environ.get("WP_DEFAULT_STATUS", "draft"),
        )


def load_site_config(
    site_name: str,
    config_path: str | Path | None = None,
) -> SiteConfig:
    """Load a site configuration by name from the YAML config file.

    Falls back to environment variables if the config file doesn't exist
    or doesn't contain the requested site.

    Args:
        site_name: Name of the site (key in the YAML file).
        config_path: Override path to wordpress_sites.yaml.

    Returns:
        SiteConfig for the requested site.

    Raises:
        ValueError: If the site is not found and env vars aren't set.
    """
    filepath = Path(config_path) if config_path else _CONFIG_DIR / "wordpress_sites.yaml"

    if filepath.exists():
        config = _load_from_yaml(filepath, site_name)
        if config:
            return config
        logger.info(
            "Site '%s' not found in %s, trying env vars", site_name, filepath
        )

    return SiteConfig.from_env(site_name)


def _load_from_yaml(filepath: Path, site_name: str) -> SiteConfig | None:
    """Load a specific site from the YAML config file."""
    with filepath.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "sites" not in data:
        return None

    site_data: dict[str, Any] | None = data["sites"].get(site_name)
    if site_data is None:
        return None

    return SiteConfig(
        name=site_name,
        base_url=site_data["base_url"],
        username=site_data["username"],
        application_password=site_data["application_password"],
        default_author_id=site_data.get("default_author_id"),
        default_status=site_data.get("default_status", "draft"),
    )


def list_sites(config_path: str | Path | None = None) -> list[str]:
    """List all site names from the YAML config file."""
    filepath = Path(config_path) if config_path else _CONFIG_DIR / "wordpress_sites.yaml"

    if not filepath.exists():
        return []

    with filepath.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "sites" not in data:
        return []

    return sorted(data["sites"].keys())


def save_site_config(
    site_name: str,
    site_data: dict[str, Any],
    config_path: str | Path | None = None,
) -> None:
    """Save or update a site configuration in the YAML config file.

    Args:
        site_name: Key name for the site.
        site_data: Dict with keys: base_url, username, application_password,
                   and optionally default_author_id, default_status.
        config_path: Override path to wordpress_sites.yaml.

    Raises:
        ValueError: If required fields are missing from site_data.
    """
    required = {"base_url", "username", "application_password"}
    missing = required - set(site_data.keys())
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(sorted(missing))}")

    filepath = Path(config_path) if config_path else _CONFIG_DIR / "wordpress_sites.yaml"

    if filepath.exists():
        with filepath.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        data = {}

    if "sites" not in data:
        data["sites"] = {}

    entry: dict[str, Any] = {
        "base_url": site_data["base_url"],
        "username": site_data["username"],
        "application_password": site_data["application_password"],
    }
    if site_data.get("default_author_id") is not None:
        entry["default_author_id"] = int(site_data["default_author_id"])
    if "default_status" in site_data:
        entry["default_status"] = site_data["default_status"]

    data["sites"][site_name] = entry

    with filepath.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    logger.info("Saved site config '%s' to %s", site_name, filepath)


def delete_site_config(
    site_name: str,
    config_path: str | Path | None = None,
) -> bool:
    """Remove a site from the YAML config file.

    Args:
        site_name: Key name of the site to remove.
        config_path: Override path to wordpress_sites.yaml.

    Returns:
        True if the site was found and removed, False if not found.
    """
    filepath = Path(config_path) if config_path else _CONFIG_DIR / "wordpress_sites.yaml"

    if not filepath.exists():
        return False

    with filepath.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "sites" not in data or site_name not in data["sites"]:
        return False

    del data["sites"][site_name]

    with filepath.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    logger.info("Deleted site config '%s' from %s", site_name, filepath)
    return True
