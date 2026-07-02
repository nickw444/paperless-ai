"""Paperless-AI CLI - Automated document categorization for Paperless-ngx."""

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from categorizer.engine import FAILED_TAG_NAME, PARSED_TAG_NAME, CategorizationEngine
from llm.codex import CodexAgent
from llm.debug import print_agent_debug_traces
from paperless.client import PaperlessClient

console = Console()


@click.group()
def cli():
    """Paperless-AI: Automated document categorization using the Codex CLI."""
    pass


@cli.command()
def test_connection():
    """Test connection to Paperless-ngx API."""
    try:
        client = PaperlessClient()
        if client.test_connection():
            console.print("[green]✓[/green] Successfully connected to Paperless-ngx API")
            sys.exit(0)
        else:
            console.print("[red]✗[/red] Failed to connect to Paperless-ngx API")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]✗[/red] Connection error: {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--output", type=click.Choice(["table", "json"]), default="table", help="Output format"
)
def list_inbox(output):
    """List all documents in the inbox."""
    try:
        client = PaperlessClient()
        documents = client.list_inbox_documents()

        if output == "json":
            data = [
                {
                    "id": doc.id,
                    "title": doc.title,
                    "created": doc.created.isoformat(),
                    "original_file_name": doc.original_file_name,
                }
                for doc in documents
            ]
            console.print(json.dumps(data, indent=2))
        else:
            table = Table(title=f"Inbox Documents ({len(documents)} total)")
            table.add_column("ID", style="cyan")
            table.add_column("Title", style="white")
            table.add_column("Created", style="yellow")
            table.add_column("Original File", style="dim")

            for doc in documents:
                table.add_row(
                    str(doc.id),
                    doc.title,
                    doc.created_date,
                    doc.original_file_name,
                )

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@cli.command()
@click.option("--id", "doc_id", type=int, help="Analyze specific document by ID")
@click.option(
    "--output", type=click.Choice(["table", "json"]), default="table", help="Output format"
)
@click.option("--limit", type=int, help="Process only first N documents")
@click.option("--export", type=click.Path(), help="Export suggestions to file (JSON)")
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Automatically confirm apply-time prompts",
)
@click.option("--debug", is_flag=True, help="Print agent inputs and outputs for inspection")
@click.option(
    "--reprocess-stale",
    is_flag=True,
    help="Include parsed inbox documents whose paperless-ai version differs from config",
)
@click.option(
    "--reprocess-all",
    is_flag=True,
    help="Include all inbox documents, even if already parsed",
)
def analyze(doc_id, output, limit, export, yes, debug, reprocess_stale, reprocess_all):
    """Analyze inbox documents and suggest categorizations."""
    try:
        if reprocess_stale and reprocess_all:
            raise click.UsageError("--reprocess-stale and --reprocess-all cannot be used together")

        agent = CodexAgent(debug=debug)
        engine = CategorizationEngine(agent=agent)
        client = engine.paperless

        # Get documents to analyze
        if doc_id:
            documents = [client.get_document(doc_id)]
        else:
            # Exclude already-tracked documents unless explicitly reprocessing.
            excluded_tag_ids = []
            parsed_tag_id = None
            try:
                # Check if tracking tags exist, but don't create them yet.
                for tag_name in (PARSED_TAG_NAME, FAILED_TAG_NAME):
                    tag_id = engine.get_tag_id_by_name(tag_name)
                    if tag_id is not None:
                        if tag_name == PARSED_TAG_NAME:
                            parsed_tag_id = tag_id
                        if not (reprocess_stale or reprocess_all):
                            excluded_tag_ids.append(tag_id)
            except Exception:
                pass  # If we can't check, continue without filtering

            documents = client.list_inbox_documents(exclude_tag_ids=excluded_tag_ids)
            if reprocess_stale:
                version_field_id = engine.get_processing_version_custom_field_id()
                documents = [
                    doc
                    for doc in documents
                    if _should_analyze_for_stale_reprocessing(
                        engine,
                        doc,
                        parsed_tag_id,
                        version_field_id,
                    )
                ]
            if limit:
                documents = documents[:limit]

        if not documents:
            console.print("[yellow]No documents to analyze[/yellow]")
            return

        # Analyze documents
        suggestions = []
        with console.status("[bold green]Analyzing documents...") as status:
            for i, doc in enumerate(documents, 1):
                status.update(f"[bold green]Analyzing document {i}/{len(documents)}...")
                suggestion = engine.categorize_document(doc)
                if debug and engine.last_agent_result:
                    print_agent_debug_traces(
                        console,
                        engine.last_agent_result.debug_traces,
                        document_id=doc.id,
                    )
                suggestions.append(suggestion)

        # Export if requested
        if export:
            with open(export, "w") as f:
                data = [s.model_dump() for s in suggestions]
                json.dump(data, f, indent=2, default=str)
            console.print(f"[green]✓[/green] Exported suggestions to {export}")

        # Display results
        if output == "json":
            console.print(json.dumps([s.model_dump() for s in suggestions], indent=2, default=str))
        else:
            for suggestion in suggestions:
                _display_suggestion(suggestion)

        has_new_entities = engine.new_entities_found and any(engine.new_entities_found.values())
        if has_new_entities:
            _show_new_entities_review(engine.new_entities_found)

        if suggestions and _confirm_or_yes(
            "\nApply categorization suggestions to documents?",
            yes=yes,
        ):
            if has_new_entities:
                created = _create_new_entities(engine, engine.new_entities_found)
                console.print(
                    f"[green]✓[/green] Created {created['correspondents']} new correspondent(s)"
                )
            _apply_suggestions(engine, suggestions)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def _confirm_or_yes(prompt: str, *, yes: bool, confirm=click.confirm) -> bool:
    """Return True for --yes, otherwise ask the user for confirmation."""
    if yes:
        return True
    return confirm(prompt)


