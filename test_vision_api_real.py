import base64
import httpx
from pathlib import Path

img_path = Path("samples/.renders/page_1.png")
if not img_path.exists():
    print(f"File not found: {img_path}")
    exit(1)

image_b64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")
print(f"Image base64 length: {len(image_b64)}")

payload = {
    "model": "qwen2.5vl:7b",
    "messages": [{
        "role": "user",
        "content": "Analyze this document page image carefully.",
        "images": [image_b64],
    }],
    "stream": False
}

try:
    with httpx.Client(timeout=120.0) as client:
        resp = client.post("http://localhost:11434/api/chat", json=payload)
        print(f"Status Code: {resp.status_code}")
        print(f"Response text: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
