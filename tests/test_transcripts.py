import json

from bench.cli import main
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


def write_records(path, records, *, malformed_line=False):
    lines = [json.dumps(record) for record in records]
    if malformed_line:
        lines.insert(1, "{truncated")
    path.write_text("\n".join(lines) + "\n")


def codex_message(role, text, *, block_type=None):
    return {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": role,
            "content": [
                {
                    "type": block_type
                    or ("input_text" if role == "user" else "output_text"),
                    "text": text,
                }
            ],
        },
    }


def codex_meta(*, cwd="/code/project", originator="Codex Desktop", session_id="s1"):
    return {
        "type": "session_meta",
        "payload": {
            "id": session_id,
            "cwd": cwd,
            "originator": originator,
            "source": "vscode" if originator == "Codex Desktop" else "exec",
            "timestamp": "2026-07-15T12:00:00Z",
        },
    }


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


def test_parse_codex_session_reads_metadata_and_full_conversation(tmp_path):
    p = tmp_path / "rollout.jsonl"
    write_records(
        p,
        [
            codex_meta(),
            codex_message("developer", "internal instructions", block_type="input_text"),
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "fix the login bug"},
            },
            codex_message("user", "fix the login bug"),
            codex_message("assistant", "Implemented the fix."),
            codex_message("user", "Make the explanation shorter."),
            codex_message("assistant", "Done."),
        ],
        malformed_line=True,
    )

    session = transcripts.parse_session(p)

    assert session.source == "codex"
    assert session.session_id == "s1"
    assert session.cwd == "/code/project"
    assert session.originator == "Codex Desktop"
    assert session.started_at == "2026-07-15T12:00:00Z"
    assert session.mode == "interactive"
    assert session.malformed_lines == 1
    assert session.user_messages == ["fix the login bug", "Make the explanation shorter."]
    assert session.assistant_messages == ["Implemented the fix.", "Done."]
    assert [(message.role, message.text) for message in session.messages] == [
        ("user", "fix the login bug"),
        ("assistant", "Implemented the fix."),
        ("user", "Make the explanation shorter."),
        ("assistant", "Done."),
    ]
    assert transcripts.first_user_message(p) == "fix the login bug"


def test_codex_skips_injected_context_before_real_request(tmp_path):
    p = tmp_path / "rollout.jsonl"
    write_records(
        p,
        [
            codex_meta(),
            codex_message("user", "<recommended_plugins>generated context</recommended_plugins>"),
            codex_message("user", "<environment_context><cwd>/code/project</cwd></environment_context>"),
            codex_message("user", "add support for CSV export"),
        ],
    )

    session = transcripts.parse_session(p)

    assert session.user_messages == ["add support for CSV export"]
    assert transcripts.first_user_message(p) == "add support for CSV export"


def test_codex_extracts_request_from_attachment_and_browser_wrappers(tmp_path):
    p = tmp_path / "rollout.jsonl"
    write_records(
        p,
        [
            codex_meta(),
            codex_message(
                "user",
                "# Files mentioned by the user:\n"
                "## Screenshot.png: /tmp/private/Screenshot.png\n"
                "<in-app-browser-context>ambient state</in-app-browser-context>\n"
                "## My request for Codex:\nFix the mobile layout shown in the screenshot.",
            ),
        ],
    )

    session = transcripts.parse_session(p)

    assert session.user_messages == ["Fix the mobile layout shown in the screenshot."]


def test_codex_keeps_real_text_when_injected_and_user_blocks_share_a_message(tmp_path):
    p = tmp_path / "rollout.jsonl"
    record = codex_message("user", "unused")
    record["payload"]["content"] = [
        {"type": "input_text", "text": "<environment_context>generated</environment_context>"},
        {"type": "input_text", "text": "fix the actual bug"},
    ]
    write_records(p, [codex_meta(), record])

    assert transcripts.parse_session(p).user_messages == ["fix the actual bug"]


def test_codex_does_not_unwrap_literal_request_marker_in_normal_prompt(tmp_path):
    p = tmp_path / "rollout.jsonl"
    prompt = (
        "Update the parser for messages following the "
        "`## My request for Codex:` marker, and keep normal prompt text intact."
    )
    write_records(p, [codex_meta(), codex_message("user", prompt)])

    assert transcripts.first_user_message(p) == prompt


def test_codex_context_only_session_has_no_task_statement(tmp_path):
    p = tmp_path / "rollout.jsonl"
    write_records(
        p,
        [
            codex_meta(),
            codex_message("user", "<environment_context>generated context</environment_context>"),
            codex_message("assistant", "Waiting for a request."),
        ],
    )

    session = transcripts.parse_session(p)

    assert session.user_messages == []
    assert transcripts.first_user_message(p) is None