def _apply_suggestions(engine, suggestions):
    """Apply categorization suggestions to documents."""
    parsed_tag_id = None
    failed_tag_id = None

    applied_count = 0
    failed_tagged_count = 0
    skipped_count = 0

    with console.status("[bold green]Applying suggestions...") as status:
        for i, suggestion in enumerate(suggestions, 1):
            status.update(f"[bold green]Updating document {i}/{len(suggestions)}...")

            # Track analysis failures so normal inbox runs do not retry them forever.
            if suggestion.status != "success":
                if failed_tag_id is None:
                    failed_tag_id = engine.get_or_create_failed_tag()

                tags = list(suggestion.current_tags)
                if failed_tag_id not in tags:
                    tags.append(failed_tag_id)

                try:
                    update_kwargs = {
                        "document_id": suggestion.document_id,
                        "tags": tags,
                    }
                    custom_fields = engine.processing_custom_field_values(
                        suggestion.processing_metadata
                    )
                    if custom_fields:
                        update_kwargs["custom_fields"] = custom_fields
                    engine.paperless.update_document(**update_kwargs)
                    failed_tagged_count += 1
                except Exception as e:
                    console.print(
                        f"[red]✗[/red] Failed to tag document "
                        f"{suggestion.document_id} as failed: {e}"
                    )
                    skipped_count += 1
                continue

            if engine.has_unresolved_new_correspondent(suggestion):
                console.print(
                    f"[yellow]⚠️[/yellow] Skipped document {suggestion.document_id}: "
                    f"unresolved new correspondent "
                    f"'{suggestion.suggested_correspondent}'"
                )
                skipped_count += 1
                continue

            if parsed_tag_id is None:
                parsed_tag_id = engine.get_or_create_parsed_tag()

            # Build tags list: include parsed tag + suggested tags
            tags = list(suggestion.suggested_tag_ids) if suggestion.suggested_tag_ids else []
            if parsed_tag_id not in tags:
                tags.append(parsed_tag_id)

            try:
                engine.paperless.update_document(
                    document_id=suggestion.document_id,
                    title=suggestion.suggested_title,
                    content=suggestion.suggested_content,
                    correspondent=engine.resolve_suggestion_correspondent_id(suggestion),
                    document_type=suggestion.suggested_type_id,
                    storage_path=suggestion.suggested_storage_path_id,
                    tags=tags,
                    custom_fields=engine.processing_custom_field_values(
                        suggestion.processing_metadata
                    ),
                )
                applied_count += 1
            except Exception as e:
                console.print(
                    f"[red]✗[/red] Failed to update document {suggestion.document_id}: {e}"
                )
                skipped_count += 1

    console.print(f"\n[green]✓[/green] Applied changes to {applied_count} document(s)")
    if failed_tagged_count > 0:
        console.print(
            f"[yellow]⚠️[/yellow] Tagged {failed_tagged_count} failed document(s) "
            f"with {FAILED_TAG_NAME}"
        )
    if skipped_count > 0:
        console.print(f"[yellow]⚠️[/yellow] Skipped {skipped_count} document(s)")


def _show_new_entities_review(new_entities):
    """Display new entities for review."""
    console.print("\n[bold]New Entities Detected:[/bold]\n")

    if new_entities["correspondents"]:
        console.print("[yellow]NEW CORRESPONDENTS:[/yellow]")
        for name, doc_ids in new_entities["correspondents"].items():
            console.print(f"  • {name} (found in {len(doc_ids)} documents)")


