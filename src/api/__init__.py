"""Compatibilidad mínima para `src.api`.

Los consumidores nuevos deben importar submódulos concretos como
`src.api.orchestrator`, `src.api.repos`, `src.api.llm_client`, etc.
"""

from src.api.repos import get_repos

__all__ = ["get_repos"]
