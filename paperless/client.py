"""Paperless-ngx API client."""

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import settings
from paperless.models import (
    Correspondent,
    Document,
    DocumentType,
    PaginatedResponse,
    StoragePath,
    Tag,
)


class PaperlessClient:
    """Client for interacting with Paperless-ngx API."""

    def __init__(self):
        """Initialize the Paperless API client."""
        self.base_url = settings.paperless_url
        self.headers = {
            "Authorization": f"Token {settings.paperless_api_token}",
            "Content-Type": "application/json",
        }

        # Configure session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(self.headers)

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict:
        """Make a GET request to the API with error handling."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise ConnectionError("Authentication failed. Check your API token.") from e
            elif e.response.status_code == 404:
                raise ValueError(f"Resource not found: {url}") from e
            else:
                raise ConnectionError(f"API request failed: {e}") from e
        except requests.exceptions.Timeout as e:
            raise TimeoutError(f"Request timed out: {url}") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Failed to connect to Paperless: {url}") from e

    def _post(self, endpoint: str, data: dict[str, Any]) -> dict:
        """Make a POST request to the API with error handling."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.post(url, json=data, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise ConnectionError("Authentication failed. Check your API token.") from e
            elif e.response.status_code == 400:
                raise ValueError(f"Bad request: {e.response.text}") from e
            else:
                raise ConnectionError(f"API request failed: {e}") from e
        except requests.exceptions.Timeout as e:
            raise TimeoutError(f"Request timed out: {url}") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Failed to connect to Paperless: {url}") from e

    def _patch(self, endpoint: str, data: dict[str, Any]) -> dict:
        """Make a PATCH request to the API with error handling."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.patch(url, json=data, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise ConnectionError("Authentication failed. Check your API token.") from e
            elif e.response.status_code == 400:
                raise ValueError(f"Bad request: {e.response.text}") from e
            else:
                raise ConnectionError(f"API request failed: {e}") from e
        except requests.exceptions.Timeout as e:
            raise TimeoutError(f"Request timed out: {url}") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Failed to connect to Paperless: {url}") from e

    def _get_all_pages(self, endpoint: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Fetch all pages from a paginated endpoint."""
        all_results = []
        page = 1
        params = params or {}

        while True:
            params["page"] = page
            data = self._get(endpoint, params)
            paginated = PaginatedResponse(**data)
            all_results.extend(paginated.results)

            if not paginated.next:
                break
            page += 1
            time.sleep(0.1)  # Small delay to avoid overwhelming the server

        return all_results

    def test_connection(self) -> bool:
        """Test the connection to Paperless-ngx API."""
        try:
            self._get("/api/documents/", params={"page_size": 1})
            return True
        except Exception:
            return False

    def list_inbox_documents(self, exclude_tag_id: int | None = None) -> list[Document]:
        """
        List all documents in the inbox.

        Args:
            exclude_tag_id: Optional tag ID to exclude from results
        """
        results = self._get_all_pages("/api/documents/", params={"is_in_inbox": "true"})
        documents = [Document(**doc) for doc in results]

        # Filter out documents with the excluded tag if specified
        if exclude_tag_id is not None:
            documents = [doc for doc in documents if exclude_tag_id not in doc.tags]

        return documents

    def get_document(self, document_id: int) -> Document:
        """Get a specific document by ID."""
        data = self._get(f"/api/documents/{document_id}/")
        return Document(**data)

    def list_tags(self) -> list[Tag]:
        """List all available tags."""
        results = self._get_all_pages("/api/tags/")
        return [Tag(**tag) for tag in results]

    def list_correspondents(self) -> list[Correspondent]:
        """List all available correspondents."""
        results = self._get_all_pages("/api/correspondents/")
        return [Correspondent(**corr) for corr in results]

    def list_document_types(self) -> list[DocumentType]:
        """List all available document types."""
        results = self._get_all_pages("/api/document_types/")
        return [DocumentType(**dtype) for dtype in results]

    def list_storage_paths(self) -> list[StoragePath]:
        """List all available storage paths."""
        results = self._get_all_pages("/api/storage_paths/")
        return [StoragePath(**spath) for spath in results]

    def create_correspondent(self, name: str) -> Correspondent:
        """Create a new correspondent with ML matching enabled."""
        data = {
            "name": name,
            "matching_algorithm": 6,  # 6 = Auto (ML matching)
        }
        result = self._post("/api/correspondents/", data)
        return Correspondent(**result)

    def create_tag(self, name: str) -> Tag:
        """Create a new tag."""
        data = {"name": name}
        result = self._post("/api/tags/", data)
        return Tag(**result)

    def create_document_type(self, name: str) -> DocumentType:
        """Create a new document type."""
        data = {"name": name}
        result = self._post("/api/document_types/", data)
        return DocumentType(**result)

    def create_storage_path(self, name: str, path: str) -> StoragePath:
        """Create a new storage path."""
        data = {"name": name, "path": path}
        result = self._post("/api/storage_paths/", data)
        return StoragePath(**result)

    def update_document(
        self,
        document_id: int,
        title: str | None = None,
        correspondent: int | None = None,
        document_type: int | None = None,
        storage_path: int | None = None,
        tags: list[int] | None = None,
    ) -> Document:
        """Update a document's metadata."""
        data = {}
        if title is not None:
            data["title"] = title
        if correspondent is not None:
            data["correspondent"] = correspondent
        if document_type is not None:
            data["document_type"] = document_type
        if storage_path is not None:
            data["storage_path"] = storage_path
        if tags is not None:
            data["tags"] = tags

        result = self._patch(f"/api/documents/{document_id}/", data)
        return Document(**result)
