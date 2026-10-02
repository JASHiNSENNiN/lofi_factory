"""Guard: the pipeline is pure algorithm. No LLM, text/image/music
generator, or AI service may be imported, called or declared anywhere."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_FORBIDDEN = re.compile(
    r"\b(groq|genai|google\.generativeai|google-generativeai|openai|anthropic|"
    r"ollama|pollinations|musicgen|audiocraft|transformers|diffusers|torch|"
    r"replicate|huggingface|LOFI_LLM_FAILSAFE|GROQ_API_KEY|GEMINI_API_KEY)\b",
    re.IGNORECASE,
)

_SCANNED_DIRS = ("scripts", "webui", "deploy", "config")
_SCANNED_ROOT_FILES = (
    "run.py", "publish.py", "auto_service.py", "dashboard.py", "webui.py",
    "requirements.txt", "requirements-dev.txt", ".env.example",
)
_EXTS = (".py", ".txt", ".yaml", ".yml", ".sh", ".service", ".timer", ".example")


def _files():
    for name in _SCANNED_ROOT_FILES:
        path = os.path.join(ROOT, name)
        if os.path.exists(path):
            yield path
    for d in _SCANNED_DIRS:
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, d)):
            if "__pycache__" in dirpath:
                continue
            for f in files:
                if f.endswith(_EXTS):
                    yield os.path.join(dirpath, f)


def test_no_ai_references_anywhere():
    hits = []
    for path in _files():
        with open(path, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                if _FORBIDDEN.search(line):
                    hits.append(f"{os.path.relpath(path, ROOT)}:{n}: {line.strip()[:100]}")
    assert not hits, "AI/LLM references found:\n" + "\n".join(hits)
