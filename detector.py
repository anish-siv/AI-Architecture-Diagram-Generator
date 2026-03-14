"""
Technology detector — scans a repository for known config files and
infers the technology stack and architectural components.
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Set

# ── file‑name → parser mapping ──────────────────────────────────────────────

TARGET_FILES = [
    # Package managers
    "package.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "requirements.txt",
    "Pipfile",
    "pyproject.toml",
    "Gemfile",
    "go.mod",
    "Cargo.toml",
    # Containers
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    # Environment
    ".env.example",
    ".env",
    # Spring
    "application.properties",
    "application.yml",
    "application.yaml",
    # CI/CD
    "Jenkinsfile",
    ".gitlab-ci.yml",
    # Serverless / IaC
    "serverless.yml",
    "serverless.yaml",
    # API specs
    "openapi.yaml",
    "openapi.yml",
    "swagger.json",
    # Monorepo
    "lerna.json",
    "pnpm-workspace.yaml",
    "nx.json",
    # Docs (last — lowest priority for rule-based)
    "README.md",
]

TEMPLATE_DIRS = ["templates", "views", "pages"]
TEMPLATE_EXTENSIONS = {".html", ".htm"}

# ── keyword → technology mapping ────────────────────────────────────────────

TECH_KEYWORDS: Dict[str, List[str]] = {
    # JavaScript / TypeScript
    "react":        ["react", "react-dom", "next"],
    "vue":          ["vue", "nuxt"],
    "angular":      ["@angular/core"],
    "svelte":       ["svelte"],
    "express":      ["express"],
    "nestjs":       ["@nestjs/core"],
    "fastify":      ["fastify"],
    "nextjs":       ["next"],
    "tailwindcss":  ["tailwindcss"],
    "typescript":   ["typescript"],
    "prisma":       ["prisma", "@prisma/client"],
    # Python
    "django":       ["django"],
    "flask":        ["flask"],
    "fastapi":      ["fastapi"],
    "celery":       ["celery"],
    "sqlalchemy":   ["sqlalchemy"],
    "pytorch":      ["torch", "pytorch"],
    "tensorflow":   ["tensorflow"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "langchain":    ["langchain"],
    "openai":       ["openai"],
    "pandas":       ["pandas"],
    "numpy":        ["numpy"],
    # Java / Kotlin
    "spring-boot":  ["spring-boot", "org.springframework"],
    "spring-security": ["spring-security", "spring-boot-starter-security"],
    "thymeleaf":    ["thymeleaf"],
    # Ruby
    "rails":        ["rails"],
    # Go
    "gin":          ["github.com/gin-gonic/gin"],
    "fiber":        ["github.com/gofiber/fiber"],
    # Databases
    "postgresql":   ["postgres", "postgresql", "psycopg", "psycopg2"],
    "mysql":        ["mysql", "mysql2"],
    "mongodb":      ["mongoose", "mongodb", "pymongo"],
    "redis":        ["redis", "ioredis"],
    "h2":           ["com.h2database", "h2database", "h2:mem", "h2:file", "jdbc:h2"],
    "sqlite":       ["sqlite", "sqlite3"],
    "elasticsearch":["elasticsearch"],
    # Auth — embedded middleware (runs inside the backend)
    "jwt":          ["jsonwebtoken", "pyjwt"],
    "passport":     ["passport"],
    # Auth — external services (separate systems)
    "oauth":        ["oauth", "authlib"],
    "auth0":        ["auth0"],
    "firebase-auth":["firebase", "firebase-admin"],
    # Cloud / Infra
    "aws":          ["aws-sdk", "boto3", "aws-cdk"],
    "gcp":          ["google-cloud", "@google-cloud"],
    "azure":        ["azure", "@azure"],
    "docker":       ["docker"],
    "kubernetes":   ["kubernetes", "k8s"],
    "terraform":    ["terraform"],
    # Messaging / Queues
    "rabbitmq":     ["amqplib", "pika", "rabbitmq"],
    "kafka":        ["kafkajs", "confluent-kafka", "kafka"],
    # Misc
    "graphql":      ["graphql", "apollo", "@apollo/server"],
    "stripe":       ["stripe"],
    "sendgrid":     ["sendgrid", "@sendgrid/mail"],
    "s3":           ["s3", "minio"],
    # Server-rendered frontend / CDN
    "bootstrap":    ["bootstrap"],
    "font-awesome": ["font-awesome", "fontawesome"],
    # CI/CD
    "github-actions": ["uses:", "github.com/actions"],
    "jenkins":      ["jenkinsfile", "pipeline {"],
    "gitlab-ci":    [".gitlab-ci"],
    "circleci":     [".circleci"],
    # IaC / Serverless
    "serverless-fw": ["serverless"],
    "cloudformation": ["aws::cloudformation", "AWSTemplateFormatVersion"],
    # API style
    "rest-api":     ["openapi", "swagger"],
    "grpc":         ["grpc", "protobuf"],
    "websocket":    ["socket.io", "websocket", "sockjs"],
}

# ── technology → component category ─────────────────────────────────────────

COMPONENT_MAP: Dict[str, str] = {
    "react":        "Frontend",
    "vue":          "Frontend",
    "angular":      "Frontend",
    "svelte":       "Frontend",
    "nextjs":       "Frontend",
    "tailwindcss":  "Frontend",
    "express":      "Backend",
    "nestjs":       "Backend",
    "fastify":      "Backend",
    "django":       "Backend",
    "flask":        "Backend",
    "fastapi":      "Backend",
    "spring-boot":  "Backend",
    "rails":        "Backend",
    "gin":          "Backend",
    "fiber":        "Backend",
    "postgresql":   "Database",
    "mysql":        "Database",
    "mongodb":      "Database",
    "redis":        "Cache/Database",
    "h2":           "Database",
    "sqlite":       "Database",
    "elasticsearch":"Search Engine",
    "thymeleaf":    "Backend",
    "bootstrap":    "Frontend",
    "font-awesome": "Frontend",
    "spring-security":"Backend",
    "passport":     "Backend",
    "jwt":          "Backend",
    "oauth":        "Authentication",
    "auth0":        "Authentication",
    "firebase-auth":"Authentication",
    "aws":          "Cloud Services",
    "gcp":          "Cloud Services",
    "azure":        "Cloud Services",
    "docker":       "Containerisation",
    "kubernetes":   "Orchestration",
    "terraform":    "Infrastructure as Code",
    "pytorch":      "AI/ML",
    "tensorflow":   "AI/ML",
    "scikit-learn": "AI/ML",
    "langchain":    "AI/ML",
    "openai":       "AI/ML",
    "pandas":       "AI/ML",
    "numpy":        "AI/ML",
    "celery":       "Task Queue",
    "rabbitmq":     "Message Broker",
    "kafka":        "Message Broker",
    "graphql":      "API Layer",
    "prisma":       "ORM",
    "sqlalchemy":   "ORM",
    "stripe":       "Payments",
    "sendgrid":     "Email Service",
    "s3":           "Object Storage",
    "typescript":   "Language",
    "github-actions":"CI/CD",
    "jenkins":      "CI/CD",
    "gitlab-ci":    "CI/CD",
    "circleci":     "CI/CD",
    "serverless-fw":"Infrastructure as Code",
    "cloudformation":"Infrastructure as Code",
    "rest-api":     "API Layer",
    "grpc":         "API Layer",
    "websocket":    "API Layer",
    "nginx":        "Reverse Proxy",
}

# ── knowledge base loader ────────────────────────────────────────────────────
#
# KB entries are stored SEPARATELY from TECH_KEYWORDS because they should
# only match against package-manager dependency lists (package.json deps,
# requirements.txt lines, pyproject.toml deps) — never against free-text
# files like READMEs, Dockerfiles, or compose files where short package
# names cause rampant false positives.

_KB_PATH = Path(__file__).parent / "data" / "knowledge_base.json"

_KB_SKIP_CATEGORIES = {"Library", "Testing", "Developer Tool", "Build Tool",
                       "CLI Tool", "Logging", "Documentation", "Security"}

# package_name -> category (only for KB-sourced packages)
KB_PACKAGE_MAP: Dict[str, str] = {}


def _load_knowledge_base() -> None:
    """Load data/knowledge_base.json into KB_PACKAGE_MAP.
    Only called once at module load.  Silently no-ops if the file is missing."""
    if not _KB_PATH.exists():
        return
    try:
        kb = json.loads(_KB_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    for registry in ("pypi", "npm"):
        for pkg_name, entry in kb.get(registry, {}).items():
            category = entry.get("category", "Library")
            if category in _KB_SKIP_CATEGORIES:
                continue
            key = pkg_name.lower()
            if key not in COMPONENT_MAP:
                KB_PACKAGE_MAP[key] = category


_load_knowledge_base()

# ── scanning helpers ─────────────────────────────────────────────────────────


# Config files that describe the app's own stack.  These should only be used
# from the repo root (or src/).  A docs/package.json or examples/requirements.txt
# describes a sub-project, not the main application.
_ROOT_ONLY_FILES = {
    "package.json", "pom.xml", "build.gradle", "build.gradle.kts",
    "requirements.txt", "Pipfile", "pyproject.toml", "Gemfile",
    "go.mod", "Cargo.toml",
}

_NON_APP_DIRS = {
    "docs", "documentation", "examples", "samples", "fixtures",
    "test", "tests", "spec", "specs", "e2e", "__tests__",
    "scripts", "tools", "benchmarks",
}


def _find_target_files(repo_path: str) -> Dict[str, Path]:
    """Walk the repo (skipping common noise dirs) and return found target files.
    For package-manager files, only accept repo root or app source directories."""
    skip_dirs = {"node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build"}
    found: Dict[str, Path] = {}
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        rel_root = os.path.relpath(root, repo_path)
        depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1
        top_dir = rel_root.split(os.sep)[0] if rel_root != "." else ""
        for fname in files:
            if fname not in TARGET_FILES:
                continue
            if fname in found:
                continue
            if fname in _ROOT_ONLY_FILES:
                if depth > 1 or top_dir.lower() in _NON_APP_DIRS:
                    continue
            found[fname] = Path(root) / fname
    return found


def _find_template_files(repo_path: str) -> List[Path]:
    """Find HTML template files inside common template directories."""
    skip_dirs = {"node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build"}
    templates: List[Path] = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        if any(td in Path(root).parts for td in TEMPLATE_DIRS):
            for fname in files:
                if Path(fname).suffix in TEMPLATE_EXTENSIONS:
                    templates.append(Path(root) / fname)
    return templates


def _scan_templates(templates: List[Path]) -> Set[str]:
    """Scan HTML template files for template engine markers and CDN dependencies."""
    techs: Set[str] = set()
    cdn_patterns = {
        "bootstrap":    [r"bootstrap", r"cdn.*bootstrap"],
        "font-awesome": [r"font-awesome", r"fontawesome"],
        "tailwindcss":  [r"tailwindcss", r"cdn.*tailwind"],
    }
    engine_markers = {
        "thymeleaf":  [r"th:", r"xmlns:th\s*=.*thymeleaf"],
        "django":     [r"\{%\s*(?:extends|block|load)\b", r"\{\{"],
        "rails":      [r"<%=?\s"],
    }
    for tpl in templates:
        text = _read_text(tpl, max_bytes=128_000)
        if not text:
            continue
        lower = text.lower()
        for tech, patterns in cdn_patterns.items():
            if any(re.search(p, lower) for p in patterns):
                techs.add(tech)
        for tech, patterns in engine_markers.items():
            if any(re.search(p, lower) for p in patterns):
                techs.add(tech)
    return techs


def _read_text(path: Path, max_bytes: int = 512_000) -> str:
    """Read a text file, returning empty string on failure."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
    except OSError:
        return ""