def test_codex_uses_session_id_fallback_and_ignores_non_text_blocks(tmp_path):
    p = tmp_path / "rollout.jsonl"
    meta = codex_meta()
    meta["payload"].pop("id")
    meta["payload"]["session_id"] = "fallback-id"
    message = codex_message("user", "fix the task")
    message["payload"]["content"].insert(
        0, {"type": "input_image", "image_url": "data:image/png;base64,private"}
    )
    write_records(p, [meta, message])

    session = transcripts.parse_session(p)

    assert session.session_id == "fallback-id"
    assert session.user_messages == ["fix the task"]


def test_codex_messages_retain_timestamps_and_supply_started_at_fallback(tmp_path):
    p = tmp_path / "rollout.jsonl"
    user = codex_message("user", "fix the task")
    user["timestamp"] = "2026-07-15T12:01:00Z"
    assistant = codex_message("assistant", "Done.")
    assistant["timestamp"] = "2026-07-15T12:02:00Z"
    write_records(p, [user, assistant])

    session = transcripts.parse_session(p)

    assert session.started_at == "2026-07-15T12:01:00Z"
    assert [message.timestamp for message in session.messages] == [
        "2026-07-15T12:01:00Z",
        "2026-07-15T12:02:00Z",
    ]


def test_codex_request_marker_at_start_is_unwrapped(tmp_path):
    p = tmp_path / "rollout.jsonl"
    write_records(
        p,
        [
            codex_meta(),
            codex_message("user", "## My request for Codex:\nFix the wrapped task."),
        ],
    )

    assert transcripts.first_user_message(p) == "Fix the wrapped task."


def test_codex_exec_and_benchmark_sessions_are_classified_separately(tmp_path):
    automated = tmp_path / "automated.jsonl"
    benchmark = tmp_path / "benchmark.jsonl"
    write_records(
        automated,
        [codex_meta(originator="codex_exec"), codex_message("user", "generate newsletter")],
    )
    write_records(
        benchmark,
        [
            codex_meta(cwd="/private/tmp/bench-run-abc/repo"),
            codex_message("user", "fix fixture task"),
        ],
    )

    assert transcripts.parse_session(automated).mode == "automation"
    assert transcripts.parse_session(benchmark).mode == "benchmark"


def test_benchmark_mode_takes_precedence_over_automation_originator(tmp_path):
    p = tmp_path / "benchmark.jsonl"
    write_records(
        p,
        [
            codex_meta(cwd="/tmp/bench-run-123/repo", originator="codex_exec"),
            codex_message("user", "run the benchmark fixture"),
        ],
    )

    assert transcripts.parse_session(p).mode == "benchmark"


def test_parse_claude_session_ignores_sidechains_and_tool_results(tmp_path):
    p = tmp_path / "claude.jsonl"
    write_records(
        p,
        [
            {
                "type": "user",
                "sessionId": "claude-1",
                "cwd": "/code/project",
                "entrypoint": "cli",
                "timestamp": "2026-07-15T12:00:00Z",
                "isSidechain": True,
                "message": {"role": "user", "content": "subagent task"},
            },
            {
                "type": "user",
                "sessionId": "claude-1",
                "cwd": "/code/project",
                "entrypoint": "cli",
                "timestamp": "2026-07-15T12:00:01Z",
                "isSidechain": False,
                "message": {
                    "role": "user",
                    "content": [{"type": "tool_result", "content": "not a prompt"}],
                },
            },
            {
                "type": "user",
                "sessionId": "claude-1",
                "cwd": "/code/project",
                "entrypoint": "cli",
                "timestamp": "2026-07-15T12:00:02Z",
                "isSidechain": False,
                "message": {"role": "user", "content": "explain the auth middleware"},
            },
            {
                "type": "assistant",
                "sessionId": "claude-1",
                "cwd": "/code/project",
                "entrypoint": "cli",
                "timestamp": "2026-07-15T12:00:03Z",
                "isSidechain": False,
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "private"},
                        {"type": "text", "text": "Here is how it works."},
                    ],
                },
            },
        ],
    )

    session = transcripts.parse_session(p)

    assert session.source == "claude"
    assert session.mode == "interactive"
    assert session.session_id == "claude-1"
    assert session.user_messages == ["explain the auth middleware"]
    assert session.assistant_messages == ["Here is how it works."]


