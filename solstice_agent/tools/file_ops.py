"""
File Operations Tools
=====================
Read, write, edit (surgical find/replace), list, delete.
The edit_file tool is the star — surgical find/replace that preserves
everything else in the file. Way better than rewriting entire files.
"""

import logging
from pathlib import Path

log = logging.getLogger("solstice.tools.file_ops")


def read_file(path: str, max_lines: int = 500) -> str:
    """Read a file and return its contents with line numbers."""
    from .security import validate_path

    path_err = validate_path(path, "read")
    if path_err:
        return f"Error: {path_err}"

    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: File not found: {path}"
        if not p.is_file():
            return f"Error: Not a file: {path}"
        if p.stat().st_size > 5 * 1024 * 1024:
            return f"Error: File too large (>5MB): {path}"

        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        if len(lines) > max_lines:
            shown = lines[:max_lines]
            result = "".join(
                f"{i+1:>4} | {line}" for i, line in enumerate(shown)
            )
            result += f"\n... ({len(lines) - max_lines} more lines truncated)"
            return result

        return "".join(f"{i+1:>4} | {line}" for i, line in enumerate(lines))
    except Exception as e:
        return f"Error reading {path}: {e}"


def write_file(path: str, content: str) -> str:
    """Write content to a file. Creates parent directories if needed."""
    from .security import validate_path

    path_err = validate_path(path, "write")
    if path_err:
        return f"Error: {path_err}"

    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Written: {p} ({len(content)} chars)"
    except Exception as e:
        return f"Error writing {path}: {e}"


def edit_file(path: str, old_text: str, new_text: str) -> str:
    """
    Surgical find/replace in a file. Replaces the FIRST occurrence of
    old_text with new_text. Everything else in the file stays exactly the same.

    This is the right way to edit files — not rewriting the whole thing.
    """
    from .security import validate_path

    path_err = validate_path(path, "edit")
    if path_err:
        return f"Error: {path_err}"

    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: File not found: {path}"

        with open(p, 'r', encoding='utf-8') as f:
            original = f.read()

        if old_text not in original:
            # Try to help — show nearby content
            lines = original.split('\n')
            first_line = old_text.split('\n')[0].strip()
            matches = [
                f"  Line {i+1}: {line.strip()}"
                for i, line in enumerate(lines)
                if first_line[:30] in line
            ]
            hint = ""
            if matches:
                hint = "\n\nDid you mean one of these?\n" + "\n".join(matches[:5])
            return f"Error: old_text not found in {path}.{hint}"

        count = original.count(old_text)
        if count > 1:
            return (f"Warning: old_text appears {count} times in {path}. "
                    f"Only replacing the first occurrence. "
                    f"Use more surrounding context for precision.")

        updated = original.replace(old_text, new_text, 1)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(updated)

        return f"Edited: {p} (replaced {len(old_text)} chars with {len(new_text)} chars)"
    except Exception as e:
        return f"Error editing {path}: {e}"


