"""The RuntimeBrief Siri demo stays an iPhone clip with the shortcut's words."""
import ast
from pathlib import Path

ROOT = Path(__file__).parents[1] / "docs" / "media" / "runtimebrief-siri"


def spoken_lines():
    module = ast.parse((ROOT / "render.py").read_text())
    beats = next(
        node.value for node in module.body
        if isinstance(node, ast.Assign) and any(getattr(target, "id", None) == "BEATS" for target in node.targets)
    )
    lines = []
    for seconds, payload in ast.literal_eval(beats):
        assert seconds > 0
        if payload is not None:
            text, _question = payload
            lines.append(text)
    return lines


def test_siri_replies_omit_the_fictional_demo_prefix():
    replies = spoken_lines()
    assert replies
    for line in replies:
        assert "Fictional demo." not in line


def test_demo_files_are_present():
    video = ROOT / "runtimebrief-siri-demo.mp4"
    assert video.is_file()
    assert video.stat().st_size > 50_000
    assert video.read_bytes()[4:8] == b"ftyp"
    assert (ROOT / "screens" / "app.png").is_file()
    assert (ROOT / "screens" / "siri.png").is_file()