def test_claude_sdk_session_is_automation(tmp_path):
    p = tmp_path / "claude.jsonl"
    write_records(
        p,
        [
            {
                "type": "user",
                "sessionId": "claude-sdk",
                "cwd": "/code/project",
                "entrypoint": "sdk-cli",
                "message": {"role": "user", "content": "draft the daily newsletter"},
            }
        ],
    )

    assert transcripts.parse_session(p).mode == "automation"


def test_claude_skips_local_command_input_and_output_before_real_request(tmp_path):
    p = tmp_path / "claude.jsonl"
    write_records(
        p,
        [
            {
                "type": "user",
                "sessionId": "claude-cli",
                "cwd": "/code/project",
                "entrypoint": "cli",
                "message": {
                    "role": "user",
                    "content": "<bash-input>gh auth status</bash-input>",
                },
            },
            {
                "type": "user",
                "sessionId": "claude-cli",
                "cwd": "/code/project",
                "entrypoint": "cli",
                "message": {
                    "role": "user",
                    "content": "<local-command-stdout>Goodbye!</local-command-stdout>",
                },
            },
            {
                "type": "user",
                "sessionId": "claude-cli",
                "cwd": "/code/project",
                "entrypoint": "cli",
                "message": {"role": "user", "content": "fix the actual issue"},
            },
        ],
    )

    assert transcripts.parse_session(p).user_messages == ["fix the actual issue"]


def test_claude_cleans_each_text_block_independently(tmp_path):
    p = tmp_path / "claude.jsonl"
    write_records(
        p,
        [
            {
                "type": "user",
                "sessionId": "claude-cli",
                "cwd": "/code/project",
                "entrypoint": "cli",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "<system-reminder>generated</system-reminder>"},
                        {"type": "text", "text": "add the actual feature"},
                        {"type": "tool_result", "content": "ignored"},
                    ],
                },
            }
        ],
    )

    assert transcripts.parse_session(p).user_messages == ["add the actual feature"]


def test_generic_session_retains_user_and_assistant_messages(tmp_path):
    p = tmp_path / "generic.jsonl"
    write_records(
        p,
        [
            {"role": "user", "content": [{"type": "input_text", "text": "explain this"}]},
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Here is the explanation."}],
            },
        ],
    )

    session = transcripts.parse_session(p)

    assert session.source == "generic"
    assert session.mode == "unknown"
    assert session.user_messages == ["explain this"]
    assert session.assistant_messages == ["Here is the explanation."]


def test_missing_file_and_non_object_json_are_safe(tmp_path):
    missing = transcripts.parse_session(tmp_path / "missing.jsonl")
    assert missing.user_messages == []
    assert missing.malformed_lines == 0

    p = tmp_path / "odd.jsonl"
    p.write_text("[]\nnull\n42\n")
    odd = transcripts.parse_session(p)
    assert odd.user_messages == []
    assert odd.malformed_lines == 0


def test_survey_can_filter_by_source_and_mode(tmp_path):
    write_records(
        tmp_path / "codex-interactive.jsonl",
        [codex_meta(session_id="interactive"), codex_message("user", "fix the crash")],
    )
    write_records(
        tmp_path / "codex-automation.jsonl",
        [
            codex_meta(originator="codex_exec", session_id="automation"),
            codex_message("user", "generate newsletter"),
        ],
    )
    write_session(tmp_path / "claude.jsonl", "add a dashboard")

    all_sessions = transcripts.survey(tmp_path, max_examples=0)
    interactive_codex = transcripts.survey(
        tmp_path, max_examples=0, source="codex", mode="interactive"
    )
    automated_codex = transcripts.survey(
        tmp_path, max_examples=0, source="codex", mode="automation"
    )

    assert all_sessions.sessions == 3
    assert all_sessions.sources == {"codex": 2, "claude": 1}
    assert all_sessions.modes == {"interactive": 1, "automation": 1, "unknown": 1}
    assert interactive_codex.sessions == 1
    assert interactive_codex.categorized == {"bugfix": 1}
    assert automated_codex.sessions == 1
    assert automated_codex.categorized == {"other": 1}
    assert "codex" in all_sessions.render()
    assert "interactive" in all_sessions.render()


def test_survey_can_select_legacy_unknown_mode(tmp_path):
    write_session(tmp_path / "claude.jsonl", "explain the service")

    result = transcripts.survey(tmp_path, mode="unknown", max_examples=0)

    assert result.sessions == 1
    assert result.sources == {"claude": 1}
    assert result.modes == {"unknown": 1}


