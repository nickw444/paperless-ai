"""Paperless-AI CLI - Automated document categorization for Paperless-ngx."""

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from categorizer.engine import CategorizationEngine
from llm.factory import create_agent
from paperless.client import PaperlessClient

console = Console()


@click.group()
def cli():
    """Paperless-AI: Automated document categorization using configurable AI agents."""
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
@click.option("--apply", is_flag=True, help="Apply changes after review")
def analyze(doc_id, output, limit, export, apply):
    """Analyze inbox documents and suggest categorizations."""
    try:
        agent = create_agent()
        engine = CategorizationEngine(agent=agent)
        client = engine.paperless

        # Get documents to analyze
        if doc_id:
            documents = [client.get_document(doc_id)]
        else:
            # Exclude already-parsed documents (only when not analyzing a specific doc)
            parsed_tag_id = None
            try:
                # Check if parsed tag exists, but don't create it yet
                engine._load_metadata()
                for tag in engine._tags:
                    if tag.name.lower() == "paperless-ai-parsed":
                        parsed_tag_id = tag.id
                        break
            except Exception:
                pass  # If we can't check, continue without filtering

            documents = client.list_inbox_documents(exclude_tag_id=parsed_tag_id)
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

        # Show new entities review if any were found (only correspondents now)
        if engine.new_entities_found and any(engine.new_entities_found.values()):
            _show_new_entities_review(engine.new_entities_found)

            if apply:
                if click.confirm("\nCreate these new correspondents in Paperless?"):
                    created = _create_new_entities(engine, engine.new_entities_found)
                    console.print(
                        f"[green]✓[/green] Created {created['correspondents']} new correspondent(s)"
                    )

                    # Re-run categorization ONLY for documents with NEW correspondents
                    if engine.documents_with_new_entities:
                        count = len(engine.documents_with_new_entities)
                        if click.confirm(
                            f"\nRe-categorize {count} documents that had new correspondents?"
                        ):
                            docs_to_reprocess = [
                                doc
                                for doc in documents
                                if doc.id in engine.documents_with_new_entities
                            ]
                            new_suggestions = []
                            with console.status(
                                "[bold green]Re-categorizing documents..."
                            ) as status:
                                for i, doc in enumerate(docs_to_reprocess, 1):
                                    count_text = f"{i}/{len(docs_to_reprocess)}"
                                    status.update(
                                        f"[bold green]Re-categorizing document {count_text}..."
                                    )
                                    new_suggestion = engine.categorize_document(doc)
                                    new_suggestions.append(new_suggestion)
                            # Replace old suggestions with new ones
                            for new_sugg in new_suggestions:
                                for i, old_sugg in enumerate(suggestions):
                                    if old_sugg.document_id == new_sugg.document_id:
                                        suggestions[i] = new_sugg
                                        break

        # Apply changes if requested
        if apply and suggestions:
            if click.confirm("\nApply categorization suggestions to documents?"):
                _apply_suggestions(engine, suggestions)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def _apply_suggestions(engine, suggestions):
    """Apply categorization suggestions to documents."""
    # Get or create the paperless-ai-parsed tag
    parsed_tag_id = engine.get_or_create_parsed_tag()

    applied_count = 0
    skipped_count = 0

    with console.status("[bold green]Applying suggestions...") as status:
        for i, suggestion in enumerate(suggestions, 1):
            status.update(f"[bold green]Updating document {i}/{len(suggestions)}...")

            # Skip if there was an error
            if suggestion.status != "success":
                skipped_count += 1
                continue

            # Build tags list: include parsed tag + suggested tags
            tags = list(suggestion.suggested_tag_ids) if suggestion.suggested_tag_ids else []
            if parsed_tag_id not in tags:
                tags.append(parsed_tag_id)

            try:
                engine.paperless.update_document(
                    document_id=suggestion.document_id,
                    title=suggestion.suggested_title,
                    correspondent=suggestion.suggested_correspondent_id,
                    document_type=suggestion.suggested_type_id,
                    storage_path=suggestion.suggested_storage_path_id,
                    tags=tags,
                )
                applied_count += 1
            except Exception as e:
                console.print(
                    f"[red]✗[/red] Failed to update document {suggestion.document_id}: {e}"
                )
                skipped_count += 1

    console.print(f"\n[green]✓[/green] Applied changes to {applied_count} document(s)")
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

    with console.status("[bold green]Creating new correspondents...") as status:
        # Create correspondents
        for name in new_entities["correspondents"]:
            try:
                status.update(f"[bold green]Creating correspondent: {name}")
                engine.paperless.create_correspondent(name)
                created["correspondents"] += 1
            except Exception as e:
                console.print(f"[red]✗[/red] Failed to create correspondent '{name}': {e}")

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

    # Type
    current_type = suggestion.current_type_name or "None"
    suggested_type = suggestion.suggested_type
    if suggested_type and current_type.lower() != suggested_type.lower():
        console.print(f"  Type: [dim]{current_type}[/dim] -> [cyan]{suggested_type}[/cyan]")
    elif current_type != "None":
        console.print(f"  Type: {current_type}")

    # Tags
    current_tags = (
        ", ".join(suggestion.current_tag_names) if suggestion.current_tag_names else "None"
    )
    suggested_tags = ", ".join(suggestion.suggested_tags) if suggestion.suggested_tags else None
    if suggested_tags and current_tags.lower() != suggested_tags.lower():
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
        console.print("  [yellow]⚠️  New correspondent will be created if --apply is used[/yellow]")


if __name__ == "__main__":
    cli()
