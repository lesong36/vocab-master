#!/usr/bin/env python3
"""VocabMaster 本地服务：提供静态页面，并将学习记录持久化到 vocab_data.json。"""

from __future__ import annotations

import json
import os
import hashlib
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "vocab_data.json"
AI_CONFIG_FILE = ROOT / "ai_config.json"
AUDIO_CACHE_DIR = ROOT / ".audio_cache"
DEFAULT_PORT = 8080
DEFAULT_AI_BASE = "https://api.aicodewith.com/v1"
DEFAULT_AI_MODEL = "gpt-4o-mini"


def _mask_api_key(api_key: str) -> str:
    key = (api_key or "").strip()
    if not key:
        return "(empty)"
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def load_ai_config() -> dict:
    if AI_CONFIG_FILE.exists():
        try:
            data = json.loads(AI_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"[vocab_server] AI 配置读取失败: {exc}\n")
    return {
        "baseUrl": os.environ.get("AI_BASE_URL", DEFAULT_AI_BASE),
        "apiKey": os.environ.get("AICODEWITH_API_KEY")
        or os.environ.get("OPENAI_API_KEY", ""),
        "model": os.environ.get("AI_MODEL", DEFAULT_AI_MODEL),
    }


def ai_is_configured() -> bool:
    cfg = load_ai_config()
    return bool((cfg.get("apiKey") or "").strip())


def describe_ai_config(cfg: dict | None = None) -> dict:
    cfg = cfg or load_ai_config()
    base_url = (cfg.get("baseUrl") or DEFAULT_AI_BASE).rstrip("/")
    model = cfg.get("model") or DEFAULT_AI_MODEL
    api_key = (cfg.get("apiKey") or "").strip()
    source = "ai_config.json" if AI_CONFIG_FILE.exists() else "env/default"
    return {
        "configured": bool(api_key),
        "configFile": AI_CONFIG_FILE.name,
        "configSource": source,
        "baseUrl": base_url,
        "model": model,
        "apiKeyMasked": _mask_api_key(api_key),
    }


def log_ai(message: str) -> None:
    sys.stderr.write(f"[vocab_server][ai] {message}\n")
    sys.stderr.flush()


def call_chat_completion(prompt: str) -> tuple[str | None, str | None]:
    cfg = load_ai_config()
    info = describe_ai_config(cfg)
    api_key = (cfg.get("apiKey") or "").strip()
    if not api_key:
        log_ai("调用失败: no_api_key")
        return None, "no_api_key"

    base_url = info["baseUrl"]
    model = info["model"]
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
        "temperature": 0.85,
        # DeepSeek V4 默认开启 thinking；助记场景关闭以降低延迟
        "thinking": {"type": "disabled"},
    }

    log_ai(
        f"请求开始 model={model} baseUrl={base_url} "
        f"key={info['apiKeyMasked']} prompt_chars={len(prompt)}"
    )

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        err = f"http_{exc.code}: {detail}"
        log_ai(f"调用失败 model={model} error={err}")
        return None, err
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        log_ai(f"调用失败 model={model} error={err}")
        return None, err

    text = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if not text:
        log_ai(f"调用失败 model={model} error=empty_response")
        return None, "empty_response"

    usage = data.get("usage") or {}
    log_ai(
        f"调用成功 model={model} chars={len(text)} "
        f"tokens={usage.get('total_tokens', '?')}"
    )
    return text, None


class VocabHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        if self.path.startswith("/api/pronunciation"):
            query = urllib.parse.urlparse(self.path).query
            word = urllib.parse.parse_qs(query).get("word", [""])[0].strip()
            if not word or len(word) > 100:
                self._json_response(400, {"error": "valid word required"})
                return

            cache_key = hashlib.sha256(word.lower().encode("utf-8")).hexdigest()
            wav_file = AUDIO_CACHE_DIR / f"{cache_key}.wav"
            if not wav_file.exists():
                try:
                    AUDIO_CACHE_DIR.mkdir(exist_ok=True)
                    aiff_file = AUDIO_CACHE_DIR / f"{cache_key}.aiff"
                    subprocess.run(
                        ["/usr/bin/say", "-v", "Samantha", "-o", str(aiff_file), word],
                        check=True,
                        capture_output=True,
                        timeout=15,
                    )
                    subprocess.run(
                        [
                            "/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@44100",
                            str(aiff_file), str(wav_file),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=15,
                    )
                    aiff_file.unlink(missing_ok=True)
                except (OSError, subprocess.SubprocessError) as exc:
                    self._json_response(500, {"error": f"pronunciation generation failed: {exc}"})
                    return

            try:
                body = wav_file.read_bytes()
            except OSError as exc:
                self._json_response(500, {"error": str(exc)})
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/health":
            ai_info = describe_ai_config()
            self._json_response(
                200,
                {
                    "ok": True,
                    "dataFile": DATA_FILE.name,
                    "dataFileExists": DATA_FILE.exists(),
                    "aiConfigured": ai_info["configured"],
                    "aiConfigFile": ai_info["configFile"],
                    "aiModel": ai_info["model"],
                    "aiBaseUrl": ai_info["baseUrl"],
                },
            )
            return

        if self.path == "/api/ai-status":
            self._json_response(200, describe_ai_config())
            return

        if self.path == "/api/vocab-data":
            if not DATA_FILE.exists():
                self._json_response(404, {"error": "not_found"})
                return
            try:
                data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self._json_response(500, {"error": str(exc)})
                return
            self._json_response(200, data)
            return

        super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/ai-hint":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json_response(400, {"error": f"invalid json: {exc}"})
                return

            prompt = (payload.get("prompt") or "").strip()
            if not prompt:
                self._json_response(400, {"error": "prompt required"})
                return

            text, err = call_chat_completion(prompt)
            ai_info = describe_ai_config()
            if text:
                self._json_response(
                    200,
                    {
                        "ok": True,
                        "text": text,
                        "source": "ai",
                        "model": ai_info["model"],
                    },
                )
                return
            self._json_response(
                503,
                {
                    "ok": False,
                    "error": err or "ai_unavailable",
                    "source": "none",
                    "model": ai_info["model"],
                },
            )
            return

        if self.path != "/api/vocab-data":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._json_response(400, {"error": f"invalid json: {exc}"})
            return

        if not isinstance(payload, dict) or "users" not in payload:
            self._json_response(400, {"error": "payload must contain users"})
            return

        try:
            DATA_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            self._json_response(500, {"error": str(exc)})
            return

        self._json_response(200, {"ok": True, "savedAt": payload.get("savedAt")})

    def log_message(self, format: str, *args) -> None:
        if self.path.startswith("/api/"):
            sys.stderr.write(f"[vocab_server] {self.command} {self.path}\n")
        elif not self.path.endswith((".js", ".css", ".map", ".ico")):
            sys.stderr.write(f"[vocab_server] {self.command} {self.path}\n")

    def _json_response(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    ai_info = describe_ai_config()
    server = ThreadingHTTPServer(("127.0.0.1", port), VocabHandler)
    print(f"VocabMaster 本地服务已启动", flush=True)
    print(f"  页面: http://127.0.0.1:{port}/vocabulary_app.html", flush=True)
    print(f"  数据: {DATA_FILE}", flush=True)
    print(
        f"  AI: {'已配置' if ai_info['configured'] else '未配置'} "
        f"| source={ai_info['configSource']} "
        f"| model={ai_info['model']} "
        f"| baseUrl={ai_info['baseUrl']} "
        f"| key={ai_info['apiKeyMasked']}",
        flush=True,
    )
    log_ai(
        f"配置已加载 configured={ai_info['configured']} "
        f"source={ai_info['configSource']} model={ai_info['model']} "
        f"baseUrl={ai_info['baseUrl']} key={ai_info['apiKeyMasked']}"
    )
    print("按 Ctrl+C 停止", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.server_close()


if __name__ == "__main__":
    main()
