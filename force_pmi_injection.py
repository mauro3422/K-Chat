"""Compatibility wrapper for the PMI graph population script."""

from scripts.populate_pmi_graph import *  # noqa: F401,F403
from scripts.populate_pmi_graph import main


if __name__ == "__main__":
    raise SystemExit(main())
