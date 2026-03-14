#!/usr/bin/env python3
"""
Build the technology knowledge base from public package registry APIs.

Usage:
    python build_knowledge_base.py

Fetches metadata for packages listed in data/seed_packages.json from
PyPI and npm, maps them to architectural categories, and writes the
result to data/knowledge_base.json.

Requires network access.  Run once; commit the output.
"""

import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SEED_PATH = Path(__file__).parent / "data" / "seed_packages.json"
OUTPUT_PATH = Path(__file__).parent / "data" / "knowledge_base.json"

# ── PyPI classifier → component category mapping ────────────────────────────

_PYPI_CLASSIFIER_MAP: Dict[str, str] = {
    # Frameworks
    "Framework :: Django":          "Backend",
    "Framework :: Flask":           "Backend",
    "Framework :: FastAPI":         "Backend",
    "Framework :: Pyramid":         "Backend",
    "Framework :: Bottle":          "Backend",
    "Framework :: Tornado":         "Backend",
    "Framework :: Twisted":         "Backend",
    "Framework :: aiohttp":         "Backend",
    "Framework :: Celery":          "Task Queue",
    "Framework :: Pytest":          "Testing",
    "Framework :: Sphinx":          "Documentation",
    "Framework :: Jupyter":         "AI/ML",
    # Topics
    "Topic :: Database":                               "Database",
    "Topic :: Database :: Front-Ends":                  "Database",
    "Topic :: Database :: Database Engines/Servers":    "Database",
    "Topic :: Internet :: WWW/HTTP":                    "Backend",
    "Topic :: Internet :: WWW/HTTP :: WSGI":            "Backend",
    "Topic :: Internet :: WWW/HTTP :: HTTP Servers":    "Backend",
    "Topic :: Internet :: WWW/HTTP :: Dynamic Content": "Backend",
    "Topic :: Scientific/Engineering":                              "AI/ML",
    "Topic :: Scientific/Engineering :: Artificial Intelligence":   "AI/ML",
    "Topic :: Scientific/Engineering :: Image Recognition":         "AI/ML",
    "Topic :: Scientific/Engineering :: Information Analysis":      "AI/ML",
    "Topic :: Software Development :: Libraries :: Python Modules": "Library",
    "Topic :: Software Development :: Testing":                     "Testing",
    "Topic :: System :: Systems Administration":                    "Infrastructure",
    "Topic :: System :: Monitoring":                                "Monitoring",
    "Topic :: Communications :: Email":                             "Email Service",
    "Topic :: Security":                                            "Security",
    "Topic :: Office/Business :: Financial":                        "Payments",
}

# Fallback keyword-based category detection for packages whose
# classifiers are too generic or missing.
_KEYWORD_CATEGORY_HINTS: Dict[str, str] = {
    "database":       "Database",
    "postgres":       "Database",
    "mysql":          "Database",
    "mongo":          "Database",
    "redis":          "Cache/Database",
    "elasticsearch":  "Search Engine",
    "opensearch":     "Search Engine",
    "orm":            "ORM",
    "sql":            "ORM",
    "auth":           "Backend",
    "jwt":            "Backend",
    "oauth":          "Authentication",
    "queue":          "Task Queue",
    "celery":         "Task Queue",
    "kafka":          "Message Broker",
    "rabbitmq":       "Message Broker",
    "amqp":           "Message Broker",
    "aws":            "Cloud Services",
    "gcp":            "Cloud Services",
    "google-cloud":   "Cloud Services",
    "azure":          "Cloud Services",
    "s3":             "Object Storage",
    "storage":        "Object Storage",
    "stripe":         "Payments",
    "payment":        "Payments",
    "email":          "Email Service",
    "smtp":           "Email Service",
    "sendgrid":       "Email Service",
    "sentry":         "Monitoring",
    "monitoring":     "Monitoring",
    "docker":         "Containerisation",
    "kubernetes":     "Orchestration",
    "k8s":            "Orchestration",
    "terraform":      "Infrastructure as Code",
    "serverless":     "Infrastructure as Code",
    "grpc":           "API Layer",
    "graphql":        "API Layer",
    "rest":           "API Layer",
    "websocket":      "API Layer",
    "scraping":       "Scraping",
    "crawler":        "Scraping",
    "frontend":       "Frontend",
    "react":          "Frontend",
    "vue":            "Frontend",
    "angular":        "Frontend",
    "svelte":         "Frontend",
    "css":            "Frontend",
    "ui":             "Frontend",
    "machine learning": "AI/ML",
    "deep learning":  "AI/ML",
    "neural":         "AI/ML",
    "nlp":            "AI/ML",
    "llm":            "AI/ML",
    "ai":             "AI/ML",
    "data science":   "AI/ML",
    "workflow":       "Task Queue",
    "cli":            "CLI Tool",
    "logging":        "Logging",
    "validation":     "Library",
    "testing":        "Testing",
    "test":           "Testing",
    "linter":         "Developer Tool",
    "formatter":      "Developer Tool",
    "bundler":        "Build Tool",
    "build":          "Build Tool",
}

