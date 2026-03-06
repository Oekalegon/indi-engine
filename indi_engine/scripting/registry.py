"""Script registry: manages .py script files on disk.

Maintains two directories:
  builtin_dir — read-only scripts shipped with the engine
  user_dir    — writeable scripts uploaded by clients

User scripts take precedence over builtin scripts of the same name on load.
"""

import ast
import re
from pathlib import Path

from indi_engine.scripting.sandbox import check_syntax

_MAX_SCRIPT_SIZE = 64 * 1024  # 64 KB
_VALID_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_name(name: str) -> None:
    if not _VALID_NAME.match(name):
        raise ValueError(
            f"Invalid script name '{name}'. "
            "Only letters, digits, underscores, and hyphens are allowed."
        )


def _extract_docstring(source: str) -> str:
    """Return the first line of the module docstring, or empty string."""
    try:
        tree = ast.parse(source)
        if (
            tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)
        ):
            return tree.body[0].value.value.strip().splitlines()[0]
    except SyntaxError:
        pass
    return ""


class ScriptRegistry:
    def __init__(self, builtin_dir: str, user_dir: str) -> None:
        self._builtin = Path(builtin_dir)
        self._user = Path(user_dir)
        self._user.mkdir(parents=True, exist_ok=True)

    def list(self) -> list:
        """Return metadata for all known scripts.

        Returns:
            List of dicts with keys: name, builtin (bool), description (str).
        """
        scripts = []
        if self._builtin.exists():
            for path in sorted(self._builtin.glob("*.py")):
                source = path.read_text(encoding="utf-8")
                scripts.append({
                    "name": path.stem,
                    "builtin": True,
                    "description": _extract_docstring(source),
                })
        for path in sorted(self._user.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            scripts.append({
                "name": path.stem,
                "builtin": False,
                "description": _extract_docstring(source),
            })
        return scripts

    def load(self, name: str) -> str:
        """Return source of a named script.

        User scripts take precedence over builtins.

        Raises:
            ValueError: If name contains invalid characters.
            FileNotFoundError: If no script with that name exists.
        """
        _validate_name(name)
        for base in (self._user, self._builtin):
            p = base / (name + ".py")
            if p.exists():
                return p.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Script '{name}' not found")

    def save(self, name: str, source: str) -> None:
        """Validate and save a script to the user directory.

        Raises:
            ValueError: If name is invalid or source exceeds size limit.
            SyntaxError: If source fails RestrictedPython compilation.
        """
        _validate_name(name)
        if len(source.encode("utf-8")) > _MAX_SCRIPT_SIZE:
            raise ValueError(
                f"Script '{name}' exceeds maximum allowed size of {_MAX_SCRIPT_SIZE} bytes"
            )
        check_syntax(source)
        (self._user / (name + ".py")).write_text(source, encoding="utf-8")

    def delete(self, name: str) -> None:
        """Delete a user script.

        Raises:
            ValueError: If name is invalid.
            PermissionError: If the script is a builtin.
            FileNotFoundError: If the script does not exist.
        """
        _validate_name(name)
        if (self._builtin / (name + ".py")).exists():
            raise PermissionError(f"Cannot delete built-in script '{name}'")
        user_path = self._user / (name + ".py")
        if not user_path.exists():
            raise FileNotFoundError(f"Script '{name}' not found")
        user_path.unlink()
