"""Backward-compat facade. New code should import from submodules directly."""
import src.llm.models as models  # noqa: F401 — kept for test patches like @patch("src.llm.policy.models.*")
from src.llm.discovery import get_models, get_free_models, get_verified_models
from src.llm.verifier import verify_model
from src.llm.selector import get_default_model
from src.llm.failover import _mark_and_refresh
