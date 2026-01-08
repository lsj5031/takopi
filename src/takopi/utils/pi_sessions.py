"""Pi session management utilities.

This module provides utilities for pi coding agent sessions:
- Reading session files from ~/.pi/agent/sessions/
- Extracting session metadata (first user message, message count)
- Exporting sessions to HTML via pi --export

Pi-only feature. Other engines can be added by future contributors.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PiSessionMetadata:
    """Metadata about a pi session."""

    session_file: Path
    project_alias: str
    first_message: str
    message_count: int
    created_at: str


def get_pi_session_dir() -> Path:
    """Get pi session storage directory.

    Respects PI_CODING_AGENT_DIR environment variable.
    Defaults to ~/.pi/agent/sessions/

    Returns:
        Path to pi sessions directory
    """
    if env_dir := os.environ.get("PI_CODING_AGENT_DIR"):
        base = Path(env_dir).expanduser()
    else:
        base = Path.home() / ".pi" / "agent"

    return base / "sessions"


def path_to_session_dir(project_path: Path) -> str:
    """Convert project path to pi's session directory name.

    Pi uses a specific naming scheme:
    /home/user/code/Tui -> --home-user-code-Tui--

    Args:
        project_path: Absolute path to project

    Returns:
        Session directory name
    """
    safe = str(project_path).lstrip("/\\").replace("/", "-").replace("\\", "-")
    return f"--{safe}--"


def find_session_files(
    project_path: Path, session_dir: Path | None = None
) -> list[Path]:
    """Find all pi session files for a project.

    Args:
        project_path: Absolute path to project
        session_dir: Override pi session directory (for testing)

    Returns:
        List of session file paths, sorted by modification time (newest first)
    """
    if session_dir is None:
        session_dir = get_pi_session_dir()

    project_session_dir = session_dir / path_to_session_dir(project_path)

    if not project_session_dir.exists():
        return []

    sessions = list(project_session_dir.glob("*.jsonl"))
    sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return sessions


def extract_first_message(session_file: Path) -> str | None:
    """Extract first user message from pi session file.

    Pi session files are JSONL (newline-delimited JSON).
    We look for the first message with role="user".

    Args:
        session_file: Path to .jsonl session file

    Returns:
        First user message text, or None if not found

    Example:
        >>> extract_first_message(session_path)
        'Implement OAuth login flow'
    """
    try:
        with open(session_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)

                    if event.get("type") in ("message_start", "message"):
                        message = event.get("message", {})
                        if message.get("role") == "user":
                            content = message.get("content", [])
                            text = ""
                            if isinstance(content, str):
                                text = content
                            elif isinstance(content, list) and len(content) > 0:
                                first_item = content[0]
                                if isinstance(first_item, dict):
                                    text = first_item.get("text", "")
                            
                            if text:
                                return (
                                    text[:100] + "..."
                                    if len(text) > 100
                                    else text
                                )

                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

        return None

    except (FileNotFoundError, IOError):
        return None


def count_messages(session_file: Path) -> int:
    """Count total user messages in pi session file.

    Args:
        session_file: Path to .jsonl session file

    Returns:
        Number of user messages in session
    """
    try:
        count = 0
        with open(session_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)

                    if event.get("type") in ("message_start", "message"):
                        message = event.get("message", {})
                        if message.get("role") == "user":
                            count += 1

                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

        return count

    except (FileNotFoundError, IOError):
        return 0


def get_session_metadata(
    session_file: Path,
    project_alias: str,
) -> PiSessionMetadata:
    """Extract metadata from a pi session file.

    Args:
        session_file: Path to .jsonl session file
        project_alias: Project name for display

    Returns:
        PiSessionMetadata object
    """
    first_message = extract_first_message(session_file) or "Untitled session"
    message_count = count_messages(session_file)

    timestamp = session_file.stem.split("_")[0]

    return PiSessionMetadata(
        session_file=session_file,
        project_alias=project_alias,
        first_message=first_message,
        message_count=message_count,
        created_at=timestamp,
    )


def export_session_to_html(
    session_file: Path,
    output_file: Path | None = None,
    export_dir: Path = Path("/tmp/pi-exports"),
) -> Path:
    """Export a pi session to HTML using pi --export.

    Args:
        session_file: Path to session .jsonl file
        output_file: Specific output filename. If None, auto-generates.
        export_dir: Directory for exports. Defaults to /tmp/pi-exports/

    Returns:
        Path to exported HTML file

    Raises:
        FileNotFoundError: If pi not installed
        subprocess.CalledProcessError: If pi --export fails
    """
    try:
        subprocess.run(
            ["which", "pi"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise FileNotFoundError(
            "pi not found. Install with: npm install -g @anthropics/claude-code"
        ) from e

    export_dir.mkdir(parents=True, exist_ok=True)

    if output_file is None:
        import time

        timestamp_str = time.strftime("%Y%m%d-%H%M%S")

        session_parent = session_file.parent.name
        project_name = session_parent.strip("-").replace("-", "_")

        output_file = export_dir / f"{project_name}-{timestamp_str}.html"

    result = subprocess.run(
        ["pi", "--export", str(session_file), str(output_file)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            ["pi", "--export", str(session_file), str(output_file)],
            result.stderr,
        )

    return output_file
