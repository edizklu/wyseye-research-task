import time
import urllib.request
import json
import sys

def benchmark_ollama(model_name: str, prompt: str):
    url = "http://127.0.0.1:11434/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.0
        }
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    
    print(f"[{model_name}] Test başlatılıyor...")
    start_time = time.time()
    
    try:
        with urllib.request.urlopen(req) as response:
            first_token_time = None
            full_response = ""
            token_count = 0
            
            for line in response:
                if line:
                    data = json.loads(line.decode('utf-8'))
                    if first_token_time is None and not data.get("done", False):
                        first_token_time = time.time()
                        ttft = first_token_time - start_time
                        print(f"İlk Token Gecikmesi (TTFT): {ttft:.2f} saniye")
                    
                    if "response" in data:
                        full_response += data["response"]
                        token_count += 1
                        
                    if data.get("done", False):
                        eval_count = data.get("eval_count", token_count)
                        eval_duration = data.get("eval_duration", 0) / 1e9
                        prompt_eval_duration = data.get("prompt_eval_duration", 0) / 1e9
                        
                        if eval_duration > 0:
                            speed = eval_count / eval_duration
                            print(f"Üretim Hızı: {speed:.2f} tok/s")
                        if prompt_eval_duration > 0:
                            print(f"Prompt İşleme Süresi (Ollama API): {prompt_eval_duration:.2f} saniye")
                        
                        total_time = time.time() - start_time
                        print(f"Toplam Süre: {total_time:.2f} saniye")
                        break
                        
    except Exception as e:
        print(f"Hata oluştu: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanım: python test_latency.py <model_adi>")
        sys.exit(1)
        
    model = sys.argv[1]
    test_prompt = "Lütfen aşağıdaki faturayı analiz et. Bu uzun bir test metnidir. " * 50
    benchmark_ollama(model, test_prompt)
