"""Minimal Ollama client shared by the translator and the term extractor."""
import re
import time

import requests

THINK = re.compile(r"<think>.*?</think>", re.S)


class Ollama:
    def __init__(self, url, model, timeout=900):
        self.url, self.model, self.timeout = url.rstrip("/"), model, timeout
        try:
            r = requests.post(f"{self.url}/api/show", json={"model": model}, timeout=30)
        except requests.ConnectionError:
            raise SystemExit(f"Không kết nối được Ollama ở {self.url}. Hãy mở Ollama trước.")
        if r.status_code == 404:
            raise SystemExit(f"Chưa có model '{model}'. Tải bằng:  ollama pull {model}")
        r.raise_for_status()
        self.can_think = "thinking" in r.json().get("capabilities", [])

    def chat(self, system, user, options, fmt=None):
        """Returns (text, generated tokens, generation seconds). fmt: optional JSON schema."""
        body = {
            "model": self.model, "stream": False, "keep_alive": "30m", "options": options,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self.can_think:
            body["think"] = False
        if fmt is not None:
            body["format"] = fmt
        for attempt in range(3):
            try:
                r = requests.post(f"{self.url}/api/chat", json=body, timeout=self.timeout)
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(10)
        d = r.json()
        return THINK.sub("", d["message"]["content"]), d.get("eval_count", 0), d.get("eval_duration", 0) / 1e9