# ── per‑file parsers ────────────────────────────────────────────────────────


def _parse_package_json(text: str) -> Set[str]:
    techs: Set[str] = set()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return techs
    all_deps = list((data.get("dependencies") or {}).keys()) + \
               list((data.get("devDependencies") or {}).keys())
    dep_str = " ".join(all_deps).lower()
    for tech, keywords in TECH_KEYWORDS.items():
        if any(kw in dep_str for kw in keywords):
            techs.add(tech)
    # Exact match against KB for each declared dependency
    for dep in all_deps:
        dep_lower = dep.lower()
        if dep_lower in KB_PACKAGE_MAP:
            techs.add(dep_lower)
    return techs


def _parse_requirements_txt(text: str) -> Set[str]:
    techs: Set[str] = set()
    lines = text.lower().splitlines()
    for tech, keywords in TECH_KEYWORDS.items():
        if any(kw in line for line in lines for kw in keywords):
            techs.add(tech)
    # Exact match against KB for each pip package
    for line in lines:
        pkg = re.split(r"[>=<!\[;#\s]", line.strip())[0]
        if pkg and pkg in KB_PACKAGE_MAP:
            techs.add(pkg)
    return techs


def _parse_pom_xml(text: str) -> Set[str]:
    """Match against <groupId> and <artifactId> values for precision."""
    techs: Set[str] = set()
    ids = re.findall(r"<(?:groupId|artifactId)>\s*(.+?)\s*</", text, re.IGNORECASE)
    id_blob = " ".join(ids).lower()
    for tech, keywords in TECH_KEYWORDS.items():
        if any(kw in id_blob for kw in keywords):
            techs.add(tech)
    return techs