def _create_new_entities(engine, new_entities):
    """Create new entities in Paperless (only correspondents)."""
    created = {"correspondents": 0}
    created_names: list[str] = []

    with console.status("[bold green]Creating new correspondents...") as status:
        # Create correspondents
        for name in new_entities["correspondents"]:
            try:
                status.update(f"[bold green]Creating correspondent: {name}")
                engine.paperless.create_correspondent(name)
                created["correspondents"] += 1
                created_names.append(name)
            except Exception as e:
                console.print(f"[red]✗[/red] Failed to create correspondent '{name}': {e}")

    engine.remove_pending_correspondents(created_names)

    # Invalidate cache so the engine will reload metadata
    engine._correspondents = None
    engine._load_metadata()

    return created


def _display_suggestion(suggestion):
    """Display a single categorization suggestion."""
    # Status indicator
    if suggestion.status == "success":
        status_icon = "[green]✓[/green]"
    else:
        status_icon = "[red]✗[/red]"

    console.print(f"\n{status_icon} [bold]Document ID: {suggestion.document_id}[/bold]")

    if suggestion.error_message:
        console.print(f"  [red]Error:[/red] {suggestion.error_message}")
        return

    # Title
    current_title = f'"{suggestion.current_title}"'
    suggested_title = f'"{suggestion.suggested_title}"' if suggestion.suggested_title else None
    if suggested_title and current_title != suggested_title:
        console.print(f"  Title: [dim]{current_title}[/dim] -> [cyan]{suggested_title}[/cyan]")
    else:
        console.print(f"  Title: {current_title}")

    if suggestion.suggested_content:
        console.print(
            f"  Content: [cyan]LLM OCR replacement suggested "
            f"({len(suggestion.suggested_content):,} chars)[/cyan]"
        )

    # Type
    current_type = suggestion.current_type_name or "None"
    suggested_type = suggestion.suggested_type
    if suggested_type and current_type.lower() != suggested_type.lower():
        console.print(f"  Type: [dim]{current_type}[/dim] -> [cyan]{suggested_type}[/cyan]")
    elif current_type != "None":
        console.print(f"  Type: {current_type}")

    # Tags
    current_tag_names = suggestion.current_tag_names
    suggested_tag_names = suggestion.suggested_tags
    current_tags = ", ".join(current_tag_names) if current_tag_names else "None"
    suggested_tags = ", ".join(suggested_tag_names) if suggested_tag_names else None
    tags_unchanged = {name.lower() for name in current_tag_names} == {
        name.lower() for name in suggested_tag_names
    }
    if suggested_tags and not tags_unchanged:
        console.print(f"  Tags: [dim]{current_tags}[/dim] -> [cyan]{suggested_tags}[/cyan]")
    elif current_tags != "None":
        console.print(f"  Tags: {current_tags}")

    # Correspondent
    current_corr = suggestion.current_correspondent_name or "None"
    suggested_corr = suggestion.suggested_correspondent
    if suggested_corr and current_corr.lower() != suggested_corr.lower():
        if suggestion.suggested_correspondent_is_new:
            corr_display = f"[yellow]NEW: {suggested_corr}[/yellow]"
        else:
            corr_display = f"[cyan]{suggested_corr}[/cyan]"
        console.print(f"  Correspondent: [dim]{current_corr}[/dim] -> {corr_display}")
    elif current_corr != "None":
        console.print(f"  Correspondent: {current_corr}")

    # Storage Path
    current_storage = suggestion.current_storage_path_name or "None"
    suggested_storage = suggestion.suggested_storage_path
    if suggested_storage and current_storage.lower() != suggested_storage.lower():
        console.print(
            f"  Storage Path: [dim]{current_storage}[/dim] -> [cyan]{suggested_storage}[/cyan]"
        )
    elif current_storage != "None":
        console.print(f"  Storage Path: {current_storage}")

    # Show warning if there are NEW correspondents
    if suggestion.suggested_correspondent_is_new:
        console.print("  [yellow]⚠️  New correspondent will be created during review[/yellow]")


def _should_analyze_for_stale_reprocessing(
    engine: CategorizationEngine,
    document,
    parsed_tag_id: int | None,
    version_field_id: int | None,
) -> bool:
    """Return whether a document should be analyzed under --reprocess-stale."""
    if parsed_tag_id is None or parsed_tag_id not in document.tags:
        return True
    return engine.is_document_processing_stale(document, version_field_id)


def _exclude_documents_with_tag(documents, tag_id: int | None):
    """Return documents excluding any document with the given tag id."""
    if tag_id is None:
        return documents
    return [doc for doc in documents if tag_id not in doc.tags]


if __name__ == "__main__":
    cli()
