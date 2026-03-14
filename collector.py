"""
Context collector — builds a curated, token-budgeted snapshot of a
repository for the LLM to analyse.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Rough chars-per-token ratio (conservative for English + code)
_CHARS_PER_TOKEN = 4
_DEFAULT_TOKEN_BUDGET = 30_000
_MAX_FILE_CHARS = 80_000  # never send more than ~20k tokens from one file

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "venv", ".venv",
    "dist", "build", ".idea", ".vscode", "target", ".gradle",
    ".next", "coverage", ".tox", "egg-info",
}

# ── tiered file priority ────────────────────────────────────────────────────

TIER_1_NAMES = {
    "package.json", "pom.xml", "build.gradle", "build.gradle.kts",
    "requirements.txt", "Pipfile", "pyproject.toml", "Gemfile",
    "go.mod", "Cargo.toml",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "application.properties", "application.yml", "application.yaml",
    ".env.example",
}

TIER_2_NAMES = {
    "Jenkinsfile", ".gitlab-ci.yml", "serverless.yml", "serverless.yaml",
    "nginx.conf", "openapi.yaml", "openapi.yml", "swagger.json",
    "lerna.json", "pnpm-workspace.yaml", "nx.json",
    "tsconfig.json", "webpack.config.js", "vite.config.ts",
    "README.md",
}

TIER_2_PATTERNS = {
    ".github/workflows",    # GitHub Actions
    ".circleci",            # CircleCI
}

TIER_2_EXTENSIONS = {".tf"}  # Terraform

TIER_3_ENTRY_POINTS = {
    "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
    "index.ts", "index.js", "server.ts", "server.js", "app.ts", "app.js",
    "main.go", "main.rs",
    "Program.cs", "Startup.cs",
}

TIER_3_EXTENSIONS = {".py", ".ts", ".js", ".java", ".go", ".rs", ".rb"}

# ── public API ──────────────────────────────────────────────────────────────


def collect(repo_path: str, token_budget: int = _DEFAULT_TOKEN_BUDGET) -> str:
    """
    Walk *repo_path*, select the most architecturally informative files
    within *token_budget* tokens, and return a single prompt-ready string.
    """
    char_budget = token_budget * _CHARS_PER_TOKEN
    sections: List[str] = []
    used = 0

    # Always include the directory tree (cheap, highly informative)
    tree = _build_tree(repo_path)
    tree_section = f"=== DIRECTORY TREE ===\n{tree}\n"
    sections.append(tree_section)
    used += len(tree_section)

    # Gather files into tiers
    t1, t2, t3 = _classify_files(repo_path)

    for tier_label, file_list in [("TIER 1", t1), ("TIER 2", t2), ("TIER 3", t3)]:
        for fpath in file_list:
            remaining = char_budget - used
            if remaining <= 500:
                break
            content = _read_truncated(fpath, min(remaining, _MAX_FILE_CHARS))
            if not content.strip():
                continue
            rel = _rel_path(fpath, repo_path)
            block = f"=== FILE: {rel} ===\n{content}\n"
            sections.append(block)
            used += len(block)

    return "\n".join(sections)


# ── internal helpers ────────────────────────────────────────────────────────


def _classify_files(repo_path: str) -> Tuple[List[Path], List[Path], List[Path]]:
    """Walk the repo once and sort every interesting file into a tier."""
    t1: List[Path] = []
    t2: List[Path] = []
    t3: List[Path] = []
    seen_extensions: Dict[str, int] = {}

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        rel_root = os.path.relpath(root, repo_path)

        for fname in sorted(files):
            fpath = Path(root) / fname
            ext = fpath.suffix.lower()

            if fname in TIER_1_NAMES:
                t1.append(fpath)
            elif fname in TIER_2_NAMES:
                t2.append(fpath)
            elif ext in TIER_2_EXTENSIONS:
                t2.append(fpath)
            elif any(pat in rel_root for pat in TIER_2_PATTERNS):
                t2.append(fpath)
            elif fname in TIER_3_ENTRY_POINTS:
                t3.append(fpath)
            elif ext in TIER_3_EXTENSIONS:
                count = seen_extensions.get(ext, 0)
                if count < 3:
                    t3.append(fpath)
                    seen_extensions[ext] = count + 1

    return t1, t2, t3


def _build_tree(repo_path: str, max_depth: int = 4, max_entries: int = 200) -> str:
    """Build a compact directory tree string."""
    lines: List[str] = []
    count = 0

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        depth = root.replace(repo_path, "").count(os.sep)
        if depth >= max_depth:
            dirs.clear()
            continue
        indent = "  " * depth
        folder = os.path.basename(root)
        lines.append(f"{indent}{folder}/")
        count += 1
        sub_indent = "  " * (depth + 1)
        for f in sorted(files):
            if count >= max_entries:
                lines.append(f"{sub_indent}... (truncated)")
                return "\n".join(lines)
            lines.append(f"{sub_indent}{f}")
            count += 1

    return "\n".join(lines)


def _read_truncated(path: Path, max_chars: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n... (truncated)"
    return text


def _rel_path(fpath: Path, repo_path: str) -> str:
    try:
        return str(fpath.relative_to(repo_path))
    except ValueError:
        return str(fpath)
