from __future__ import annotations

import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import fitz
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class PageInfo:
    page_number: int
    is_scanned: bool
    text: str
    tables: list[dict] = field(default_factory=list)
    image_path: Optional[str] = None
    text_density: float = 0.0


@dataclass 
class ParseResult:
    source_file: str
    page_count: int
    pages: list[PageInfo]
    has_scanned_pages: bool
    full_markdown: str
    tables: list[dict]
    pipeline_used: str
    cropped_table_images: list[str] = field(default_factory=list)


def _detect_scanned_pages(pdf_path: Path) -> list[bool]:
    doc = fitz.open(str(pdf_path))
    results = []
    for page in doc:
        text = page.get_text().strip()
        images = page.get_images()
        is_scanned = len(text) < 50 and len(images) > 0
        results.append(is_scanned)
        logger.debug(
            f"Page {page.number + 1}: text_len={len(text)}, images={len(images)}, "
            f"scanned={is_scanned}"
        )
    doc.close()
    return results


def _calculate_text_density(pdf_path: Path, page_num: int) -> float:
    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    text = page.get_text().strip()
    doc.close()
    
    max_chars = 3000.0
    char_count = len(text)
    density = min(char_count / max_chars, 1.0)
    logger.debug(f"Page {page_num + 1} text density: {density:.3f} ({char_count} chars)")
    return float(density)


def _render_page_to_png(pdf_path: Path, page_num: int, output_dir: Path, dpi: int = 200) -> Path:
    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / f"page_{page_num + 1}.png"
    pix.save(str(png_path))
    doc.close()
    logger.debug(f"Rendered page {page_num + 1} to {png_path}")
    return png_path


def _crop_table_regions(pdf_path: Path, page_num: int, doc_result, output_dir: Path, dpi: int = 200) -> list[str]:
    cropped_paths = []
    tables = getattr(doc_result.document, 'tables', [])
    
    page_tables = []
    for idx, table in enumerate(tables):
        if hasattr(table, 'prov') and table.prov:
            prov = table.prov[0] if isinstance(table.prov, list) and len(table.prov) > 0 else table.prov
            prov_page = getattr(prov, 'page_no', None)
            if prov_page == page_num + 1 and hasattr(prov, 'bbox'):
                page_tables.append((idx, prov.bbox))
    
    if not page_tables:
        return []
    
    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    full_page_path = output_dir / f"temp_page_{page_num + 1}_full.png"
    pix.save(str(full_page_path))
    
    page_width, page_height = page.rect.width, page.rect.height
    doc.close()
    
    with Image.open(full_page_path) as img:
        img_width, img_height = img.size
        scale_x = img_width / page_width
        scale_y = img_height / page_height
        
        for table_idx, bbox in page_tables:
            if hasattr(bbox, 'l') and hasattr(bbox, 't') and hasattr(bbox, 'r') and hasattr(bbox, 'b'):
                l, t, r, b = bbox.l, bbox.t, bbox.r, bbox.b
            elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                l, t, r, b = bbox
            else:
                logger.warning(f"Unrecognized bbox format for table {table_idx}: {bbox}")
                continue
                
            if hasattr(bbox, 'coord_origin') and bbox.coord_origin == "bottom-left":
                t, b = page_height - b, page_height - t
                
            px_l = l * scale_x
            px_t = t * scale_y
            px_r = r * scale_x
            px_b = b * scale_y
            
            px_l, px_r = min(px_l, px_r), max(px_l, px_r)
            px_t, px_b = min(px_t, px_b), max(px_t, px_b)
            
            pad_x = (px_r - px_l) * 0.05
            pad_y = (px_b - px_t) * 0.05
            
            crop_box = (
                max(0, px_l - pad_x),
                max(0, px_t - pad_y),
                min(img_width, px_r + pad_x),
                min(img_height, px_b + pad_y)
            )
            
            cropped = img.crop(crop_box)
            crop_path = output_dir / f"table_crop_{page_num + 1}_{table_idx}.png"
            cropped.save(crop_path)
            cropped_paths.append(str(crop_path))
            logger.info(f"Cropped table {table_idx} from page {page_num + 1} to {crop_path}")
            
    if full_page_path.exists():
        full_page_path.unlink()
        
    return cropped_paths


def _adaptive_resize(image_path: Path, max_size: int = 1024) -> Path:
    with Image.open(image_path) as img:
        width, height = img.size
        if width > max_size or height > max_size:
            ratio = min(max_size / width, max_size / height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            img.save(image_path)
            logger.debug(f"Resized {image_path.name} from {width}x{height} to {new_size}")
    return image_path


def _extract_tables_from_docling(doc_result) -> list[dict]:
    all_tables = []
    
    try:
        tables = getattr(doc_result.document, 'tables', [])
        for table in tables:
            try:
                df = table.export_to_dataframe()
                headers = [str(h) for h in df.columns.tolist()]
                rows = [[str(cell) for cell in row] for row in df.values.tolist()]
                all_tables.append({"headers": headers, "rows": rows})
            except Exception as e:
                logger.debug(f"DataFrame export failed, trying raw data: {e}")
                try:
                    grid = table.data
                    if grid and len(grid) > 0:
                        headers = [str(cell.text if hasattr(cell, 'text') else cell) for cell in grid[0]]
                        rows = [
                            [str(cell.text if hasattr(cell, 'text') else cell) for cell in row]
                            for row in grid[1:]
                        ]
                        all_tables.append({"headers": headers, "rows": rows})
                except Exception as e2:
                    logger.warning(f"Table extraction fallback also failed: {e2}")
    except Exception as e:
        logger.warning(f"Could not extract tables from Docling result: {e}")
    
    return all_tables


def parse_pdf(pdf_path: str | Path, render_dir: Optional[Path] = None) -> ParseResult:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    if render_dir is None:
        render_dir = pdf_path.parent / ".renders"
    
    logger.info(f"Parsing {pdf_path.name}...")
    
    scanned_flags = _detect_scanned_pages(pdf_path)
    has_scanned = any(scanned_flags)
    has_native = any(not s for s in scanned_flags)
    
    if has_scanned and has_native:
        pipeline = "hybrid"
    elif has_scanned:
        pipeline = "ocr"
    else:
        pipeline = "native"
    
    logger.info(f"Pipeline: {pipeline} ({sum(scanned_flags)} scanned / {len(scanned_flags) - sum(scanned_flags)} native pages)")
    
    from docling.document_converter import DocumentConverter
    
    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    
    full_markdown = result.document.export_to_markdown()
    all_tables = _extract_tables_from_docling(result)
    
    pages = []
    all_cropped_tables = []
    
    for i, is_scanned in enumerate(scanned_flags):
        image_path = None
        text_density = _calculate_text_density(pdf_path, i)
        
        if is_scanned:
            png_path = _render_page_to_png(pdf_path, i, render_dir)
            png_path = _adaptive_resize(png_path)
            image_path = str(png_path)
            
            cropped_paths = _crop_table_regions(pdf_path, i, result, render_dir)
            all_cropped_tables.extend(cropped_paths)
            
        pages.append(PageInfo(
            page_number=i + 1,
            is_scanned=is_scanned,
            text="",
            image_path=image_path,
            text_density=text_density,
        ))
    
    return ParseResult(
        source_file=pdf_path.name,
        page_count=len(scanned_flags),
        pages=pages,
        has_scanned_pages=has_scanned,
        full_markdown=full_markdown,
        tables=all_tables,
        pipeline_used=pipeline,
        cropped_table_images=all_cropped_tables,
    )
