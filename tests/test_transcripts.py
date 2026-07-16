import json

from bench.mine import transcripts


def write_session(path, first_user_text):
    records = [
        {"type": "system", "message": {"role": "system", "content": "boot"}},
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": first_user_text}],
            },
        },
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def test_classify():
    assert transcripts.classify("fix the login bug causing a crash") == "bugfix"
    assert transcripts.classify("refactor the user service and rename methods") == "refactor"
    assert transcripts.classify("zzz qqq") == "other"


def test_survey(tmp_path):
    proj = tmp_path / "projects" / "myrepo"
    proj.mkdir(parents=True)
    write_session(proj / "s1.jsonl", "fix the crash when parsing dates")
    write_session(proj / "s2.jsonl", "add support for CSV export")
    write_session(proj / "s3.jsonl", "explain how the auth middleware works")
    (proj / "junk.jsonl").write_text("not json\n{broken\n")

    result = transcripts.survey(tmp_path / "projects")
    assert result.sessions == 3
    assert result.categorized["bugfix"] == 1
    assert result.categorized["feature"] == 1
    assert result.categorized["explain"] == 1
    rendered = result.render()
    assert "3 sessions" in rendered


def test_plain_string_content(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(json.dumps({"role": "user", "content": "fix the bug"}) + "\n")
    assert transcripts.first_user_message(p) == "fix the bug"
