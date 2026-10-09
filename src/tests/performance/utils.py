def _stderr_without_starlette_deprecation(stderr: str) -> str:
    """Drop the benign StarletteDeprecationWarning (httpx/testclient) emitted at
    import time so a genuine error/traceback still fails the test."""
    kept: list[str] = []
    lines = stderr.splitlines()
    i = 0
    while i < len(lines):
        if "StarletteDeprecationWarning" in lines[i]:
            i += 1
            if i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\t")):
                i += 1  # skip the source-echo line that follows the warning
            continue
        kept.append(lines[i])
        i += 1
    return "\n".join(kept).strip()


def _stderr_without_py314_anyio_syntax_warning(stderr: str) -> str:
    """Drop the Python 3.14 SyntaxWarning emitted because anyio returns in a finally block"""
    WARNING = "SyntaxWarning: 'return' in a 'finally' block"

    lines = stderr.splitlines()
    for i, line in enumerate(lines):
        if WARNING in line:
            lines.pop(i)  # SyntaxWarning: 'return' in a 'finally' block
            if i < len(lines):
                assert lines[i] == "  return result"
                lines.pop(i)  #   return result
            break

    return "\n".join(lines).strip()


def _strip_benign_warnings(stderr: str) -> str:
    """Drop the benign warnings emitted at import time so a genuine error/traceback still fails the test."""
    stderr = _stderr_without_starlette_deprecation(stderr)
    stderr = _stderr_without_py314_anyio_syntax_warning(stderr)
    return stderr
