from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"

VISION_PROMPT = """Analyze this document page image carefully. Extract ALL information you can see:

1. **Text content**: All readable text, preserving structure and layout
2. **Form fields**: Any labeled fields with their values (e.g., "Invoice No: 12345")
3. **Tables**: Describe table structure with headers and cell values
4. **Visual elements**: Logos, stamps, signatures, charts, diagrams — describe them
5. **Layout**: How the content is organized (columns, sections, headers)

Provide your analysis as structured text. Be thorough and accurate.
For tables, use markdown table format.
For form fields, use "Key: Value" format.
/no_think
"""

TABLE_VISION_PROMPT = """Analyze this cropped table image. Extract the COMPLETE table structure:

1. **Headers**: List all column headers exactly as shown
2. **Rows**: List every row with exact cell values
3. **Formatting**: Preserve numbers, currencies, percentages exactly

Output the table in markdown table format. Be precise — do not miss any cell.
/no_think
"""


def _call_ollama_vision(model: str, prompt: str, image_b64: str, timeout: float = 1200.0) -> str:
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": prompt,
            "images": [image_b64],
        }],
        "stream": False,
        "options": {"num_ctx": 8192},
    }
    
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        if resp.status_code != 200:
            logger.error(f"Ollama API Error ({resp.status_code}): {resp.text}")
        resp.raise_for_status()
    
    data = resp.json()
    content = data.get("message", {}).get("content", "")
    return content


def analyze_page_image(
    image_path: str | Path,
    model: str = "qwen3.5",
    prompt: str | None = None,
) -> str:
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    
    prompt_text = prompt or VISION_PROMPT
    
    logger.info(f"Analyzing page image: {image_path.name} with {model}")
    
    image_bytes = image_path.read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    
    try:
        result = _call_ollama_vision(model, prompt_text, image_b64)
        logger.debug(f"VLM response length: {len(result)} chars")
        return result
        
    except Exception as e:
        logger.error(f"VLM analysis failed for {image_path.name}: {e}")
        raise


def should_skip_vlm(text_density: float, threshold: float = 0.85) -> bool:
    skip = text_density >= threshold
    logger.info(f"VLM skip check: density={text_density:.3f}, threshold={threshold}, skip={skip}")
    return skip


def analyze_scanned_pages(
    image_paths: list[str | Path],
    model: str = "qwen3.5",
    text_densities: dict[int, float] | None = None,
) -> dict[int, str]:
    import concurrent.futures

    results = {}
    text_densities = text_densities or {}
    
    def _process_page(idx: int, path: Path) -> tuple[int, str | None]:
        try:
            page_num = int(path.stem.split("_")[1])
        except (IndexError, ValueError):
            page_num = idx + 1
            
        density = text_densities.get(page_num, 0.0)
        if should_skip_vlm(density):
            logger.info(f"Skipping VLM for page {page_num} due to high text density.")
            return page_num, None
            
        logger.info(f"Processing page {page_num}...")
        res = analyze_page_image(path, model=model)
        return page_num, res

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        futures = [executor.submit(_process_page, i, Path(p)) for i, p in enumerate(image_paths)]
        for future in concurrent.futures.as_completed(futures):
            try:
                page_num, res = future.result()
                if res is not None:
                    results[page_num] = res
            except Exception as exc:
                logger.error(f"A page generated an exception: {exc}")

    return results
def analyze_scanned_pages(scanned_images: list[str], model: str = "qwen2.5vl:7b", text_densities: dict | None = None) -> dict[int, str]:
    results = {}
    for img in scanned_images:
        p_num = int(Path(img).stem.split('_')[-1])
        results[p_num] = analyze_page_image(img, model=model)
    return results
