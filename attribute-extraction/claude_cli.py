"""Use the Claude Code CLI (`claude -p`) as the LLM backend.

This routes extraction through the local `claude` binary, which authenticates with
the user's Claude subscription — so it doesn't consume Anthropic API credits.
Slower than the API (each call spawns a CLI session) and there's no native
structured-output mode, so we instruct the model to emit a JSON array and parse
it robustly.

Used by extract.py when backend="claude_cli".
"""

import datetime as dt
import json
import os
import re
import subprocess
import threading
import time

# --- usage accounting -------------------------------------------------------
# Every `claude -p --output-format json` envelope carries a `usage` block with
# input_tokens / cache_read_input_tokens / cache_creation_input_tokens / output.
# We used to discard it, and then spend days inferring the subscription's
# metering from when overnight runs hit the cap. Two nights at different window
# sizes capped within 9% of the same total-input figure computed at FULL rate
# for the 7,469-token system prompt, and 2.2x apart computed at the 10% cache
# rate — strong evidence the repeated prefix is NOT being cached. That matters
# enormously: at window_tokens=3000 the full term sends 41.4M tokens of rubric
# against 13.9M of actual debate.
#
# So record it. Set CLAUDE_CLI_USAGE_LOG to a path and every call appends one
# line. Costs nothing — the numbers are already in the response we parse.
_USAGE_LOCK = threading.Lock()


def _record_usage(env: dict, label: str = "") -> None:
    path = os.environ.get("CLAUDE_CLI_USAGE_LOG", "")
    if not path:
        return
    u = env.get("usage") or {}
    row = {
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "input": u.get("input_tokens"),
        "cache_read": u.get("cache_read_input_tokens"),
        "cache_creation": u.get("cache_creation_input_tokens"),
        "output": u.get("output_tokens"),
        "duration_ms": env.get("duration_ms"),
        "duration_api_ms": env.get("duration_api_ms"),
        "cost_usd": env.get("total_cost_usd"),
    }
    try:
        with _USAGE_LOCK, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass          # accounting must never break an extraction run

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
    # `range(retries)` would make retries=0 mean ZERO attempts — the call fails
    # instantly with an empty error and looks like a CLI fault. Retries are
    # retries; one attempt always happens. (`call_structured` already did this
    # correctly with `range(retries + 1)`.)
    for attempt in range(max(1, retries)):
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
            last_err = (proc.stderr or proc.stdout or "").strip()[:1200] or f"exit {proc.returncode}"
        if attempt < retries - 1:
            time.sleep(2 ** attempt)   # 1s, 2s, 4s …
    raise RuntimeError(f"claude CLI failed after {retries} attempts: {last_err}")


class QuotaExhausted(RuntimeError):
    """The subscription's usage window is spent — retrying cannot help.

    Distinguished from an ordinary transient failure because the response is
    the opposite of transient: no request reached the API at all. The envelope
    comes back `is_error` with `duration_api_ms: 0` and every token count zero,
    which no real API error produces.

    This matters because the two are indistinguishable to a retry loop. On the
    night of 2026-08-13 the Forthrightness pass consumed the window at 03:12 and
    the positions pass that followed spent its whole 2.8h budget re-attempting
    260 windows three times each — 780 calls, none of which could ever have
    succeeded — while reporting "no progress, backing off".
    """


def _is_quota_error(envelope: dict) -> bool:
    """True for the never-reached-the-API signature described above."""
    if not envelope.get("is_error"):
        return False
    usage = envelope.get("usage") or {}
    spent = sum(v for k, v in usage.items()
                if k.endswith("tokens") and isinstance(v, int))
    return envelope.get("duration_api_ms") == 0 and spent == 0


def call_structured(system: str, user: str, schema: dict, model: str = None,
                    instruction: str = "", timeout: int = 300, retries: int = 2,
                    label: str = "", system_prompt_flag: bool = None,
                    effort: str = None):
    """Run `claude -p --json-schema <schema> --output-format json` and return the
    validated ``structured_output`` object.

    This is the subscription-path equivalent of the API's structured outputs
    (``messages.parse``): the CLI enforces the JSON Schema on the model's answer
    (via a forced tool call) and returns the parsed object in the result envelope,
    so we don't fall back to brittle text parsing. Closes the quality gap that the
    loose-JSON CLI path otherwise has vs the API.
    """
    # Both default off, and both switchable by environment so an A/B can flip
    # them for one run without editing call sites.
    if system_prompt_flag is None:
        system_prompt_flag = os.environ.get("CLAUDE_CLI_SYSTEM_FLAG", "") == "1"
    effort = effort or os.environ.get("CLAUDE_CLI_EFFORT", "") or None

    if system_prompt_flag:
        # Send the rubric as the SESSION SYSTEM PROMPT rather than as the head
        # of the user message. Two things change, both measured in usage_v3.jsonl
        # over the 294 calls of 2026-08-19..24:
        #
        #   * --system-prompt REPLACES the CLI's own default system prompt,
        #     which is 20,611 tokens and cache-read on every single call. We use
        #     none of it: extraction needs no tools, no file access and no
        #     Claude Code behaviour, only the model and a JSON schema.
        #   * a system prompt is a stable cacheable prefix. Prepended to the user
        #     message the rubric was NOT being reused — cache_read sat at exactly
        #     20,611 (the CLI default alone) while cache_creation ran at 26,512
        #     per call, i.e. we paid to write a cache entry that nothing ever
        #     read back, because the unique window text shared its cached span.
        #
        # The risk is that this is a different instrument: same rubric, different
        # surrounding prompt. Gate it on ab_prompt.py before trusting it.
        prompt = f"{instruction}\n\n=== TEXT TO ANALYSE ===\n{user}".lstrip()
        cmd = ["claude", "-p", prompt, "--system-prompt", system,
               "--json-schema", json.dumps(schema), "--output-format", "json"]
    else:
        prompt = f"{system}{instruction}\n\n=== TEXT TO ANALYSE ===\n{user}"
        cmd = ["claude", "-p", prompt, "--json-schema", json.dumps(schema),
               "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["--effort", effort]
    last_err = ""
    for attempt in range(retries + 1):
        proc = None
        try:
            proc = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            last_err = f"timeout after {timeout}s"
        if proc is not None and proc.returncode == 0 and proc.stdout.strip():
            try:
                env = json.loads(proc.stdout)
            except json.JSONDecodeError:
                env, last_err = None, "result envelope was not JSON"
            if env is not None:
                _record_usage(env, label)
                if _is_quota_error(env):
                    raise QuotaExhausted(
                        "no request reached the API (zero tokens, zero API "
                        "time) — the subscription usage window is spent. "
                        "Retrying cannot help; resume after it resets.")
                if env.get("is_error"):
                    last_err = str(env.get("result", "cli error"))[:300]
                elif env.get("structured_output") is not None:
                    return env["structured_output"]
                else:
                    last_err = "no structured_output in envelope"
        elif proc is not None:
            raw = (proc.stderr or proc.stdout or "").strip()
            try:
                if _is_quota_error(json.loads(raw)):
                    raise QuotaExhausted(
                        "no request reached the API (zero tokens, zero API "
                        "time) — the subscription usage window is spent. "
                        "Retrying cannot help; resume after it resets.")
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass
            last_err = raw[:1200] or f"exit {proc.returncode}"
        if attempt < retries:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"claude --json-schema failed after {retries + 1} attempts: {last_err}")


