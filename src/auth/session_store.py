from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

_SESSION_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,512}$")


def is_session_token_valid(token: str) -> bool:
    return bool(_SESSION_TOKEN_RE.fullmatch((token or "").strip()))


def read_session_token(path: Path, *, delete_on_invalid: bool = False) -> Optional[str]:
    """Read and validate a session token from file.

    Returns None if file doesn't exist, is empty, or token is invalid.
    """
    try:
        if not path.exists():
            return None

        token = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not token:
            if delete_on_invalid:
                delete_session_token_file(path)
            return None

        if not is_session_token_valid(token):
            logger.warning("无效的会话文件内容，已忽略: %s", path)
            if delete_on_invalid:
                delete_session_token_file(path)
            return None

        return token
    except Exception as e:
        logger.debug("读取会话文件失败: %s (%s)", path, e)
        return None


def write_session_token_file(path: Path, token: str) -> bool:
    """Atomically write session token to file (best effort)."""
    if not is_session_token_valid(token):
        logger.warning("拒绝写入无效会话 token: len=%s", len(token or ""))
        return False

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp.{secrets.token_hex(6)}")
        try:
            tmp.write_text(token, encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)
            except Exception:
                pass
            os.replace(tmp, path)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
        return True
    except Exception as e:
        logger.debug("写入会话文件失败: %s (%s)", path, e)
        return False


def delete_session_token_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
