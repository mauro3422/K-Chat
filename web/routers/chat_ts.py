from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()

@router.get("/chat-ts", include_in_schema=False)
def get_chat_ts() -> RedirectResponse:
    return RedirectResponse(url="/", status_code=301)