def _parse_dockerfile(text: str) -> Set[str]:
    techs: Set[str] = {"docker"}
    lower = text.lower()
    if "python" in lower:
        techs.add("python-runtime")
    if "node" in lower:
        techs.add("node-runtime")
    if "java" in lower or "openjdk" in lower:
        techs.add("java-runtime")
    if "nginx" in lower:
        techs.add("nginx")
    return techs


def _parse_docker_compose(text: str) -> Set[str]:
    techs: Set[str] = {"docker"}
    lower = text.lower()
    for tech, keywords in TECH_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            techs.add(tech)
    return techs


def _parse_env_example(text: str) -> Set[str]:
    techs: Set[str] = set()
    lower = text.lower()
    env_hints = {
        "database_url": "postgresql",
        "mongo":        "mongodb",
        "redis":        "redis",
        "aws":          "aws",
        "stripe":       "stripe",
        "sendgrid":     "sendgrid",
        "openai":       "openai",
        "auth0":        "auth0",
        "firebase":     "firebase-auth",
        "jwt":          "jwt",
        "s3":           "s3",
    }
    for hint, tech in env_hints.items():
        if hint in lower:
            techs.add(tech)
    return techs


def _parse_application_properties(text: str) -> Set[str]:
    """Parse Spring application.properties / application.yml."""
    techs: Set[str] = set()
    lower = text.lower()
    prop_hints = {
        "jdbc:h2":          "h2",
        "jdbc:mysql":       "mysql",
        "jdbc:postgresql":  "postgresql",
        "jdbc:mongodb":     "mongodb",
        "jdbc:sqlite":      "sqlite",
        "spring.security":  "spring-security",
        "spring.redis":     "redis",
        "spring.data.mongodb": "mongodb",
        "spring.elasticsearch": "elasticsearch",
        "spring.kafka":     "kafka",
        "spring.rabbitmq":  "rabbitmq",
        "thymeleaf":        "thymeleaf",
    }
    for hint, tech in prop_hints.items():
        if hint in lower:
            techs.add(tech)
    return techs


