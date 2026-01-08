"""Telegram session viewing UX.

Provides /sessions command with inline keyboards for viewing and exporting
pi coding agent sessions. Pi-only feature.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..config import ProjectsConfig
from ..context import RunContext
from ..logging import get_logger
from ..utils.pi_sessions import (
    export_session_to_html,
    find_session_files,
    get_session_metadata,
    path_to_session_dir,
)

if TYPE_CHECKING:
    from .client import BotClient

logger = get_logger(__name__)


async def show_sessions_menu(
    bot: BotClient,
    chat_id: int,
    context: RunContext | None,
    projects: ProjectsConfig,
    page: int = 0,
    message_id: int | None = None,
) -> None:
    """Show sessions menu for current or default project.

    Args:
        bot: Telegram bot client
        chat_id: Telegram chat ID
        context: Current run context (project + branch)
        projects: Project configuration
        page: Page number (0-indexed), 5 sessions per page
    """
    PAGE_SIZE = 5

    if context and context.project:
        project_alias = context.project
        message = f"📂 Sessions for: {project_alias}"
    else:
        if projects.default_project is None:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "❌ No project context found.\n\n"
                    "Use /project <name> first or set default_project in takopi.toml"
                ),
            )
            return

        project_alias = projects.default_project
        message = f"📂 Sessions for: {project_alias}\n\nUsing default project"

    project_config = projects.projects.get(project_alias)
    if not project_config:
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ Project '{project_alias}' not found in config.",
        )
        return

    if project_config.default_engine != "pi":
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"❌ Session viewing is only available for pi engine.\n\n"
                f"Project '{project_alias}' uses: "
                f"{project_config.default_engine or 'default'}"
            ),
        )
        return

    session_files = find_session_files(project_config.path)

    if not session_files:
        session_dir_name = path_to_session_dir(project_config.path)
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"📂 Sessions for: {project_alias}\n\n"
                f"No sessions found.\n\n"
                f"Sessions are stored at:\n"
                f"~/.pi/agent/sessions/{session_dir_name}/"
            ),
        )
        return

    total_sessions = len(session_files)
    total_pages = (total_sessions + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))  # Clamp to valid range

    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_sessions)

    sessions_metadata = []
    for session_file in session_files[start_idx:end_idx]:
        metadata = get_session_metadata(session_file, project_alias)
        sessions_metadata.append(metadata)

    text = f"{message}\n\n"
    text += f"Found {total_sessions} session{'s' if total_sessions > 1 else ''}"
    if total_pages > 1:
        text += f" (page {page + 1}/{total_pages})"
    text += "\n\n"

    keyboard = []

    for idx, metadata in enumerate(sessions_metadata):
        first_msg = metadata.first_message
        if len(first_msg) > 40:
            first_msg = first_msg[:40] + "..."
        button_text = f'📄 "{first_msg}" - {metadata.message_count} msgs'

        # Use short callback data: project:index (Telegram has 64-byte limit)
        # Session filename for lookup
        session_name = metadata.session_file.name
        callback_data = f"s:{project_alias}:{session_name[:50]}"

        keyboard.append([{"text": button_text, "callback_data": callback_data}])

    # Navigation buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            {"text": "⬅️ Prev", "callback_data": f"page:{project_alias}:{page - 1}"}
        )
    if page < total_pages - 1:
        nav_buttons.append(
            {"text": "Next ➡️", "callback_data": f"page:{project_alias}:{page + 1}"}
        )
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append(
        [{"text": "🔄 Refresh", "callback_data": f"refresh:{project_alias}"}]
    )

    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup={"inline_keyboard": keyboard},
            )
        except Exception:
            # Fallback if edit fails (e.g. message too old)
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup={"inline_keyboard": keyboard},
            )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup={"inline_keyboard": keyboard},
        )


async def handle_session_export(
    bot: BotClient,
    chat_id: int,
    session_file: Path,
) -> None:
    """Export session and send HTML file.

    Args:
        bot: Telegram bot client
        chat_id: Telegram chat ID
        session_file: Path to session .jsonl file
    """
    loading_msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            f"⏳ Exporting session to HTML...\n"
            f"Session: {session_file.name}\n"
            f"This may take a few seconds..."
        ),
    )

    loading_msg_id = loading_msg.get("message_id") if loading_msg else None

    try:
        html_path = export_session_to_html(session_file)

        file_size_mb = html_path.stat().st_size / (1024 * 1024)

        if loading_msg_id:
            await bot.delete_message(chat_id, loading_msg_id)

        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"✅ Export complete!\n\n"
                f"📎 {html_path.name} ({file_size_mb:.1f} MB)\n\n"
                f"Download the file below and open in your browser."
            ),
        )

        await bot.send_document(
            chat_id=chat_id,
            document=html_path,
            caption=f"Session export: {html_path.name}",
        )

        html_path.unlink()

        logger.info(
            "sessions.export_success",
            session=str(session_file),
            output=str(html_path),
        )

    except Exception as e:
        if loading_msg_id:
            await bot.delete_message(chat_id, loading_msg_id)

        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ Export failed\n\nError: {e!s}",
        )

        logger.error(
            "sessions.export_failed",
            session=str(session_file),
            error=str(e),
        )


async def handle_callback_query(
    bot: BotClient,
    chat_id: int,
    callback_data: str,
    projects: ProjectsConfig,
    context: RunContext | None,
    message_id: int | None = None,
) -> bool:
    """Handle callback query from inline keyboard.

    Args:
        bot: Telegram bot client
        chat_id: Telegram chat ID
        callback_data: Callback data from button
        projects: Project configuration
        context: Current run context

    Returns:
        True if callback was handled, False otherwise
    """
    if callback_data.startswith("s:"):
        # Format: s:<project>:<session_filename_prefix>
        parts = callback_data.split(":", 2)
        if len(parts) < 3:
            return False
        project_alias = parts[1]
        session_prefix = parts[2]

        project_config = projects.projects.get(project_alias)
        if not project_config:
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ Project '{project_alias}' not found.",
            )
            return True

        # Find session file by prefix
        session_files = find_session_files(project_config.path)
        session_file = next(
            (f for f in session_files if f.name.startswith(session_prefix)),
            None,
        )

        if session_file is None:
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Session not found. It may have been deleted.",
            )
            return True

        await handle_session_export(bot, chat_id, session_file)
        return True

    elif callback_data.startswith("refresh:"):
        project_alias = callback_data.split(":", 1)[1]

        logger.info(
            "sessions.refresh",
            project=project_alias,
        )

        refresh_context = RunContext(project=project_alias, branch=None)
        await show_sessions_menu(
            bot, chat_id, refresh_context, projects, message_id=message_id
        )

        return True

    elif callback_data.startswith("page:"):
        # Format: page:<project>:<page_number>
        parts = callback_data.split(":")
        if len(parts) < 3:
            return False
        project_alias = parts[1]
        try:
            page = int(parts[2])
        except ValueError:
            return False

        logger.info(
            "sessions.page",
            project=project_alias,
            page=page,
        )

        page_context = RunContext(project=project_alias, branch=None)
        await show_sessions_menu(
            bot, chat_id, page_context, projects, page=page, message_id=message_id
        )

        return True

    return False
