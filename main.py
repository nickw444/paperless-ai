"""Paperless-AI CLI - Automated document categorization for Paperless-ngx."""

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from categorizer.engine import CategorizationEngine
from paperless.client import PaperlessClient

console = Console()


@click.group()
def cli():
    """Paperless-AI: Automated document categorization using Claude."""
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
def analyze(doc_id, output, limit, export):
    """Analyze inbox documents and suggest categorizations (READ-ONLY)."""
    try:
        engine = CategorizationEngine()
        client = engine.paperless

        # Get documents to analyze
        if doc_id:
            documents = [client.get_document(doc_id)]
        else:
            documents = client.list_inbox_documents()
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

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


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
    console.print(f'  Current Title: [dim]"{suggestion.current_title}"[/dim]')
    if suggestion.suggested_title:
        console.print(f'  Suggested Title: [cyan]"{suggestion.suggested_title}"[/cyan]')

    # Type
    current_type_display = suggestion.current_type_name or "[dim]None[/dim]"
    console.print(f"  Current Type: {current_type_display}")
    if suggestion.suggested_type:
        console.print(f"  Suggested Type: [cyan]{suggestion.suggested_type}[/cyan]")

    # Tags
    current_tags_display = (
        ", ".join(suggestion.current_tag_names)
        if suggestion.current_tag_names
        else "[dim]None[/dim]"
    )
    console.print(f"  Current Tags: {current_tags_display}")
    if suggestion.suggested_tags:
        console.print(f"  Suggested Tags: [cyan]{', '.join(suggestion.suggested_tags)}[/cyan]")

    # Correspondent
    current_corr_display = suggestion.current_correspondent_name or "[dim]None[/dim]"
    console.print(f"  Current Correspondent: {current_corr_display}")
    if suggestion.suggested_correspondent:
        console.print(
            f"  Suggested Correspondent: [cyan]{suggestion.suggested_correspondent}[/cyan]"
        )


if __name__ == "__main__":
    cli()
