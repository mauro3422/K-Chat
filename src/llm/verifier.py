import logging

import src.llm.api_call as api_call

logger: logging.Logger = logging.getLogger(__name__)


async def verify_model(model_id: str) -> bool:
    """Tests if a model responds correctly by sending an ultra-short message."""
    try:
        await api_call._api_call(
            model=model_id,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=2,
            timeout=2.0,
        )
        return True
    except Exception as e:
        logger.warning("Model %s failed verification: %s", model_id, e)
        return False
