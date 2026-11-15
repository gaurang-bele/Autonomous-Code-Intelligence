import os, subprocess, sys, tempfile
from pathlib import Path
from langchain_core.tools import tool
from app.config import get_settings

def _run(cmd, cwd, timeout):
    kw = dict(cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if os.name == "posix":
        def limits():
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout + 1))
            resource.setrlimit(resource.RLIMIT_FSIZE, (5000000, 5000000))
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        kw["preexec_fn"] = limits
    try:
        p = subprocess.run(cmd, **kw)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"Timed out after {timeout} seconds"

def analyze_python_code(code_string: str) -> str:
    cfg = get_settings()
    if len(code_string.encode()) > cfg.max_file_size_bytes:
        return "ERROR: source exceeds MAX_FILE_SIZE_BYTES"
    with tempfile.TemporaryDirectory(prefix="review-sandbox-") as d:
        path = Path(d) / "candidate.py"
        path.write_text(code_string, encoding="utf-8")
        checks = [
            ("syntax", [sys.executable, "-m", "py_compile", str(path)]),
            ("flake8", [sys.executable, "-m", "flake8", str(path), "--max-line-length=88"]),
            ("black", [sys.executable, "-m", "black", "--check", "--diff", str(path)]),
        ]
        out = []
        for name, cmd in checks:
            code, msg = _run(cmd, d, cfg.sandbox_timeout_seconds)
            out.append(f"{name}: {'PASS' if code == 0 else f'FAIL (exit {code})'}" + (f"\n{msg}" if msg else ""))
        return "\n\n".join(out)

@tool
def run_linter_tool(code_string: str) -> str:
    """Lint a Python source string in a temporary directory using syntax, flake8 and black checks."""
    return analyze_python_code(code_string)