def _parse_cicd(text: str) -> Set[str]:
    """Parse CI/CD config files (Jenkinsfile, .gitlab-ci.yml, GH Actions).
    Only detects the CI platform itself — CI scripts reference many tools
    (linters, test runners, deploy targets) that don't describe the app."""
    techs: Set[str] = set()
    lower = text.lower()
    if "uses:" in lower or "github.com/actions" in lower:
        techs.add("github-actions")
    if "pipeline {" in lower or "jenkinsfile" in lower:
        techs.add("jenkins")
    if ".gitlab-ci" in lower:
        techs.add("gitlab-ci")
    if ".circleci" in lower:
        techs.add("circleci")
    if "docker" in lower:
        techs.add("docker")
    return techs


def _parse_api_spec(text: str) -> Set[str]:
    """Parse OpenAPI / Swagger specs.  Only flags the API style itself —
    the spec body contains too many generic words to keyword-match safely."""
    techs: Set[str] = {"rest-api"}
    lower = text.lower()
    if "graphql" in lower:
        techs.add("graphql")
    if "grpc" in lower:
        techs.add("grpc")
    if "websocket" in lower or "socket.io" in lower:
        techs.add("websocket")
    return techs


def _parse_monorepo(text: str) -> Set[str]:
    """Detect monorepo tooling."""
    return set()


