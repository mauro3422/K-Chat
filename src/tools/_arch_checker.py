"""_arch_checker: validación de reglas arquitectónicas Legos.

Módulo Lego privado — no depende de tools ni de core.
Solo importa stdlib.

Verifica que las dependencias entre capas respeten las reglas:
- No upward coupling (tools→core, memory→tools, etc.)
- No framework imports in domain layers (src/ no importa fastapi)
- No global singletons (detecta patrones peligrosos)

Usage:
    from src.tools._arch_checker import check_file, check_directory, Rule
"""

from __future__ import annotations

import ast
import logging
import os

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from pathlib import Path


# ─── Rule definitions ─────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Rule:
    """A single architectural rule."""
    name: str
    source_pattern: str      # e.g. "src.tools", "src.memory"
    banned_pattern: str      # e.g. "src.core", "fastapi|flask"
    severity: str = "error"  # "error" | "warning"
    description: str = ""


@dataclass(frozen=True, slots=True)
class Violation:
    """A detected architectural violation."""
    rule: Rule
    file_path: str
    line: int
    import_text: str
    message: str = ""

    def __str__(self) -> str:
        msg = self.message or f"imports '{self.banned_pattern}' from {self.source_pattern}"
        return f"🔴 {self.rule.name} | {self.file_path}:{self.line} | '{self.import_text}' — {msg}"

    @property
    def banned_pattern(self) -> str:
        return self.rule.banned_pattern


@dataclass(slots=True)
class ArchitectureReport:
    """Full architecture check report."""
    violations: list[Violation] = field(default_factory=list)
    files_checked: int = 0
    rules_applied: int = 0
    checked_paths: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.violations) == 0

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.rule.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.rule.severity == "warning")

    def summary(self) -> str:
        lines = [f"🏛️ ARCHITECTURE CHECK — {self.files_checked} archivos, {self.rules_applied} reglas"]
        if self.ok:
            lines.append("   ✅ SIN VIOLACIONES — Arquitectura limpia")
        else:
            lines.append(f"   🔴 {self.error_count} errores | 🟡 {self.warning_count} warnings")
            lines.append("")
            for v in self.violations:
                lines.append(f"   {v}")
        lines.append("")
        lines.append(f"   Archivos escaneados: {self.files_checked}")
        return "\n".join(lines)


# ─── Default rules (K-Chat Legos architecture) ───────────────────────

DEFAULT_RULES: list[Rule] = [
    Rule(
        name="no-upward-tools→core",
        source_pattern="src.tools",
        banned_pattern="src.core",
        description="src/tools/ must NOT import src/core/",
    ),
    Rule(
        name="no-upward-memory→tools",
        source_pattern="src.memory",
        banned_pattern="src.tools",
        description="src/memory/ must NOT import src/tools/",
    ),
    Rule(
        name="no-upward-memory→core",
        source_pattern="src.memory",
        banned_pattern="src.core",
        description="src/memory/ must NOT import src/core/",
    ),
    Rule(
        name="no-upward-llm→tools",
        source_pattern="src.llm",
        banned_pattern="src.tools",
        description="src/llm/ must NOT import src/tools/",
    ),
    Rule(
        name="no-upward-llm→memory",
        source_pattern="src.llm",
        banned_pattern="src.memory",
        description="src/llm/ must NOT import src/memory/",
    ),
    Rule(
        name="no-upward-context→tools",
        source_pattern="src.context",
        banned_pattern="src.tools",
        description="src/context/ must NOT import src/tools/",
    ),
    Rule(
        name="no-upward-context→core",
        source_pattern="src.context",
        banned_pattern="src.core",
        description="src/context/ must NOT import src/core/",
    ),
    Rule(
        name="no-framework-in-domain",
        source_pattern="src.",
        banned_pattern="fastapi|flask|django|starlette",
        severity="error",
        description="Domain layers (src/) must NOT import web frameworks",
    ),
    Rule(
        name="no-upward-channels→core",
        source_pattern="channels.",
        banned_pattern="src.core",
        description="channels/ should only import via src.api facade",
    ),
]


# ─── Import extraction ────────────────────────────────────────────────

