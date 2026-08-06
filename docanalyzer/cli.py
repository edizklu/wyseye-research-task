from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from . import __version__

app = typer.Typer(
    name="docanalyze",
    help="On-Premise LLM Document Analyzer — Extract structured JSON from PDFs",
    add_completion=False,
)
console = Console()

PHASE_COLORS = {1: "cyan", 2: "yellow", 3: "magenta"}


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command()
def analyze(
    pdf_path: Path = typer.Argument(
        ...,
        help="Path to the PDF file to analyze",
        exists=True,
        readable=True,
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output JSON file path (default: outputs/<filename>.json)",
    ),
    fast_model: str = typer.Option(
        "phi4-mini", "--fast-model", "-f",
        help="Fast LLM for metadata extraction (Phase 1)",
    ),
    deep_model: str = typer.Option(
        "qwen2.5:latest", "--deep-model", "-d",
        help="Deep LLM for tables & entities (Phase 2-3)",
    ),
    vlm_model: str = typer.Option(
        "qwen2.5vl:7b", "--vlm-model",
        help="Vision model for scanned page analysis",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Enable verbose logging with timing info",
    ),
    stream: bool = typer.Option(
        True, "--stream/--no-stream",
        help="Enable streaming + chunked output (default: enabled)",
    ),
) -> None:
    _setup_logging(verbose)
    
    total_start = time.time()
    
    if output is None:
        output_dir = Path("outputs")
        output_dir.mkdir(exist_ok=True)
        output = output_dir / f"{pdf_path.stem}.json"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
    
    console.print(Panel(
        f"[bold cyan]Document Analyzer v{__version__}[/bold cyan]\n"
        f"  Input:  [white]{pdf_path}[/white]\n"
        f"  Output: [white]{output}[/white]\n"
        f"  Fast: [cyan]{fast_model}[/cyan]  |  Deep: [yellow]{deep_model}[/yellow]  |  VLM: [magenta]{vlm_model}[/magenta]\n"
        f"  Mode:   [white]{'Dual LLM Streaming + Chunked' if stream else 'Single-shot'}[/white]",
        title="[bold]On-Premise LLM Document Analyzer[/bold]",
        border_style="cyan",
    ))
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Parsing PDF with Docling...", total=None)
            
            from .parser import parse_pdf
            parse_start = time.time()
            parse_result = parse_pdf(pdf_path)
            parse_duration = time.time() - parse_start
            
            progress.update(task, description=f"[green] Parsed {parse_result.page_count} pages ({parse_result.pipeline_used}) [{parse_duration:.1f}s]")
            progress.stop()
        
        if verbose:
            console.print(f"  Pipeline: [yellow]{parse_result.pipeline_used}[/yellow]")
            console.print(f"  Scanned pages: [yellow]{sum(1 for p in parse_result.pages if p.is_scanned)}[/yellow]")
            console.print(f"  Tables found: [yellow]{len(parse_result.tables)}[/yellow]")
            console.print(f"  Markdown length: [yellow]{len(parse_result.full_markdown)} chars[/yellow]")
        
        vlm_results = None
        text_densities = {
            p.page_number: p.text_density
            for p in parse_result.pages if p.is_scanned
        }
        
        if parse_result.has_scanned_pages:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                scanned_images = [
                    p.image_path for p in parse_result.pages 
                    if p.is_scanned and p.image_path
                ]
                task = progress.add_task(
                    f"[cyan]Analyzing {len(scanned_images)} scanned page(s) with VLM ({vlm_model})...", 
                    total=None
                )
                
                from .vision import analyze_scanned_pages
                vlm_start = time.time()
                vlm_results = analyze_scanned_pages(
                    scanned_images, model=vlm_model,
                    text_densities=text_densities,
                )
                vlm_duration = time.time() - vlm_start
                
                skipped = len(scanned_images) - len(vlm_results or {})
                skip_info = f", {skipped} skipped" if skipped > 0 else ""
                progress.update(task, description=f"[green] VLM analysis complete [{vlm_duration:.1f}s{skip_info}]")
                progress.stop()
        
        ocr_engine = "rapidocr" if parse_result.has_scanned_pages else None
        
        if stream:
            doc_analysis = _run_streaming_extraction(
                parse_result=parse_result,
                vlm_results=vlm_results,
                fast_model=fast_model,
                deep_model=deep_model,
                ocr_engine=ocr_engine,
            )
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("[cyan]Extracting structured JSON with LLM...", total=None)
                
                from .extractor import extract_document_json
                extract_start = time.time()
                
                doc_analysis = extract_document_json(
                    source_file=parse_result.source_file,
                    page_count=parse_result.page_count,
                    pipeline_used=parse_result.pipeline_used,
                    markdown_content=parse_result.full_markdown,
                    vlm_results=vlm_results,
                    model=fast_model,
                    ocr_engine=ocr_engine,
                )
                extract_duration = time.time() - extract_start
                
                progress.update(task, description=f"[green] JSON extraction complete [{extract_duration:.1f}s]")
                progress.stop()
        
        total_duration = time.time() - total_start
        doc_analysis.document.processing.duration_seconds = round(total_duration, 2)
        
        output_json = doc_analysis.model_dump_json(indent=2)
        output.write_text(output_json, encoding="utf-8")
        
        console.print()
        console.print(Panel(
            f"[bold green]Analysis complete![/bold green]\n\n"
            f"  Type: [white]{doc_analysis.document.document_type}[/white]\n"
            f"  Tables: [white]{len(doc_analysis.tables)}[/white]\n"
            f"  Key-Values: [white]{len(doc_analysis.key_values)}[/white]\n"
            f"  Entities: [white]{len(doc_analysis.entities)}[/white]\n"
            f"  Duration: [white]{total_duration:.1f}s[/white]\n"
            f"  Saved to: [white]{output}[/white]",
            title="[bold]Results[/bold]",
            border_style="green",
        ))
        
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1)


def _run_streaming_extraction(
    parse_result,
    vlm_results,
    fast_model: str,
    deep_model: str,
    ocr_engine: str | None,
) -> "DocumentAnalysis":
    from .extractor import extract_document_chunked_streaming
    
    phase_timings = {}
    
    def on_phase_start(phase: int, label: str):
        color = PHASE_COLORS.get(phase, "white")
        console.print(f"\n  [bold {color}]Phase {phase}/3: {label}[/bold {color}]")
        console.print(f"  [dim]{'─' * 60}[/dim]")
    
    def on_token(token: str, phase: int):
        sys.stderr.write(f"\033[90m{token}\033[0m")
        sys.stderr.flush()
    
    def on_phase_end(phase: int, label: str, duration: float):
        sys.stderr.write("\n")
        sys.stderr.flush()
        console.print(f"  [green]{label} complete [{duration:.1f}s][/green]")
        phase_timings[phase] = duration
    
    doc_analysis = extract_document_chunked_streaming(
        source_file=parse_result.source_file,
        page_count=parse_result.page_count,
        pipeline_used=parse_result.pipeline_used,
        markdown_content=parse_result.full_markdown,
        vlm_results=vlm_results,
        fast_model=fast_model,
        deep_model=deep_model,
        ocr_engine=ocr_engine,
        on_token=on_token,
        on_phase_start=on_phase_start,
        on_phase_end=on_phase_end,
    )
    
    return doc_analysis


@app.command()
def schema() -> None:
    from .schema import get_json_schema
    console.print_json(json.dumps(get_json_schema(), indent=2))


@app.command()
def version() -> None:
    console.print(f"docanalyze v{__version__}")


def main() -> None:
    app()