def _parse_readme(text: str) -> Set[str]:
    """README is too noisy to use as a primary source — it often lists
    technologies as examples or comparisons, not as declarations of
    what THIS project actually uses.  Return an empty set here; the
    detect() function uses _readme_confirmations() to boost confidence
    in technologies already found by other parsers."""
    return set()


def _readme_confirmations(text: str, candidates: Set[str]) -> Set[str]:
    """Return the subset of *candidates* that are also mentioned in the README.
    This is used only for confidence boosting, never for new detections."""
    confirmed: Set[str] = set()
    lower = text.lower()
    for tech in candidates:
        keywords = TECH_KEYWORDS.get(tech, [])
        if any(re.search(rf"\b{re.escape(kw)}\b", lower) for kw in keywords):
            confirmed.add(tech)
    return confirmed


_PARSERS = {
    "package.json":         _parse_package_json,
    "pom.xml":              _parse_pom_xml,
    "build.gradle":         _parse_pom_xml,
    "requirements.txt":     _parse_requirements_txt,
    "Pipfile":              _parse_requirements_txt,
    "pyproject.toml":       _parse_requirements_txt,
    "Gemfile":              _parse_requirements_txt,
    "go.mod":               _parse_requirements_txt,
    "Cargo.toml":           _parse_requirements_txt,
    "Dockerfile":           _parse_dockerfile,
    "docker-compose.yml":   _parse_docker_compose,
    "docker-compose.yaml":  _parse_docker_compose,
    "compose.yml":          _parse_docker_compose,
    "compose.yaml":         _parse_docker_compose,
    ".env.example":         _parse_env_example,
    ".env":                 _parse_env_example,
    "README.md":            _parse_readme,
    "application.properties": _parse_application_properties,
    "application.yml":      _parse_application_properties,
    "application.yaml":     _parse_application_properties,
    # CI/CD
    "Jenkinsfile":          _parse_cicd,
    ".gitlab-ci.yml":       _parse_cicd,
    # IaC / Serverless
    "serverless.yml":       _parse_requirements_txt,
    "serverless.yaml":      _parse_requirements_txt,
    # API specs
    "openapi.yaml":         _parse_api_spec,
    "openapi.yml":          _parse_api_spec,
    "swagger.json":         _parse_api_spec,
    # Monorepo
    "lerna.json":           _parse_monorepo,
    "pnpm-workspace.yaml":  _parse_monorepo,
    "nx.json":              _parse_monorepo,
}

