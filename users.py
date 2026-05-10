"""
Users router
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from security import limiter, get_current_user, require_consumer_or_creator
from schemas import UserOut
from azure_clients import get_container

router = APIRouter(prefix="/users", tags=["users"])


async def _sync_user(user_claims: dict) -> dict:
    from config import get_settings
    settings = get_settings()
    user_id    = user_claims["sub"]
    role_claim = f"https://{settings.auth0_domain}/role"
    container  = get_container("users")
    try:
        return await container.read_item(item=user_id, partition_key=user_id)
    except Exception:
        pass
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id":           user_id,
        "email":        user_claims.get("email", ""),
        "display_name": user_claims.get("name", user_claims.get("nickname", "User")),
        "role":         user_claims.get(role_claim, "consumer"),
        "created_at":   now,
    }
    await container.upsert_item(doc)
    return doc


@router.get("/me", response_model=UserOut)
@limiter.limit("60/minute")
async def get_me(request: Request, user: dict = Depends(get_current_user)):
    doc = await _sync_user(user)
    doc["created_at"] = datetime.fromisoformat(doc["created_at"])
    return doc


@router.get("/{user_id}", response_model=UserOut)
@limiter.limit("60/minute")
async def get_user(request: Request, user_id: str, _user: dict = Depends(require_consumer_or_creator)):
    try:
        doc = await get_container("users").read_item(item=user_id, partition_key=user_id)
        doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        return doc
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")
