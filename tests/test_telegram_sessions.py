from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import takopi.telegram.sessions as sessions
from takopi.config import ProjectConfig, ProjectsConfig
from takopi.context import RunContext


class _FakeBot:
    def __init__(self) -> None:
        self.send_calls: list[dict[str, Any]] = []
        self.edit_calls: list[dict[str, Any]] = []
        self.delete_calls: list[tuple[int, int]] = []
        self.document_calls: list[dict[str, Any]] = []

    async def get_updates(
        self,
        offset: int | None,
        timeout_s: int = 50,
        allowed_updates: list[str] | None = None,
    ) -> list[dict] | None:
        _ = offset
        _ = timeout_s
        _ = allowed_updates
        return []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
        disable_notification: bool | None = False,
        entities: list[dict[str, Any]] | None = None,
        parse_mode: str | None = None,
        *,
        replace_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        _ = reply_to_message_id
        _ = disable_notification
        _ = entities
        _ = parse_mode
        _ = replace_message_id
        self.send_calls.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )
        return {"message_id": len(self.send_calls)}

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        entities: list[dict[str, Any]] | None = None,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        *,
        wait: bool = True,
    ) -> dict[str, Any] | None:
        _ = entities
        _ = parse_mode
        _ = wait
        self.edit_calls.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )
        return {"message_id": message_id}

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        self.delete_calls.append((chat_id, message_id))
        return True

    async def set_my_commands(
        self,
        commands: list[dict[str, Any]],
        *,
        scope: dict[str, Any] | None = None,
        language_code: str | None = None,
    ) -> bool:
        _ = commands
        _ = scope
        _ = language_code
        return True

    async def send_document(
        self,
        *,
        chat_id: int,
        document: Path,
        caption: str | None = None,
    ) -> dict[str, Any] | None:
        self.document_calls.append(
            {
                "chat_id": chat_id,
                "document": document,
                "caption": caption,
            }
        )
        return {"message_id": 1}

    async def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: str | None = None,
    ) -> bool:
        _ = callback_query_id
        _ = text
        return True

    async def get_me(self) -> dict[str, Any] | None:
        return {"id": 1}

    async def close(self) -> None:
        return None


def _projects_cfg(
    *, tmp_path: Path, default_engine: str | None = "pi"
) -> ProjectsConfig:
    project = ProjectConfig(
        alias="tui",
        path=tmp_path,
        worktrees_dir=Path("."),
        default_engine=default_engine,
    )
    return ProjectsConfig(projects={"tui": project}, default_project=None)


def _write_session(tmp_path: Path, *, name: str, first_message: str) -> Path:
    session_file = tmp_path / name
    event = {
        "type": "message_start",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": first_message}],
        },
    }
    session_file.write_text(json.dumps(event) + "\n", encoding="utf-8")
    return session_file


@pytest.mark.anyio
async def test_show_sessions_menu_sends_keyboard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bot = _FakeBot()
    projects = _projects_cfg(tmp_path=tmp_path)

    session_a = _write_session(
        tmp_path,
        name="2024-01-01T12-00-00_abc.jsonl",
        first_message="First session message",
    )
    session_b = _write_session(
        tmp_path,
        name="2024-01-02T12-00-00_def.jsonl",
        first_message="Second session message",
    )

    def fake_find_session_files(project_path: Path) -> list[Path]:
        _ = project_path
        return [session_b, session_a]

    monkeypatch.setattr(sessions, "find_session_files", fake_find_session_files)

    await sessions.show_sessions_menu(
        bot,
        1,
        RunContext(project="tui", branch=None),
        projects,
    )

    assert len(bot.send_calls) == 1
    call = bot.send_calls[0]
    assert "Sessions for: tui" in call["text"]

    keyboard = call["reply_markup"]["inline_keyboard"]
    assert any(button[0]["callback_data"].startswith("s:tui:") for button in keyboard)