# ── API fetchers ─────────────────────────────────────────────────────────────


def _fetch_json(url: str) -> Optional[Dict]:
    """GET a URL and return parsed JSON, or None on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "arch-diagram-gen/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        print(f"  Warning: failed to fetch {url}: {exc}")
        return None


def _fetch_pypi(package: str) -> Optional[Dict[str, Any]]:
    url = f"https://pypi.org/pypi/{package}/json"
    data = _fetch_json(url)
    if not data or "info" not in data:
        return None
    info = data["info"]
    return {
        "name": info.get("name", package),
        "summary": (info.get("summary") or "")[:200],
        "classifiers": info.get("classifiers") or [],
        "keywords": (info.get("keywords") or "").lower().split(","),
        "home_page": info.get("home_page") or info.get("project_url", ""),
    }


def _fetch_npm(package: str) -> Optional[Dict[str, Any]]:
    url = f"https://registry.npmjs.org/{package}"
    data = _fetch_json(url)
    if not data or "name" not in data:
        return None
    return {
        "name": data.get("name", package),
        "description": (data.get("description") or "")[:200],
        "keywords": [k.lower() for k in (data.get("keywords") or [])],
    }


# ── category resolution ─────────────────────────────────────────────────────


def _resolve_pypi_category(meta: Dict[str, Any]) -> str:
    """Determine component category from PyPI classifiers, then keywords."""
    for classifier in meta.get("classifiers", []):
        for prefix, category in _PYPI_CLASSIFIER_MAP.items():
            if classifier.startswith(prefix):
                return category
    return _category_from_keywords(
        meta.get("keywords", []) + [meta.get("summary", "").lower()]
    )


def _resolve_npm_category(meta: Dict[str, Any]) -> str:
    """Determine component category from npm keywords."""
    return _category_from_keywords(
        meta.get("keywords", []) + [meta.get("description", "").lower()]
    )


def _category_from_keywords(tokens: List[str]) -> str:
    blob = " ".join(t.strip() for t in tokens if t).lower()
    for hint, category in _KEYWORD_CATEGORY_HINTS.items():
        if hint in blob:
            return category
    return "Library"


# ── main build logic ─────────────────────────────────────────────────────────


def build() -> Dict[str, Dict[str, Any]]:
    if not SEED_PATH.exists():
        print(f"Error: seed file not found at {SEED_PATH}", file=sys.stderr)
        sys.exit(1)

    seeds = json.loads(SEED_PATH.read_text())
    kb: Dict[str, Dict[str, Any]] = {"pypi": {}, "npm": {}}

    # PyPI
    pypi_packages = seeds.get("pypi", [])
    print(f"Fetching {len(pypi_packages)} PyPI packages...")
    for i, pkg in enumerate(pypi_packages):
        meta = _fetch_pypi(pkg)
        if meta:
            category = _resolve_pypi_category(meta)
            kb["pypi"][pkg] = {
                "name": meta["name"],
                "category": category,
                "keywords": [pkg, meta["name"].lower()],
            }
            print(f"  [{i+1}/{len(pypi_packages)}] {pkg} -> {category}")
        else:
            print(f"  [{i+1}/{len(pypi_packages)}] {pkg} -> SKIPPED (fetch failed)")
        time.sleep(0.1)

    # npm
    npm_packages = seeds.get("npm", [])
    print(f"\nFetching {len(npm_packages)} npm packages...")
    for i, pkg in enumerate(npm_packages):
        meta = _fetch_npm(pkg)
        if meta:
            category = _resolve_npm_category(meta)
            kb["npm"][pkg] = {
                "name": meta["name"],
                "category": category,
                "keywords": [pkg] + meta.get("keywords", [])[:5],
            }
            print(f"  [{i+1}/{len(npm_packages)}] {pkg} -> {category}")
        else:
            print(f"  [{i+1}/{len(npm_packages)}] {pkg} -> SKIPPED (fetch failed)")
        time.sleep(0.1)

    return kb


def main() -> None:
    kb = build()

    pypi_count = len(kb.get("pypi", {}))
    npm_count = len(kb.get("npm", {}))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(kb, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\nKnowledge base written to {OUTPUT_PATH}")
    print(f"  PyPI : {pypi_count} packages")
    print(f"  npm  : {npm_count} packages")
    print(f"  Total: {pypi_count + npm_count} packages")


if __name__ == "__main__":
    main()