def call_structured_searching(system: str, user: str, schema: dict, label: str = "",
                              model: str = None, instruction: str = "",
                              timeout: int = 600, retries: int = 2):
    """Like ``call_structured``, but with web search and fetch enabled.

    Used by the resolver, which has to look evidence up rather than recall it.
    Tools are off by default in ``claude -p``, so they are requested explicitly;
    the timeout is much longer because each call does several round-trips to the
    open web before it answers.
    """
    prompt = f"{system}{instruction}\n\n=== ITEMS TO RESOLVE ===\n{user}"
    cmd = ["claude", "-p", prompt,
           "--allowedTools", "WebSearch", "WebFetch",
           "--json-schema", json.dumps(schema), "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    last_err = ""
    for attempt in range(retries + 1):
        proc = None
        try:
            proc = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            last_err = f"timeout after {timeout}s"
        if proc is not None and proc.returncode == 0 and proc.stdout.strip():
            try:
                env = json.loads(proc.stdout)
            except json.JSONDecodeError:
                env, last_err = None, "result envelope was not JSON"
            if env is not None:
                _record_usage(env, label)
                if _is_quota_error(env):
                    raise QuotaExhausted(
                        "no request reached the API (zero tokens, zero API "
                        "time) — the subscription usage window is spent. "
                        "Retrying cannot help; resume after it resets.")
                if env.get("is_error"):
                    last_err = str(env.get("result", "cli error"))[:300]
                elif env.get("structured_output") is not None:
                    return env["structured_output"]
                else:
                    last_err = "no structured_output in envelope"
        elif proc is not None:
            last_err = (proc.stderr or proc.stdout or "").strip()[:300] or \
                f"exit {proc.returncode}"
        if attempt < retries:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"searching claude call failed after {retries + 1} "
                       f"attempts: {last_err}")


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def _extract_array(text: str):
    """Return the parsed JSON array, or None if the text doesn't contain a
    parseable array. None means PARSE FAILURE (distinct from a valid empty [])."""
    if not text:
        return None
    m = _FENCE.search(text)
    candidate = m.group(1) if m else text
    if not candidate.lstrip().startswith("["):
        s, e = candidate.find("["), candidate.rfind("]")
        if s != -1 and e != -1 and e > s:
            candidate = candidate[s:e + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def parse_json_array(text: str) -> list:
    """Extract a JSON array from CLI output, tolerating ``` fences / stray prose.
    Returns [] on failure (lossy — prefer call_json_array, which retries)."""
    data = _extract_array(text)
    return data if data is not None else []


# Without the API's structured outputs (messages.parse), the CLI returns free
# text we parse best-effort — an occasional malformed reply would otherwise drop a
# whole window's results silently. This re-asks the model (feeding back the
# failure) until the output parses to a JSON array, recovering most of the
# reliability the API gives for free.
_REPAIR = ("\n\nYour previous reply did not parse as the required JSON array. "
           "Return ONLY a valid JSON array (no prose, no markdown fences), "
           "matching the schema exactly. If nothing relevant is present, return [].")


def call_json_array(system: str, user: str, model: str = None,
                    instruction: str = JSON_INSTRUCTION, retries: int = 3,
                    timeout: int = 180) -> list:
    """Call the CLI and return a parsed JSON array, retrying on parse failure.

    A valid empty array (model genuinely found nothing) is accepted immediately;
    only unparseable output triggers a retry with corrective feedback.
    """
    instr = instruction
    for attempt in range(retries):
        text = call(system, user, model=model, instruction=instr, timeout=timeout,
                    retries=2)
        rows = _extract_array(text)
        if rows is not None:
            return rows
        instr = instruction + _REPAIR  # feed the failure back on the next try
    return []
