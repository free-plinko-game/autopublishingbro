"""WordPress REST API client for posts, pages, and media."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any

import requests

from wordpress.auth import SiteConfig

logger = logging.getLogger(__name__)

# Default timeout for API requests (seconds)
_TIMEOUT = 30


class WordPressClient:
    """Handles all WordPress REST API communication.

    Uses Application Passwords for authentication (WordPress 5.6+).
    ACF Pro fields are read/written via the `acf` key on posts.
    """

    def __init__(self, config: SiteConfig):
        self.config = config
        self._session = requests.Session()
        self._session.auth = config.auth_tuple
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        })

    # --- Posts / Pages ---

    def create_post(
        self,
        data: dict[str, Any],
        post_type: str = "post",
        status: str | None = None,
    ) -> dict[str, Any]:
        """Create a new post or page.

        Args:
            data: Post data. May include 'title', 'slug', 'content',
                  'acf' (for ACF fields), 'categories', 'tags', etc.
            post_type: WordPress post type ('post', 'page', or custom).
            status: Publish status ('draft', 'publish', 'pending').
                    Defaults to the site's default_status.

        Returns:
            Created post data from WordPress (includes id, link, etc.).

        Raises:
            WordPressAPIError: If the API request fails.
        """
        endpoint = self._endpoint(post_type)
        payload = self._prepare_post_payload(data, status)

        logger.info(
            "Creating %s: title=%r, status=%s",
            post_type,
            payload.get("title", ""),
            payload.get("status", ""),
        )

        return self._request("POST", endpoint, json=payload)

    def update_post(
        self,
        post_id: int,
        data: dict[str, Any],
        post_type: str = "post",
    ) -> dict[str, Any]:
        """Update an existing post or page.

        Args:
            post_id: WordPress post ID.
            data: Fields to update. Only provided fields are changed.
            post_type: WordPress post type.

        Returns:
            Updated post data from WordPress.

        Raises:
            WordPressAPIError: If the API request fails.
        """
        endpoint = f"{self._endpoint(post_type)}/{post_id}"

        logger.info("Updating %s %d", post_type, post_id)

        return self._request("POST", endpoint, json=data)

    def get_post(
        self,
        post_id: int,
        post_type: str = "post",
    ) -> dict[str, Any]:
        """Fetch a post with its ACF fields.

        Args:
            post_id: WordPress post ID.
            post_type: WordPress post type.

        Returns:
            Post data including 'acf' key with all ACF field values.

        Raises:
            WordPressAPIError: If the API request fails.
        """
        endpoint = f"{self._endpoint(post_type)}/{post_id}"
        params = {"_fields": "id,title,slug,status,link,acf,date,modified"}

        return self._request("GET", endpoint, params=params)

    def search_posts(
        self,
        search: str,
        post_type: str = "post",
        per_page: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for posts by keyword.

        Args:
            search: Search query string.
            post_type: WordPress post type.
            per_page: Maximum results to return.

        Returns:
            List of matching post dicts.

        Raises:
            WordPressAPIError: If the API request fails.
        """
        endpoint = self._endpoint(post_type)
        params = {
            "search": search,
            "per_page": per_page,
            "_fields": "id,title,slug,status,link",
        }

        return self._request("GET", endpoint, params=params)

    def delete_post(
        self,
        post_id: int,
        post_type: str = "post",
        force: bool = False,
    ) -> dict[str, Any]:
        """Delete a post (moves to trash unless force=True).

        Args:
            post_id: WordPress post ID.
            post_type: WordPress post type.
            force: If True, permanently delete instead of trashing.

        Returns:
            Deleted post data.

        Raises:
            WordPressAPIError: If the API request fails.
        """
        endpoint = f"{self._endpoint(post_type)}/{post_id}"
        params = {"force": force}

        logger.info("Deleting %s %d (force=%s)", post_type, post_id, force)

        return self._request("DELETE", endpoint, params=params)

    # --- Media ---

    def upload_media(
        self,
        filepath: str | Path,
        alt_text: str = "",
        title: str = "",
    ) -> dict[str, Any]:
        """Upload a media file to WordPress.

        Args:
            filepath: Local path to the file to upload.
            alt_text: Alt text for the media item.
            title: Title for the media item. Defaults to filename.

        Returns:
            Media data from WordPress (includes id, source_url, etc.).

        Raises:
            FileNotFoundError: If the file doesn't exist.
            WordPressAPIError: If the upload fails.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Media file not found: {filepath}")

        content_type = mimetypes.guess_type(str(filepath))[0] or "application/octet-stream"
        filename = filepath.name

        logger.info("Uploading media: %s (%s)", filename, content_type)

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": content_type,
        }

        with filepath.open("rb") as f:
            response = self._session.post(
                f"{self.config.api_url}/media",
                headers=headers,
                data=f,
                timeout=_TIMEOUT * 3,  # Longer timeout for uploads
            )

        self._check_response(response)
        media_data = response.json()

        # Set alt text and title if provided
        update_data: dict[str, Any] = {}
        if alt_text:
            update_data["alt_text"] = alt_text
        if title:
            update_data["title"] = title

        if update_data:
            media_id = media_data["id"]
            self._request(
                "POST",
                f"{self.config.api_url}/media/{media_id}",
                json=update_data,
            )

        return media_data

    # --- Utilities ---

    def test_connection(self) -> dict[str, Any]:
        """Test the API connection and authentication.

        Returns:
            Dict with 'ok' bool and 'user' or 'error' info.
        """
        try:
            # /users/me requires authentication
            result = self._request("GET", f"{self.config.api_url}/users/me")
            return {
                "ok": True,
                "user": result.get("name", ""),
                "user_id": result.get("id"),
            }
        except WordPressAPIError as e:
            return {
                "ok": False,
                "error": str(e),
                "status_code": e.status_code,
            }

    # --- Internal ---

    def _endpoint(self, post_type: str) -> str:
        """Build the API endpoint URL for a post type."""
        # WordPress uses 'posts' for 'post' and 'pages' for 'page'
        if post_type == "post":
            slug = "posts"
        elif post_type == "page":
            slug = "pages"
        else:
            slug = post_type  # Custom post types use their own slug

        return f"{self.config.api_url}/{slug}"

    def _prepare_post_payload(
        self,
        data: dict[str, Any],
        status: str | None,
    ) -> dict[str, Any]:
        """Prepare the payload for creating a post."""
        payload = dict(data)

        if "status" not in payload:
            payload["status"] = status or self.config.default_status

        if "author" not in payload and self.config.default_author_id:
            payload["author"] = self.config.default_author_id

        return payload

    def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        """Make an authenticated API request."""
        kwargs.setdefault("timeout", _TIMEOUT)

        response = self._session.request(method, url, **kwargs)
        self._check_response(response)
        return response.json()

    @staticmethod
    def _check_response(response: requests.Response) -> None:
        """Check for API errors and raise WordPressAPIError if needed."""
        if response.ok:
            return

        try:
            error_data = response.json()
            message = error_data.get("message", response.reason)
            code = error_data.get("code", "")
        except ValueError:
            message = response.text or response.reason
            code = ""

        raise WordPressAPIError(
            message=f"WordPress API error: {message}",
            status_code=response.status_code,
            error_code=code,
            response_body=response.text,
        )


class WordPressAPIError(Exception):
    """Raised when a WordPress REST API request fails."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: str = "",
        response_body: str = "",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.response_body = response_body