# ── GitHub Actions scanner ───────────────────────────────────────────────────


def _find_github_actions(repo_path: str) -> List[Path]:
    workflows_dir = Path(repo_path) / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return []
    return [f for f in workflows_dir.iterdir() if f.suffix in (".yml", ".yaml")]


# ── source-import scanner ───────────────────────────────────────────────────

_IMPORT_PATTERNS: Dict[str, List[str]] = {
    ".py":   [r"^\s*(?:from|import)\s+([\w.]+)"],
    ".ts":   [r"""(?:from\s+['"](.+?)['"]|require\s*\(\s*['"](.+?)['"]\s*\))"""],
    ".js":   [r"""(?:from\s+['"](.+?)['"]|require\s*\(\s*['"](.+?)['"]\s*\))"""],
    ".java": [r"^\s*import\s+([\w.]+)"],
    ".go":   [r'"([\w./]+)"'],
    ".rb":   [r"""^\s*(?:require|gem)\s+['"](.+?)['"]"""],
}

_SOURCE_EXTENSIONS = set(_IMPORT_PATTERNS.keys())


def _scan_source_imports(repo_path: str) -> Set[str]:
    """Lightweight scan of source files for import statements.
    Skips test/spec/docs directories to avoid picking up test tooling."""
    techs: Set[str] = set()
    skip = {"node_modules", ".git", "__pycache__", "venv", ".venv",
            "dist", "build", "target", ".gradle",
            "test", "tests", "spec", "specs", "__tests__",
            "e2e", "docs", "examples", "samples", "fixtures"}
    scanned = 0
    max_files = 50

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in skip]
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext not in _SOURCE_EXTENSIONS:
                continue
            if scanned >= max_files:
                return techs
            fpath = Path(root) / fname
            text = _read_text(fpath, max_bytes=64_000)
            if not text:
                continue
            scanned += 1
            imports_blob = ""
            for pattern in _IMPORT_PATTERNS.get(ext, []):
                matches = re.findall(pattern, text, re.MULTILINE)
                for m in matches:
                    if isinstance(m, tuple):
                        imports_blob += " " + " ".join(m)
                    else:
                        imports_blob += " " + m
            imports_lower = imports_blob.lower()
            for tech, keywords in TECH_KEYWORDS.items():
                if any(kw in imports_lower for kw in keywords):
                    techs.add(tech)
    return techs


# ── public API ──────────────────────────────────────────────────────────────


def detect(repo_path: str) -> Dict:
    """
    Scan *repo_path* and return a dict with:
      - technologies : set of detected tech names
      - components   : dict mapping component category → list of techs
      - files_scanned: list of config file names that were found
    """
    found_files = _find_target_files(repo_path)
    technologies: Set[str] = set()

    for fname, fpath in found_files.items():
        parser = _PARSERS.get(fname)
        if parser:
            text = _read_text(fpath)
            technologies |= parser(text)

    # GitHub Actions workflows
    gh_actions = _find_github_actions(repo_path)
    for wf in gh_actions:
        text = _read_text(wf)
        technologies |= _parse_cicd(text)

    # HTML templates
    template_files = _find_template_files(repo_path)
    if template_files:
        technologies |= _scan_templates(template_files)

    # Source-file imports
    technologies |= _scan_source_imports(repo_path)

    files_scanned = sorted(found_files.keys())
    if gh_actions:
        files_scanned.append(f".github/workflows/ ({len(gh_actions)} yml)")
    if template_files:
        files_scanned.append(f"templates/ ({len(template_files)} html)")

    components: Dict[str, List[str]] = {}
    for tech in sorted(technologies):
        category = COMPONENT_MAP.get(tech) or KB_PACKAGE_MAP.get(tech, "Other")
        components.setdefault(category, []).append(tech)

    return {
        "technologies": technologies,
        "components": components,
        "files_scanned": files_scanned,
    }