def list_files(path: str = ".", pattern: str = "*", max_results: int = 100) -> str:
    """List files in a directory, optionally filtered by glob pattern."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: Directory not found: {path}"
        if not p.is_dir():
            return f"Error: Not a directory: {path}"

        files = sorted(p.glob(pattern))[:max_results]
        if not files:
            return f"No files matching '{pattern}' in {path}"

        lines = []
        for f in files:
            size = f.stat().st_size if f.is_file() else 0
            kind = "DIR" if f.is_dir() else f"{size:>8,}B"
            lines.append(f"  {kind}  {f.name}")

        result = f"{path}/  ({len(files)} items)\n" + "\n".join(lines)
        if len(files) >= max_results:
            result += f"\n  ... (truncated at {max_results})"
        return result
    except Exception as e:
        return f"Error listing {path}: {e}"


def apply_patch(patch: str) -> str:
    """
    Apply a structured patch to one or more files. Supports multi-hunk edits
    across multiple files in a single call.

    Patch format (simplified unified diff):
        --- path/to/file.py
        @@
        -old line 1
        -old line 2
        +new line 1
        +new line 2
         context line (unchanged)
        @@
        -another old section
        +another new section

    Rules:
        - Lines starting with '-' are removed (must exist in file)
        - Lines starting with '+' are inserted
        - Lines starting with ' ' (space) are context (must match, kept as-is)
        - '@@' separates hunks within a file
        - '--- path/to/file' starts a new file
        - Empty lines in the patch are treated as context
    """
    if not patch or not patch.strip():
        return "Error: Empty patch"

    results = []
    errors = []

    # Parse the patch into file operations
    files = _parse_patch(patch)

    if not files:
        return "Error: Could not parse patch. Expected format:\n--- path/to/file\n@@\n-old line\n+new line"

    from .security import validate_path

    for file_path, hunks in files:
        path_err = validate_path(file_path, "patch")
        if path_err:
            errors.append(path_err)
            continue

        try:
            p = Path(file_path).expanduser().resolve()
            if not p.exists():
                errors.append(f"File not found: {file_path}")
                continue

            with open(p, 'r', encoding='utf-8') as f:
                content = f.read()

            original = content

            for hunk_idx, (old_lines, new_lines) in enumerate(hunks):
                old_text = "\n".join(old_lines)
                new_text = "\n".join(new_lines)

                if old_text and old_text not in content:
                    # Try stripping trailing whitespace for fuzzy match
                    content_stripped = "\n".join(line.rstrip() for line in content.split("\n"))
                    old_stripped = "\n".join(line.rstrip() for line in old_lines)
                    if old_stripped in content_stripped:
                        # Find the actual position using stripped matching
                        # Rebuild with original lines around the match
                        lines = content.split("\n")
                        stripped = [line.rstrip() for line in lines]
                        old_stripped_lines = [line.rstrip() for line in old_lines]

                        match_start = _find_subsequence(stripped, old_stripped_lines)
                        if match_start >= 0:
                            before = lines[:match_start]
                            after = lines[match_start + len(old_lines):]
                            content = "\n".join(before + new_lines + after)
                            continue

                    errors.append(f"Hunk {hunk_idx + 1} failed for {file_path}: old text not found")
                    continue

                if old_text:
                    content = content.replace(old_text, new_text, 1)
                else:
                    # Pure insertion (no old lines) — append to file
                    if content and not content.endswith("\n"):
                        content += "\n"
                    content += new_text

            if content != original:
                with open(p, 'w', encoding='utf-8') as f:
                    f.write(content)
                hunk_count = len(hunks)
                results.append(f"Patched: {file_path} ({hunk_count} hunk{'s' if hunk_count != 1 else ''})")
            else:
                results.append(f"No changes: {file_path}")

        except Exception as e:
            errors.append(f"Error patching {file_path}: {e}")

    output = "\n".join(results)
    if errors:
        output += "\n\nErrors:\n" + "\n".join(f"  - {e}" for e in errors)
    return output


def _parse_patch(patch_text: str) -> list:
    """
    Parse a patch string into [(file_path, [(old_lines, new_lines), ...]), ...].
    """
    files = []
    current_file = None
    current_hunks = []
    current_old = []
    current_new = []
    in_hunk = False

    for raw_line in patch_text.split("\n"):
        # File header
        if raw_line.startswith("--- "):
            # Save previous file
            if current_file is not None:
                if in_hunk and (current_old or current_new):
                    current_hunks.append((current_old, current_new))
                files.append((current_file, current_hunks))
            current_file = raw_line[4:].strip()
            current_hunks = []
            current_old = []
            current_new = []
            in_hunk = False
            continue

        # Hunk separator
        if raw_line.strip() == "@@":
            if in_hunk and (current_old or current_new):
                current_hunks.append((current_old, current_new))
            current_old = []
            current_new = []
            in_hunk = True
            continue

        if not in_hunk:
            continue

        # Skip +++ lines (some LLMs include them)
        if raw_line.startswith("+++ "):
            continue

        # Parse diff lines
        if raw_line.startswith("-"):
            current_old.append(raw_line[1:])
        elif raw_line.startswith("+"):
            current_new.append(raw_line[1:])
        elif raw_line.startswith(" "):
            # Context line — belongs to both old and new
            current_old.append(raw_line[1:])
            current_new.append(raw_line[1:])
        else:
            # Bare line (no prefix) — treat as context
            current_old.append(raw_line)
            current_new.append(raw_line)

    # Save last file/hunk
    if current_file is not None:
        if in_hunk and (current_old or current_new):
            current_hunks.append((current_old, current_new))
        files.append((current_file, current_hunks))

    return files


def _find_subsequence(haystack: list, needle: list) -> int:
    """Find the starting index of needle in haystack (list of strings). Returns -1 if not found."""
    if not needle:
        return -1
    for i in range(len(haystack) - len(needle) + 1):
        if haystack[i:i + len(needle)] == needle:
            return i
    return -1


def grep_files(pattern: str, path: str = ".", glob: str = None, max_results: int = 50) -> str:
    """
    Search file contents by regex pattern. Returns matching lines with
    file paths and line numbers.
    """
    import re

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Error: Invalid regex pattern: {e}"

    try:
        root = Path(path).expanduser().resolve()
        if not root.exists():
            return f"Error: Path not found: {path}"

        results = []
        glob_pattern = glob or "**/*"

        for filepath in root.glob(glob_pattern):
            if not filepath.is_file():
                continue
            # Skip binary/large files
            if filepath.stat().st_size > 2 * 1024 * 1024:
                continue
            # Skip hidden dirs and common noise
            parts = filepath.relative_to(root).parts
            if any(p.startswith('.') or p in ('node_modules', '__pycache__', 'venv', '.git') for p in parts):
                continue

            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            rel = filepath.relative_to(root)
                            results.append(f"  {rel}:{line_num}: {line.rstrip()}")
                            if len(results) >= max_results:
                                break
            except (OSError, UnicodeDecodeError):
                continue

            if len(results) >= max_results:
                break

        if not results:
            return f"No matches for /{pattern}/ in {path}"

        header = f"{len(results)} match{'es' if len(results) != 1 else ''} for /{pattern}/:"
        output = header + "\n" + "\n".join(results)
        if len(results) >= max_results:
            output += f"\n  ... (truncated at {max_results})"
        return output

    except Exception as e:
        return f"Error searching: {e}"


def find_files(pattern: str, path: str = ".", max_results: int = 100) -> str:
    """
    Find files by name pattern (glob). Searches recursively.
    """
    try:
        root = Path(path).expanduser().resolve()
        if not root.exists():
            return f"Error: Path not found: {path}"

        # If pattern doesn't include **, make it recursive
        if "**" not in pattern:
            search_pattern = f"**/{pattern}"
        else:
            search_pattern = pattern

        results = []
        for filepath in root.glob(search_pattern):
            # Skip hidden dirs
            parts = filepath.relative_to(root).parts
            if any(p.startswith('.') or p in ('node_modules', '__pycache__', 'venv') for p in parts):
                continue

            rel = filepath.relative_to(root)
            if filepath.is_file():
                size = filepath.stat().st_size
                results.append(f"  {size:>8,}B  {rel}")
            else:
                results.append(f"      DIR  {rel}/")

            if len(results) >= max_results:
                break

        if not results:
            return f"No files matching '{pattern}' in {path}"

        output = f"{len(results)} result{'s' if len(results) != 1 else ''} for '{pattern}':\n" + "\n".join(results)
        if len(results) >= max_results:
            output += f"\n  ... (truncated at {max_results})"
        return output

    except Exception as e:
        return f"Error finding files: {e}"


def delete_file(path: str) -> str:
    """Delete a file. Use with caution."""
    from .security import validate_path

    path_err = validate_path(path, "delete")
    if path_err:
        return f"Error: {path_err}"

    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: File not found: {path}"
        if not p.is_file():
            return f"Error: Not a file (use with caution): {path}"
        p.unlink()
        return f"Deleted: {p}"
    except Exception as e:
        return f"Error deleting {path}: {e}"


# --- Schema definitions ---

_SCHEMAS = {
    "read_file": {
        "name": "read_file",
        "description": "Read a file from disk. Returns contents with line numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"},
                "max_lines": {"type": "integer", "description": "Max lines to return (default 500)"},
            },
            "required": ["path"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": "Write content to a file. Creates directories if needed. Use for NEW files only — use edit_file for existing files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to write to"},
                "content": {"type": "string", "description": "File content"},
            },
            "required": ["path", "content"],
        },
    },
    "edit_file": {
        "name": "edit_file",
        "description": "Surgical find/replace in a file. Replaces the first occurrence of old_text with new_text. Preserves everything else. Use this instead of write_file for existing files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"},
                "old_text": {"type": "string", "description": "Exact text to find (must match precisely, including whitespace)"},
                "new_text": {"type": "string", "description": "Text to replace it with"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    "list_files": {
        "name": "list_files",
        "description": "List files in a directory with optional glob pattern.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (default: current dir)"},
                "pattern": {"type": "string", "description": "Glob pattern like '*.py' or '**/*.js'"},
            },
        },
    },
    "apply_patch": {
        "name": "apply_patch",
        "description": (
            "Apply a structured patch to one or more files. Supports multi-hunk edits "
            "across multiple files in a single call. Use this for complex edits that touch "
            "multiple locations or files. Format:\n"
            "--- path/to/file.py\n"
            "@@\n"
            "-old line to remove\n"
            "+new line to add\n"
            " context line (unchanged)\n"
            "@@\n"
            "-another section to change\n"
            "+replacement text\n"
            "\n"
            "Use '--- path' to start a new file, '@@' to separate hunks, "
            "'-' for removals, '+' for additions, ' ' (space) for context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "patch": {
                    "type": "string",
                    "description": "The patch in simplified unified diff format",
                },
            },
            "required": ["patch"],
        },
    },
    "grep_files": {
        "name": "grep_files",
        "description": "Search file contents by regex pattern. Returns matching lines with file paths and line numbers. Use for finding code, function definitions, imports, error messages, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for (case-insensitive)"},
                "path": {"type": "string", "description": "Directory to search in (default: current dir)"},
                "glob": {"type": "string", "description": "File glob filter, e.g. '**/*.py' or '**/*.ts'"},
                "max_results": {"type": "integer", "description": "Max matches to return (default 50)"},
            },
            "required": ["pattern"],
        },
    },
    "find_files": {
        "name": "find_files",
        "description": "Find files by name pattern (glob). Searches recursively. Use to locate files in a project.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "File name pattern, e.g. '*.py', 'README*', 'test_*.js'"},
                "path": {"type": "string", "description": "Directory to search in (default: current dir)"},
                "max_results": {"type": "integer", "description": "Max results to return (default 100)"},
            },
            "required": ["pattern"],
        },
    },
    "delete_file": {
        "name": "delete_file",
        "description": "Delete a file from disk. Irreversible.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to delete"},
            },
            "required": ["path"],
        },
    },
}


def register_file_tools(registry):
    """Register all file operation tools with a ToolRegistry."""
    registry.register("read_file", read_file, _SCHEMAS["read_file"])
    registry.register("write_file", write_file, _SCHEMAS["write_file"])
    registry.register("edit_file", edit_file, _SCHEMAS["edit_file"])
    registry.register("apply_patch", apply_patch, _SCHEMAS["apply_patch"])
    registry.register("grep_files", grep_files, _SCHEMAS["grep_files"])
    registry.register("find_files", find_files, _SCHEMAS["find_files"])
    registry.register("list_files", list_files, _SCHEMAS["list_files"])
    registry.register("delete_file", delete_file, _SCHEMAS["delete_file"])