def test_cli_mines_codex_sessions_with_filters(tmp_path, capsys):
    write_records(
        tmp_path / "codex.jsonl",
        [codex_meta(), codex_message("user", "fix the crash")],
    )

    assert (
        main(
            [
                "mine",
                "transcripts",
                str(tmp_path),
                "--source",
                "codex",
                "--mode",
                "interactive",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert "Surveyed 1 session" in captured.out
    assert "codex" in captured.out
    assert "interactive" in captured.out
    assert captured.err == ""


def test_cli_reports_when_filters_exclude_every_session(tmp_path, capsys):
    write_records(
        tmp_path / "codex.jsonl",
        [codex_meta(), codex_message("user", "fix the crash")],
    )

    assert (
        main(
            [
                "mine",
                "transcripts",
                str(tmp_path),
                "--source",
                "claude",
            ]
        )
        == 1
    )
    assert "no parseable sessions" in capsys.readouterr().err


def test_session_record_contains_cleaned_conversation_and_metadata(tmp_path):
    p = tmp_path / "codex.jsonl"
    write_records(
        p,
        [
            codex_meta(session_id="export-me"),
            codex_message("user", "<environment_context>hidden</environment_context>"),
            codex_message("user", "Add café search"),
            codex_message("assistant", "Implemented it."),
        ],
        malformed_line=True,
    )

    record = transcripts.session_record(transcripts.parse_session(p))

    assert record == {
        "schema_version": 1,
        "source": "codex",
        "session_id": "export-me",
        "started_at": "2026-07-15T12:00:00Z",
        "cwd": "/code/project",
        "mode": "interactive",
        "category": "feature",
        "first_user_message": "Add café search",
        "messages": [
            {"role": "user", "text": "Add café search", "timestamp": None},
            {"role": "assistant", "text": "Implemented it.", "timestamp": None},
        ],
        "source_path": str(p),
        "malformed_lines": 1,
    }


def test_iter_sessions_filters_unusable_sessions_and_orders_paths(tmp_path):
    write_records(
        tmp_path / "z-codex.jsonl",
        [codex_meta(session_id="z"), codex_message("user", "fix z")],
    )
    write_records(
        tmp_path / "a-codex.jsonl",
        [codex_meta(session_id="a"), codex_message("user", "fix a")],
    )
    write_records(tmp_path / "empty.jsonl", [codex_meta(session_id="empty")])
    write_session(tmp_path / "claude.jsonl", "add a dashboard")

    sessions = list(
        transcripts.iter_sessions(tmp_path, source="codex", mode="interactive")
    )

    assert [session.session_id for session in sessions] == ["a", "z"]


def test_write_sessions_jsonl_is_utf8_and_has_one_record_per_line(tmp_path):
    p = tmp_path / "codex.jsonl"
    write_records(
        p,
        [codex_meta(), codex_message("user", "Improve café search ☕️")],
    )
    output = tmp_path / "nested" / "candidates.jsonl"

    count = transcripts.write_sessions_jsonl(
        transcripts.iter_sessions(tmp_path, source="codex"), output
    )

    assert count == 1
    assert output.read_text().endswith("\n")
    assert "café search ☕️" in output.read_text()
    assert [json.loads(line)["session_id"] for line in output.read_text().splitlines()] == [
        "s1"
    ]


def test_cli_exports_filtered_sessions_and_retains_summary(tmp_path, capsys):
    write_records(
        tmp_path / "codex.jsonl",
        [codex_meta(), codex_message("user", "fix the crash")],
    )
    write_session(tmp_path / "claude.jsonl", "add a dashboard")
    output = tmp_path / "exports" / "codex-candidates.jsonl"

    assert (
        main(
            [
                "mine",
                "transcripts",
                str(tmp_path),
                "--source",
                "codex",
                "--mode",
                "interactive",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert "Surveyed 1 session" in captured.out
    assert f"Wrote 1 cleaned session to {output}" in captured.out
    assert "contains private transcript content" in captured.err
    assert [json.loads(line)["source"] for line in output.read_text().splitlines()] == [
        "codex"
    ]


def test_cli_does_not_write_export_when_filters_match_nothing(tmp_path, capsys):
    write_records(
        tmp_path / "codex.jsonl",
        [codex_meta(), codex_message("user", "fix the crash")],
    )
    output = tmp_path / "should-not-exist.jsonl"

    assert (
        main(
            [
                "mine",
                "transcripts",
                str(tmp_path),
                "--source",
                "claude",
                "--output",
                str(output),
            ]
        )
        == 1
    )

    assert not output.exists()
    assert "no parseable sessions" in capsys.readouterr().err
