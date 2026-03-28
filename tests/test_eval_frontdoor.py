from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "eval_frontdoor.py"
SPEC = importlib.util.spec_from_file_location("eval_frontdoor", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_load_prompts_reads_expectations(tmp_path: Path) -> None:
    prompt_file = tmp_path / "frontdoor.jsonl"
    prompt_file.write_text(
        (
            '{"id":"case1","category":"reference_risk","prompt":"hello","max_tokens":64,'
            '"expect":{"forbidden_lane_paths":["vision_frontdoor_direct"],'
            '"must_not_contain_regex":["(?i)\\\\bprodigy\\\\b"]}}\n'
        ),
        encoding="utf-8",
    )

    prompts = MODULE.load_prompts(str(prompt_file), limit=0)

    assert len(prompts) == 1
    assert prompts[0]["id"] == "case1"
    assert prompts[0]["expect"]["forbidden_lane_paths"] == ["vision_frontdoor_direct"]


def test_evaluate_expectations_fails_for_forbidden_lane_and_text() -> None:
    prompt = {
        "id": "lyric_guard",
        "expect": {
            "forbidden_lane_paths": ["vision_frontdoor_direct"],
            "must_not_contain_regex": ["(?i)\\bprodigy\\b"],
        },
    }

    result = MODULE.evaluate_expectations(
        prompt,
        http_status=200,
        content="This sounds like The Prodigy.",
        lane="vision",
        lane_path="vision_frontdoor_direct",
        finish_reason="stop",
        error="",
    )

    assert result["passed"] is False
    failed = [check["name"] for check in result["checks"] if not check["passed"]]
    assert "forbidden_lane_paths" in failed
    assert "must_not_contain_regex_1" in failed


def test_evaluate_expectations_passes_for_safe_direct_case() -> None:
    prompt = {
        "id": "fast_ok",
        "expect": {
            "allowed_lane_paths": ["vision_frontdoor_direct"],
            "must_contain_regex": ["(?i)^ok$"],
            "max_content_chars": 8,
        },
    }

    result = MODULE.evaluate_expectations(
        prompt,
        http_status=200,
        content="ok",
        lane="vision",
        lane_path="vision_frontdoor_direct",
        finish_reason="stop",
        error="",
    )

    assert result["passed"] is True
