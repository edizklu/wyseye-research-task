import base64
import httpx

tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

payload = {
    "model": "qwen2.5vl:7b",
    "messages": [{
        "role": "user",
        "content": "Describe this image",
        "images": [tiny_png_b64],
    }],
    "stream": False
}

try:
    with httpx.Client(timeout=120.0) as client:
        resp = client.post("http://localhost:11434/api/chat", json=payload)
        print(f"Status Code: {resp.status_code}")
        print(f"Response: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
