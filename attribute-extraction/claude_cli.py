"""Use the Claude Code CLI (`claude -p`) as the LLM backend.

This routes extraction through the local `claude` binary, which authenticates with
the user's Claude subscription — so it doesn't consume Anthropic API credits.
Slower than the API (each call spawns a CLI session) and there's no native
structured-output mode, so we instruct the model to emit a JSON array and parse
it robustly.

Used by extract.py when backend="claude_cli".
"""

import json
import re
import subprocess
import time

JSON_INSTRUCTION = (
    "\n\nReturn ONLY a JSON array (no prose, no markdown fences) where each element "
    'is an object with exactly these keys: "politician" (the person\'s name ONLY — '
    "no party, title, role, or honorific; e.g. \"Christopher Luxon\", not "
    '"Rt Hon Christopher Luxon (Prime Minister)"), "statement" (string, quoted '
    'verbatim), "score" (number 0.0-1.0), "explanation" (string). Only include '
    "statements by an individual New Zealand politician — skip organisations, "
    "governments, and non-NZ figures. If nothing relevant is present, return []."
)


def call(system: str, user: str, model: str = None, timeout: int = 180,
         retries: int = 3, instruction: str = JSON_INSTRUCTION) -> str:
    """Run one `claude -p` call and return the model's text output.

    The prompt is passed as a process argument (subprocess list form, so no shell
    quoting issues); stdin is closed to skip the CLI's stdin wait.

    CLI calls fail transiently (rate limits, dropped connections, the occasional
    non-zero exit), so we retry a few times with exponential backoff before
    giving up — one blip shouldn't abort a long batch/eval run.
    """
    prompt = f"{system}{instruction}\n\n=== TEXT TO ANALYSE ===\n{user}"
    cmd = ["claude", "-p", prompt, "--output-format", "text"]
    if model:
        cmd += ["--model", model]
    last_err = ""
    for attempt in range(retries):
        try:
            proc = subprocess.run(
                cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            last_err = f"timeout after {timeout}s"
            proc = None
        if proc is not None and proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
        if proc is not None:
            last_err = (proc.stderr or proc.stdout or "").strip()[:300] or f"exit {proc.returncode}"
        if attempt < retries - 1:
            time.sleep(2 ** attempt)   # 1s, 2s, 4s …
    raise RuntimeError(f"claude CLI failed after {retries} attempts: {last_err}")


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def parse_json_array(text: str) -> list:
    """Extract a JSON array from CLI output, tolerating ``` fences / stray prose."""
    if not text:
        return []
    m = _FENCE.search(text)
    candidate = m.group(1) if m else text
    # fall back to the outermost [...] if there's leading/trailing prose
    if not candidate.lstrip().startswith("["):
        s, e = candidate.find("["), candidate.rfind("]")
        if s != -1 and e != -1 and e > s:
            candidate = candidate[s:e + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []
