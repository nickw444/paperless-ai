"""Tests for analyze command workflow helpers."""

from datetime import datetime

import pytest
from click import UsageError

from main import _select_documents_for_analysis, _validate_analyze_options
from paperless.models import Document


class CapturingPaperless:
    def __init__(self, documents):
        self.documents = documents
        self.exclude_tag_ids: list[int] | None = None
        self.requested_document_id: int | None = None

    def get_document(self, document_id: int):
        self.requested_document_id = document_id
        return self.documents[0]

    def list_inbox_documents(self, *, exclude_tag_ids=None):
        self.exclude_tag_ids = exclude_tag_ids
        return self.documents


class SelectionEngine:
    def __init__(self, documents):
        self.paperless = CapturingPaperless(documents)
        self.version_field_requests = 0

    def get_tag_id_by_name(self, name: str) -> int | None:
        return {
            "paperless-ai-parsed": 20,
            "paperless-ai-failed": 30,
        }.get(name)

    def get_processing_version_custom_field_id(self) -> int:
        self.version_field_requests += 1
        return 10

    def is_document_processing_stale(self, document, version_field_id: int | None) -> bool:
        return version_field_id == 10 and document.id == 2


def test_validate_analyze_options_rejects_conflicting_reprocess_modes():
    with pytest.raises(
        UsageError,
        match="--reprocess-stale and --reprocess-all cannot be used together",
    ):
        _validate_analyze_options(
            reprocess_stale=True,
            reprocess_all=True,
        )


def test_select_documents_excludes_tracked_tags_and_applies_limit():
    engine = SelectionEngine([_document(1), _document(2), _document(3)])

    documents = _select_documents_for_analysis(
        engine,
        doc_id=None,
        limit=2,
        reprocess_stale=False,
        reprocess_all=False,
    )

    assert [document.id for document in documents] == [1, 2]
    assert engine.paperless.exclude_tag_ids == [20, 30]


def test_select_documents_fetches_specific_document_without_inbox_filtering():
    engine = SelectionEngine([_document(42)])

    documents = _select_documents_for_analysis(
        engine,
        doc_id=42,
        limit=None,
        reprocess_stale=False,
        reprocess_all=False,
    )

    assert [document.id for document in documents] == [42]
    assert engine.paperless.requested_document_id == 42
    assert engine.paperless.exclude_tag_ids is None


def test_select_documents_reprocess_stale_keeps_unparsed_and_stale_documents():
    engine = SelectionEngine(
        [_document(1, tags=[]), _document(2, tags=[20]), _document(3, tags=[20])]
    )

    documents = _select_documents_for_analysis(
        engine,
        doc_id=None,
        limit=None,
        reprocess_stale=True,
        reprocess_all=False,
    )

    assert [document.id for document in documents] == [1, 2]
    assert engine.paperless.exclude_tag_ids == []
    assert engine.version_field_requests == 1


def _document(document_id: int, *, tags: list[int] | None = None) -> Document:
    timestamp = datetime(2024, 1, 1)
    return Document(
        id=document_id,
        title="scan.pdf",
        content="Invoice",
        tags=tags or [],
        created=timestamp,
        created_date="2024-01-01",
        modified=timestamp,
        added=timestamp,
        original_file_name="scan.pdf",
    )