@pytest.mark.anyio
async def test_show_sessions_menu_edits_existing_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bot = _FakeBot()
    projects = _projects_cfg(tmp_path=tmp_path)

    session_a = _write_session(
        tmp_path,
        name="2024-01-01T12-00-00_abc.jsonl",
        first_message="First session message",
    )

    monkeypatch.setattr(sessions, "find_session_files", lambda _: [session_a])

    await sessions.show_sessions_menu(
        bot,
        1,
        RunContext(project="tui", branch=None),
        projects,
        message_id=123,
    )

    assert len(bot.edit_calls) == 1
    assert bot.edit_calls[0]["message_id"] == 123


@pytest.mark.anyio
async def test_handle_callback_query_refresh_calls_show_menu(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bot = _FakeBot()
    projects = _projects_cfg(tmp_path=tmp_path)
    called: list[dict] = []

    async def fake_show_sessions_menu(
        bot_arg,
        chat_id: int,
        context: RunContext | None,
        projects_arg: ProjectsConfig,
        page: int = 0,
        message_id: int | None = None,
    ) -> None:
        _ = bot_arg
        _ = projects_arg
        called.append(
            {
                "chat_id": chat_id,
                "context": context,
                "page": page,
                "message_id": message_id,
            }
        )

    monkeypatch.setattr(sessions, "show_sessions_menu", fake_show_sessions_menu)

    handled = await sessions.handle_callback_query(
        bot,
        1,
        "refresh:tui",
        projects,
        None,
        message_id=99,
    )

    assert handled is True
    assert called == [
        {
            "chat_id": 1,
            "context": RunContext(project="tui", branch=None),
            "page": 0,
            "message_id": 99,
        }
    ]


@pytest.mark.anyio
async def test_handle_callback_query_page_calls_show_menu(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bot = _FakeBot()
    projects = _projects_cfg(tmp_path=tmp_path)
    called: list[dict] = []

    async def fake_show_sessions_menu(
        bot_arg,
        chat_id: int,
        context: RunContext | None,
        projects_arg: ProjectsConfig,
        page: int = 0,
        message_id: int | None = None,
    ) -> None:
        _ = bot_arg
        _ = projects_arg
        called.append(
            {
                "chat_id": chat_id,
                "context": context,
                "page": page,
                "message_id": message_id,
            }
        )

    monkeypatch.setattr(sessions, "show_sessions_menu", fake_show_sessions_menu)

    handled = await sessions.handle_callback_query(
        bot,
        1,
        "page:tui:2",
        projects,
        None,
        message_id=101,
    )

    assert handled is True
    assert called == [
        {
            "chat_id": 1,
            "context": RunContext(project="tui", branch=None),
            "page": 2,
            "message_id": 101,
        }
    ]


@pytest.mark.anyio
async def test_handle_callback_query_session_calls_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bot = _FakeBot()
    projects = _projects_cfg(tmp_path=tmp_path)

    session_a = _write_session(
        tmp_path,
        name="2024-01-01T12-00-00_abc.jsonl",
        first_message="Export me",
    )

    monkeypatch.setattr(sessions, "find_session_files", lambda _: [session_a])
    exported: list[Path] = []

    async def fake_handle_session_export(
        bot_arg,
        chat_id: int,
        session_file: Path,
    ) -> None:
        _ = bot_arg
        _ = chat_id
        exported.append(session_file)

    monkeypatch.setattr(sessions, "handle_session_export", fake_handle_session_export)

    handled = await sessions.handle_callback_query(
        bot,
        1,
        f"s:tui:{session_a.name[:50]}",
        projects,
        None,
    )

    assert handled is True
    assert exported == [session_a]


@pytest.mark.anyio
async def test_handle_session_export_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bot = _FakeBot()
    session_a = _write_session(
        tmp_path,
        name="2024-01-01T12-00-00_abc.jsonl",
        first_message="Export me",
    )

    def fake_export_session_to_html(session_file: Path) -> Path:
        _ = session_file
        html = tmp_path / "export.html"
        html.write_text("<html></html>", encoding="utf-8")
        return html

    monkeypatch.setattr(sessions, "export_session_to_html", fake_export_session_to_html)

    await sessions.handle_session_export(bot, 1, session_a)

    assert bot.document_calls
    assert not (tmp_path / "export.html").exists()
