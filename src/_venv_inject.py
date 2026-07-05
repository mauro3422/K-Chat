"""Inject the project venv's site-packages into sys.path.

Call ``ensure_venv()`` at the top of any entry point, test file, or
package ``__init__`` to make sure the project's virtual environment
is available regardless of which Python interpreter is used.

This allows transparent access to packages like ``fastembed``,
``networkx``, and ``sqlite_vec`` that are installed in the project
venv but not in the system Python.

Usage::

    from src._venv_inject import ensure_venv
    ensure_venv()

The function is idempotent — calling it multiple times is safe.
"""

from __future__ import annotations

import site
import sys
from pathlib import Path

__all__ = ["ensure_venv"]

_VENV_INJECTED: bool = False


def ensure_venv() -> None:
    """Find the project venv and add its site-packages to ``sys.path``.

    Searches upward from the caller's file (or from ``src/_venv_inject.py``)
    for a ``venv/`` directory containing a Python binary, then computes the
    corresponding ``site-packages`` path and prepends it to ``sys.path``.
    """
    global _VENV_INJECTED
    if _VENV_INJECTED:
        return

    # Locate the project root: walk up from this file's location
    root = Path(__file__).resolve().parent.parent

    venv_python = root / "venv" / "bin" / "python3"
    if not venv_python.exists():
        # No venv found — nothing to inject
        _VENV_INJECTED = True
        return

    # If we're already running from the venv, no injection needed
    if sys.executable.startswith(str(venv_python)[:-1]):
        _VENV_INJECTED = True
        return

    # Compute site-packages path from the venv Python version
    import subprocess  # noqa: S404

    try:
        version = (
            subprocess.run(
                [str(venv_python), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            .stdout.strip()
        )
    except Exception:
        version = f"{sys.version_info.major}.{sys.version_info.minor}"

    site_packages = root / "venv" / "lib" / f"python{version}" / "site-packages"
    if site_packages.exists() and str(site_packages) not in sys.path:
        sys.path.insert(0, str(site_packages))
        # Also run site.addsitedir so .pth files in the venv are processed
        try:
            site.addsitedir(str(site_packages))
        except Exception:
            pass

    _VENV_INJECTED = True
