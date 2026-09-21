from __future__ import annotations

import typer

from loomset.config import load_config
from loomset.pipeline import run_pipeline, stage_cleaning, stage_discovery, stage_export, stage_extraction, stage_labeling, stage_review, stage_scraping, status_summary

app = typer.Typer(help="LoomSet pipeline CLI")


@app.command()
def run(
    query: str = typer.Option(..., "--query", help="Search query to process"),
    max_results: int = typer.Option(10, "--max-results", help="Maximum search results"),
    db_path: str | None = typer.Option(None, "--db-path", help="SQLite database path"),
    export_dir: str | None = typer.Option(None, "--export-dir", help="Dataset export directory"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Runtime data directory"),
):
    result = run_pipeline(
        query=query,
        max_results=max_results,
        db_path=db_path,
        export_dir=export_dir,
        data_dir=data_dir,
    )
    typer.echo(f"Exported {len(result['records'])} records to {result['dataset_path']}")


@app.command()
def status(
    db_path: str | None = typer.Option(None, "--db-path", help="SQLite database path"),
):
    config = load_config()
    target = db_path or config.project.db_path
    summary = status_summary(target)
    if not summary:
        typer.echo("No records in the database yet.")
        return
    for key, value in sorted(summary.items()):
        typer.echo(f"{key}: {value}")


@app.command()
def run_stage(
    stage: str = typer.Argument(..., help="Stage name: discovery, scraping, extraction, cleaning, labeling, review, export"),
    query: str | None = typer.Option(None, "--query", help="Query for discovery stage"),
    max_results: int = typer.Option(10, "--max-results", help="Maximum results for discovery stage"),
    db_path: str | None = typer.Option(None, "--db-path", help="SQLite database path"),
    export_dir: str | None = typer.Option(None, "--export-dir", help="Dataset export directory"),
    labels: str | None = typer.Option(None, "--labels", help="Comma-separated labels to use for labeling stage"),
    output_path: str | None = typer.Option(None, "--output-path", help="Review export file path"),
):
    config = load_config()
    db_target = db_path or config.project.db_path
    export_target = export_dir or config.project.export_dir
    if stage == "discovery":
        if query is None:
            raise typer.BadParameter("--query is required for discovery stage")
        docs = stage_discovery(query=query, max_results=max_results, db_path=db_target)
        typer.echo(f"Discovered {len(docs)} URLs")
    elif stage == "scraping":
        docs = stage_scraping(db_path=db_target, min_html_chars=config.scraping.min_html_chars)
        typer.echo(f"Scraped {len(docs)} documents")
    elif stage == "extraction":
        docs = stage_extraction(db_path=db_target)
        typer.echo(f"Extracted {len(docs)} documents")
    elif stage == "cleaning":
        docs = stage_cleaning(db_path=db_target, languages=config.cleaning.languages, min_text_length=config.cleaning.min_text_length)
        typer.echo(f"Cleaned {len(docs)} documents")
    elif stage == "labeling":
        label_values = [item.strip() for item in (labels or ",".join(config.labeling.allowed_labels)).split(",") if item.strip()]
        docs = stage_labeling(db_path=db_target, labels=label_values)
        typer.echo(f"Labeled {len(docs)} documents")
    elif stage == "review":
        result = stage_review(db_path=db_target, output_path=output_path)
        typer.echo(f"Prepared {len(result['records'])} review records at {result['output_path']}")
    elif stage == "export":
        result = stage_export(db_path=db_target, export_dir=export_target)
        typer.echo(f"Exported {len(result['records'])} records")
    else:
        raise typer.BadParameter(f"Unknown stage: {stage}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Server host"),
    port: int = typer.Option(8000, "--port", help="Server port"),
):
    """Start the LoomSet web server."""
    import uvicorn
    uvicorn.run("loomset.server:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    app()
