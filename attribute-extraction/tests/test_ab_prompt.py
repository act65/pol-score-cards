"""The A/B harness must actually be able to call the extractor.

On 2026-08-25 `ab_prompt.py` called `extract.extract_all_attributes` with a
`prompts_dir` kwarg it does not take. Every call raised TypeError, a broad
`except Exception` logged and continued, the stage never reported EX_DONE, and
it held the front of the nightly rotation for two whole nights — 8 hours of the
scheduled window, no windows extracted, and the quota untouched but unusable.

The bug was invisible to the tests I had because I only exercised the window
SELECTION (_pick/_window_text), never the call. These tests intercept at the
subprocess boundary, so they exercise the real argument-passing, the real
envelope parse and the real quote gate without spending anything.
"""

import json
import os
import sys

import pytest

import ab_prompt
import attributes
import claude_cli
import extract

CONTENT = "Hon X: The member is wrong about the numbers."
QUOTE = "The member is wrong about the numbers."


class _FakeProc:
    returncode = 0
    stderr = ""

    def __init__(self, payload):
        self.stdout = payload


@pytest.fixture
def captured(monkeypatch):
    """Capture the argv the CLI would be run with; return a canned envelope."""
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return _FakeProc(json.dumps({
            "usage": {"input_tokens": 2, "cache_read_input_tokens": 20611,
                      "cache_creation_input_tokens": 26512, "output_tokens": 9000},
            "duration_ms": 128000,
            "structured_output": {"examples": [{
                "politician": "Christopher Luxon", "statement": QUOTE,
                "subject": "speaker", "subject_name": None,
                "scores": [{"attribute": "civility", "score": 0.8,
                            "explanation": "Disputes a claim, not the person."}],
            }]},
        }))

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    return seen


def _call(monkeypatch, flag):
    monkeypatch.setenv("CLAUDE_CLI_SYSTEM_FLAG", flag)
    prompts = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "prompts")
    system = extract.build_combined_system(
        list(attributes.EXTRACTED_IN_WINDOWS), prompts)
    return extract.extract_all_attributes(
        None, system, {"date": "2023-12-05", "content": CONTENT},
        set(attributes.EXTRACTED_IN_WINDOWS), model="claude-opus-5",
        backend="claude_cli", timeout=900)


@pytest.mark.parametrize("flag", ["0", "1"])
def test_both_arms_reach_the_extractor(captured, monkeypatch, flag):
    """Whichever arm, the call must succeed and yield a parsed example.

    This is the test that would have caught the prompts_dir TypeError.
    """
    got = _call(monkeypatch, flag)
    assert sum(len(v) for v in got.values()) == 1
    assert got["civility"][0].statement == QUOTE


def test_arm_b_uses_the_system_prompt_flag(captured, monkeypatch):
    """B must pass --system-prompt and NOT carry the rubric in the user message.

    Arm B's whole point is replacing the CLI's 20,611-token default prompt with
    our rubric. If the rubric ended up in both places the arms would differ only
    in cost, and the comparison would be meaningless.
    """
    _call(monkeypatch, "1")
    cmd = captured[0]
    assert "--system-prompt" in cmd
    user_prompt = cmd[cmd.index("-p") + 1]
    system_prompt = cmd[cmd.index("--system-prompt") + 1]
    assert "### Attribute:" in system_prompt
    assert "### Attribute:" not in user_prompt
    assert CONTENT in user_prompt


def test_arm_a_is_unchanged(captured, monkeypatch):
    """A must be byte-identical to how the 618 scored windows were produced."""
    _call(monkeypatch, "0")
    cmd = captured[0]
    assert "--system-prompt" not in cmd
    user_prompt = cmd[cmd.index("-p") + 1]
    assert "### Attribute:" in user_prompt and CONTENT in user_prompt


def test_signature_mismatch_is_not_swallowed(monkeypatch, tmp_path):
    """A TypeError must crash the stage, not be logged and retried all night."""
    def boom(*a, **kw):
        raise TypeError("unexpected keyword argument 'prompts_dir'")

    monkeypatch.setattr(ab_prompt.extract, "extract_all_attributes", boom)
    monkeypatch.setattr(ab_prompt, "_pick", lambda n, seed_skip=0: ["2023-12-05#0"])
    monkeypatch.setattr(ab_prompt, "_window_text", lambda wid, wt=3000: CONTENT)
    monkeypatch.setattr(ab_prompt, "A_OUT", str(tmp_path / "a.jsonl"))
    monkeypatch.setattr(ab_prompt, "B_OUT", str(tmp_path / "b.jsonl"))
    # HERE is deliberately NOT patched — os.path.join with an absolute A_OUT
    # ignores it, and patching it would break prompt loading.
    with pytest.raises(TypeError):
        ab_prompt.run(n=1)
