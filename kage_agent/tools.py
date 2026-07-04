"""
KAGE — tool functions exposed to the agent.

ADK wraps plain Python functions as FunctionTools automatically when you pass
them into an Agent's `tools=[...]` list — it reads the docstring (Args/Returns)
to build the tool schema the model sees, so keep these Google-style and precise.
Each function is a discrete capability the agent can invoke. Keep them narrow
and single-purpose — that's what makes the agent's tool-use decisions legible
in the demo video (you can point at a log line and say "here it decided to
call X").
"""

import json
import re
from pathlib import Path

import requests

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{}"


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------

def parse_dependencies(file_path: str) -> dict:
    """Parses a requirements.txt or package.json file into a normalized dependency list.

    Args:
        file_path: Path to the manifest file (requirements.txt or package.json).

    Returns:
        A dict with "ecosystem" ("PyPI" or "npm") and "packages", a list of
        {"name": str, "version": str} objects. Contains "error" instead if
        the file doesn't exist.
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    if path.name == "package.json":
        data = json.loads(path.read_text())
        deps = {}
        deps.update(data.get("dependencies", {}))
        deps.update(data.get("devDependencies", {}))
        packages = []
        for name, version_spec in deps.items():
            # Strip range operators (^, ~, >=, etc.) to get a concrete-ish version
            version = re.sub(r"^[\^~>=<]+", "", version_spec).strip()
            packages.append({"name": name, "version": version})
        return {"ecosystem": "npm", "packages": packages}

    # Default: treat as requirements.txt style
    packages = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # name==version  /  name>=version  /  bare "name"
        match = re.match(r"^([A-Za-z0-9_.\-]+)\s*(==|>=|~=)?\s*([A-Za-z0-9_.\-]*)", line)
        if match:
            name, _, version = match.groups()
            packages.append({"name": name, "version": version or "unknown"})
    return {"ecosystem": "PyPI", "packages": packages}


# ---------------------------------------------------------------------------
# OSV.dev queries
# ---------------------------------------------------------------------------

def check_vulnerabilities(ecosystem: str, packages: list) -> dict:
    """Batch-queries OSV.dev for known vulnerabilities affecting a list of packages.

    Args:
        ecosystem: The package ecosystem, either "PyPI" or "npm".
        packages: List of {"name": str, "version": str} objects to check.

    Returns:
        A dict with "results": a list of {"name": str, "version": str,
        "vuln_ids": [str]} objects, one per input package. An empty
        "vuln_ids" list means no known vulnerabilities were found.
    """
    queries = [
        {
            "package": {"name": p["name"], "ecosystem": ecosystem},
            "version": p.get("version") if p.get("version") not in (None, "unknown") else None,
        }
        for p in packages
    ]
    # OSV rejects queries with version: None explicitly set weirdly — drop the key instead
    for q in queries:
        if q["version"] is None:
            del q["version"]

    resp = requests.post(OSV_BATCH_URL, json={"queries": queries}, timeout=30)
    resp.raise_for_status()
    raw_results = resp.json().get("results", [])

    out = []
    for pkg, result in zip(packages, raw_results):
        # Keep only top 2 vulns per package for the demo to avoid API rate limits
        vuln_ids = [v["id"] for v in result.get("vulns", [])][:2]
        out.append({"name": pkg["name"], "version": pkg.get("version", "unknown"), "vuln_ids": vuln_ids})
    return {"results": out}


import time

def get_vulnerability_details(vuln_id: str) -> dict:
    """Fetches full severity and summary details for a single OSV vulnerability ID.

    Args:
        vuln_id: An OSV vulnerability identifier, e.g. "GHSA-xxxx" or "PYSEC-xxxx",
            as returned by check_vulnerabilities.

    Returns:
        A dict with "id", "summary", "severity" (CVSS score if available),
        "aliases" (e.g. matching CVE IDs), and "published" date.
    """
    time.sleep(4) # Throttle LLM requests to stay within 15 RPM free tier limit
    resp = requests.get(OSV_VULN_URL.format(vuln_id), timeout=15)
    if resp.status_code != 200:
        return {"id": vuln_id, "error": f"status {resp.status_code}"}
    data = resp.json()

    severity = "UNKNOWN"
    for sev in data.get("severity", []):
        if sev.get("type") == "CVSS_V3":
            severity = sev.get("score", "UNKNOWN")

    return {
        "id": vuln_id,
        "summary": data.get("summary", "")[:300],
        "severity": severity,
        "aliases": data.get("aliases", []),
        "published": data.get("published", ""),
    }
import ast
import os

PACKAGE_TO_IMPORT_NAME = {
    "pyyaml": "yaml",
    "pillow": "PIL",
    "beautifulsoup4": "bs4",
    "python-dotenv": "dotenv",
    "scikit-learn": "sklearn",
    "opencv-python": "cv2",
}

# Directories to skip during usage analysis — virtual environments, VCS,
# caches, and WARDEN's own agent code (to avoid false positives from
# warden_agent/tools.py importing packages like `requests`).
_SKIP_DIRS = {"venv", ".venv", ".git", "__pycache__", "node_modules",
              "warden_agent", ".tox", ".mypy_cache", ".pytest_cache"}

# Maximum file size (bytes) to attempt parsing — skip anything larger to
# avoid hanging on generated or vendored mega-files.
_MAX_FILE_SIZE = 1_000_000  # 1 MB

def analyze_usage(package_name: str, source_dir: str = ".") -> dict:
    """Checks whether a package is imported and actively used in a project's source code.

    Uses Python's ast module to safely parse .py files and detect import
    statements and subsequent name references. Does NOT perform true call-graph
    or taint analysis — this is usage analysis, not reachability analysis.

    Args:
        package_name: The name of the package as declared in the manifest
            (e.g. "pyyaml", "pillow"). Automatically mapped to the correct
            Python import name via an internal lookup table.
        source_dir: The root directory of the project source to scan for
            .py files. Defaults to ".".

    Returns:
        A dict with "package" (original name), "import_name" (resolved Python
        import name), "found_in_files" (list of paths where imports were
        detected), "actively_used" (bool — True if the imported name is
        referenced beyond the import statement itself), "not_found" (bool —
        True if the package is never imported anywhere), and "skipped_files"
        (count of .py files that could not be parsed). Contains "error"
        instead if source_dir does not exist.
    """
    import_name = PACKAGE_TO_IMPORT_NAME.get(package_name.lower(), package_name)

    # Validate source_dir exists
    if not os.path.isdir(source_dir):
        return {
            "package": package_name,
            "import_name": import_name,
            "error": f"Source directory not found: {source_dir}",
        }

    found_in_files = []
    actively_used = False
    skipped_files = 0

    for root, dirs, files in os.walk(source_dir):
        # In-place mutation prevents os.walk from descending into skipped dirs
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for file in files:
            if not file.endswith(".py"):
                continue

            filepath = os.path.join(root, file)

            # Skip files that are too large (likely generated/vendored)
            try:
                if os.path.getsize(filepath) > _MAX_FILE_SIZE:
                    skipped_files += 1
                    continue
            except OSError:
                skipped_files += 1
                continue

            # Read and parse — use utf-8-sig to transparently strip BOM
            try:
                with open(filepath, "r", encoding="utf-8-sig") as f:
                    content = f.read()
                tree = ast.parse(content)
            except Exception:
                skipped_files += 1
                continue

            file_imports = set()
            imported = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] == import_name:
                            imported = True
                            file_imports.add(alias.asname or alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split(".")[0] == import_name:
                        imported = True
                        for alias in node.names:
                            file_imports.add(alias.asname or alias.name)

            if imported:
                found_in_files.append(filepath.replace("\\", "/"))

                # Check for active usage — any ast.Name in Load context
                # that matches an imported symbol
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name):
                        if node.id in file_imports:
                            if isinstance(node.ctx, ast.Load):
                                actively_used = True

    return {
        "package": package_name,
        "import_name": import_name,
        "found_in_files": found_in_files,
        "actively_used": actively_used,
        "not_found": len(found_in_files) == 0,
        "skipped_files": skipped_files,
    }

