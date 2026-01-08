"""Tests for pi session utilities."""

import json
from pathlib import Path

from takopi.utils.pi_sessions import (
    count_messages,
    extract_first_message,
    find_session_files,
    get_session_metadata,
    path_to_session_dir,
)


def test_path_to_session_dir_basic() -> None:
    result = path_to_session_dir(Path("/home/user/code/project"))
    assert result == "--home-user-code-project--"


def test_path_to_session_dir_with_special_chars() -> None:
    result = path_to_session_dir(Path("/home/leo/github/Tui"))
    assert result == "--home-leo-github-Tui--"


def test_find_session_files_empty(tmp_path: Path) -> None:
    result = find_session_files(Path("/nonexistent"), session_dir=tmp_path)
    assert result == []


def test_find_session_files_finds_sessions(tmp_path: Path) -> None:
    project_path = Path("/home/user/project")
    session_dir = tmp_path / path_to_session_dir(project_path)
    session_dir.mkdir(parents=True)

    session1 = session_dir / "2024-01-01T12-00-00-abc.jsonl"
    session2 = session_dir / "2024-01-02T12-00-00-def.jsonl"
    session1.write_text("{}")
    session2.write_text("{}")

    result = find_session_files(project_path, session_dir=tmp_path)
    assert len(result) == 2


def test_extract_first_message_basic(tmp_path: Path) -> None:
    session_file = tmp_path / "test.jsonl"
    event = {
        "type": "message_start",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Test message"}],
        },
    }
    session_file.write_text(json.dumps(event) + "\n")

    result = extract_first_message(session_file)
    assert result == "Test message"


def test_extract_first_message_truncates_long(tmp_path: Path) -> None:
    session_file = tmp_path / "test.jsonl"
    long_text = "A" * 150
    event = {
        "type": "message_start",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": long_text}],
        },
    }
    session_file.write_text(json.dumps(event) + "\n")

    result = extract_first_message(session_file)
    assert result is not None
    assert len(result) == 103
    assert result.endswith("...")


def test_extract_first_message_skips_assistant(tmp_path: Path) -> None:
    session_file = tmp_path / "test.jsonl"
    lines = [
        json.dumps(
            {
                "type": "message_start",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Assistant message"}],
                },
            }
        ),
        json.dumps(
            {
                "type": "message_start",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "User message"}],
                },
            }
        ),
    ]
    session_file.write_text("\n".join(lines) + "\n")

    result = extract_first_message(session_file)
    assert result == "User message"


def test_extract_first_message_not_found(tmp_path: Path) -> None:
    session_file = tmp_path / "test.jsonl"
    session_file.write_text("")

    result = extract_first_message(session_file)
    assert result is None


def test_count_messages_basic(tmp_path: Path) -> None:
    session_file = tmp_path / "test.jsonl"
    lines = [
        json.dumps(
            {"type": "message_start", "message": {"role": "user", "content": []}}
        ),
        json.dumps(
            {"type": "message_start", "message": {"role": "assistant", "content": []}}
        ),
        json.dumps(
            {"type": "message_start", "message": {"role": "user", "content": []}}
        ),
    ]
    session_file.write_text("\n".join(lines) + "\n")

    result = count_messages(session_file)
    assert result == 2


def test_count_messages_empty(tmp_path: Path) -> None:
    session_file = tmp_path / "test.jsonl"
    session_file.write_text("")

    result = count_messages(session_file)
    assert result == 0


def test_get_session_metadata_basic(tmp_path: Path) -> None:
    session_file = tmp_path / "2024-01-15T10-30-00-abc.jsonl"
    event = {
        "type": "message_start",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Fix bug"}],
        },
    }
    session_file.write_text(json.dumps(event) + "\n")

    result = get_session_metadata(session_file, "myproject")

    assert result.session_file == session_file
    assert result.project_alias == "myproject"
    assert result.first_message == "Fix bug"
    assert result.message_count == 1