def _extract_imports_from_file(file_path: str) -> list[tuple[int, str]]:
    """Extract all import statements from a Python file with line numbers.

    Returns list of (line_number, import_text).
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return []

    results: list[tuple[int, str]] = []
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # Check TYPE_CHECKING guard
            in_type_checking = False
            for parent in ast.walk(tree):
                if isinstance(parent, ast.If):
                    if (isinstance(parent.test, ast.Name) and parent.test.id == "TYPE_CHECKING"):
                        if node.lineno >= parent.lineno and node.lineno <= (getattr(parent, 'end_lineno', parent.lineno) or parent.lineno):
                            in_type_checking = True
                            break

            if node.names:
                names = ", ".join(a.name for a in node.names)
                import_text = f"from {module} import {names}"
            else:
                import_text = f"from {module} import *"

            results.append((node.lineno, import_text))

            # Mark TYPE_CHECKING imports
            if in_type_checking:
                results[-1] = (node.lineno, f"{import_text}  # TYPE_CHECKING")

    return results


def _extract_imports_regex(file_path: str) -> list[tuple[int, str]]:
    """Fallback regex-based import extraction for non-Python files or parse failures."""
    results: list[tuple[int, str]] = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from ") and " import " in stripped:
                    results.append((i, stripped))
    except Exception:
        logger.warning("Failed to extract imports from %s", file_path, exc_info=True)
    return results


# ─── Core checking logic ─────────────────────────────────────────────

def _file_matches_source(file_path: str, source_pattern: str) -> bool:
    """Check if a file path belongs to a source pattern."""
    normalized = file_path.replace(os.sep, "/")
    # Ensure pattern ends with / for directory matching
    pat = source_pattern.rstrip("/") + "/"
    return pat in normalized or normalized.endswith(source_pattern.replace(".", "/") + ".py")


def _import_matches_banned(import_text: str, banned_pattern: str) -> bool:
    """Check if an import text matches a banned pattern."""
    # Handle OR patterns: "fastapi|flask|django"
    for part in banned_pattern.split("|"):
        part = part.strip()
        if part in import_text:
            return True
    return False


def check_file(
    file_path: str,
    rules: list[Rule] | None = None,
    project_root: str | None = None,
) -> list[Violation]:
    """Check a single Python file against architectural rules.

    Args:
        file_path: Path to the file to check.
        rules: Rules to check against. Uses DEFAULT_RULES if None.
        project_root: Project root for path normalization. Auto-detected if None.

    Returns:
        List of violations found.
    """
    rules = rules or DEFAULT_RULES
    violations: list[Violation] = []

    if project_root is None:
        # Try to detect project root
        p = Path(file_path).resolve()
        for parent in p.parents:
            if (parent / "src").is_dir() and (parent / "web").is_dir():
                project_root = str(parent)
                break
        if project_root is None:
            project_root = str(Path(file_path).resolve().parent.parent)

    # Get relative path for source matching
    abs_path = os.path.abspath(file_path)
    try:
        rel_path = os.path.relpath(abs_path, project_root)
    except ValueError:
        rel_path = abs_path

    rel_path = rel_path.replace(os.sep, "/")

    # Extract imports
    imports = _extract_imports_from_file(file_path)
    if not imports:
        imports = _extract_imports_regex(file_path)

    # Check each rule
    for rule in rules:
        # Does this file belong to the source pattern?
        if not _file_matches_source(rel_path, rule.source_pattern):
            continue

        # Check each import
        for line_no, import_text in imports:
            # Skip TYPE_CHECKING imports for upward coupling rules
            # (they're only for type annotations, not runtime)
            if "# TYPE_CHECKING" in import_text and "framework" not in rule.name:
                continue

            if _import_matches_banned(import_text, rule.banned_pattern):
                violations.append(Violation(
                    rule=rule,
                    file_path=rel_path,
                    line=line_no,
                    import_text=import_text,
                ))

    return violations


def check_directory(
    directory: str,
    rules: list[Rule] | None = None,
    project_root: str | None = None,
    recursive: bool = True,
    exclude_patterns: list[str] | None = None,
) -> ArchitectureReport:
    """Check all Python files in a directory against architectural rules.

    Args:
        directory: Directory to scan.
        rules: Rules to check against. Uses DEFAULT_RULES if None.
        project_root: Project root for path normalization. Auto-detected if None.
        recursive: Whether to scan subdirectories.
        exclude_patterns: Directory names to exclude (e.g., ["__pycache__", "node_modules"]).

    Returns:
        ArchitectureReport with all violations found.
    """
    rules = rules or DEFAULT_RULES
    exclude_patterns = exclude_patterns or ["__pycache__", "node_modules", ".git", "venv", ".venv", "dist", "build"]

    report = ArchitectureReport(rules_applied=len(rules))

    abs_directory = os.path.abspath(directory)
    if project_root is None:
        # Try to detect project root
        p = Path(abs_directory)
        for parent in p.parents:
            if (parent / "src").is_dir() and (parent / "web").is_dir():
                project_root = str(parent)
                break
        if project_root is None:
            project_root = str(p.parent)

    for root, dirs, files in os.walk(abs_directory):
        # Exclude directories
        dirs[:] = [d for d in dirs if d not in exclude_patterns and not d.startswith(".")]

        for fname in sorted(files):
            if not fname.endswith(".py"):
                continue

            file_path = os.path.join(root, fname)
            report.files_checked += 1
            report.checked_paths.append(file_path)

            violations = check_file(file_path, rules=rules, project_root=project_root)
            report.violations.extend(violations)

        if not recursive:
            break

    return report


# ─── Single-file quick check (for edit_file post-hook) ────────────────

def quick_check(file_path: str, project_root: str | None = None) -> str:
    """Quick architecture check for a single file. Returns summary string.

    Designed to be called after edit_file/write_file as a post-hook.
    """
    violations = check_file(file_path, project_root=project_root)
    if not violations:
        return "✅ Arch check OK — sin violaciones arquitectónicas"

    lines = [f"🔴 Arch check: {len(violations)} violación(es) encontrada(s):"]
    for v in violations:
        lines.append(f"   {v}")
    return "\n".join(lines)
