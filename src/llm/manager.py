import logging
from concurrent.futures import ThreadPoolExecutor
from src.llm import models

logger = logging.getLogger(__name__)

def verify_model(model_id: str) -> bool:
    """Prueba si un modelo responde correctamente enviando un mensaje ultracorto."""
    try:
        models._api_call(
            model=model_id,
            messages=[{"role": "user", "content": "hola"}],
            max_tokens=2,
            timeout=2.0
        )
        return True
    except Exception as e:
        logger.warning("Modelo %s no pasó la verificación: %s", model_id, e)
        return False

def get_verified_models(force_refresh: bool = False) -> list:
    """Devuelve la lista de modelos gratuitos que están activos y funcionando."""
    if models._verified_models is None or force_refresh:
        try:
            free_models = get_free_models(force_refresh=force_refresh)
            verified = []

            def check(model_id: str):
                if verify_model(model_id):
                    return model_id
                return None

            with ThreadPoolExecutor(max_workers=max(1, len(free_models))) as executor:
                results = executor.map(check, [m.id for m in free_models])
                for res in results:
                    if res:
                        verified.append(res)
            models._verified_models = verified
        except Exception as e:
            logger.error("Error verificando modelos: %s", e)
            if models._verified_models is not None:
                return models._verified_models
            models._verified_models = [models.FALLBACK_MODEL]
    return models._verified_models

def get_models(force_refresh: bool = False):
    """Devuelve todos los modelos disponibles desde la API (con caché en memoria)."""
    if models._cached_models is None or force_refresh:
        try:
            models._cached_models = list(models.client.models.list())
        except Exception as e:
            logger.error("Error al obtener modelos de la API: %s", e)
            if models._cached_models is not None:
                return models._cached_models
            raise e
    return models._cached_models

def get_free_models(force_refresh: bool = False):
    """Devuelve solo los modelos gratuitos (IDs que terminan en -free)."""
    all_models = get_models(force_refresh=force_refresh)
    return [model for model in all_models if model.id.endswith("-free")]

def get_paid_models(force_refresh: bool = False):
    """Devuelve los modelos de pago."""
    all_models = get_models(force_refresh=force_refresh)
    return [model for model in all_models if not model.id.endswith("-free")]

def get_default_model():
    """Elige el primer modelo de PRIORITY que esté disponible y no haya fallado. Si la API no responde, usa el fallback."""
    try:
        free_ids = [m.id for m in get_free_models()]
        for modelo in models.PRIORITY:
            if modelo not in models._failed_models:
                if modelo in free_ids or modelo == "big-pickle":
                    return modelo
    except Exception as e:
        logger.warning("Error obteniendo modelos: %s", e)
    return models.FALLBACK_MODEL

def _mark_and_refresh(model: str) -> str:
    """Marca modelo como fallido, refresca lista verificada y devuelve el modelo alternativo."""
    try:
        get_verified_models(force_refresh=True)
    except Exception:
        pass
    models._failed_models.add(model)
    next_model = models._switch_model(model)
    return next_model
