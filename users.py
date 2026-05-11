"""
Users router
"""
import httpx
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from config import get_settings
from security import limiter, get_current_user, require_consumer_or_creator
from schemas import UserOut
from azure_clients import get_container

router = APIRouter(prefix="/users", tags=["users"])


async def _sync_user(user_claims: dict) -> dict:
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


class RoleUpdate(BaseModel):
    role: str


@router.post("/set-role")
@limiter.limit("5/minute")
async def set_role(
    request: Request,
    body: RoleUpdate,
    user: dict = Depends(get_current_user)
):
    """
    Called once after signup to persist the role chosen on signup.html.
    Updates both Cosmos DB and Auth0 app_metadata.
    """
    settings = get_settings()

    if body.role not in ("creator", "consumer"):
        raise HTTPException(status_code=400, detail="Invalid role")

    user_id = user["sub"]

    # 1. Update Cosmos DB
    container = get_container("users")
    try:
        doc = await container.read_item(item=user_id, partition_key=user_id)
    except Exception:
        doc = await _sync_user(user)

    doc["role"] = body.role
    await container.upsert_item(doc)

    # 2. Update Auth0 app_metadata via Management API
    try:
        # Get Management API token
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                f"https://{settings.auth0_domain}/oauth/token",
                json={
                    "client_id":     settings.auth0_client_id,
                    "client_secret": settings.auth0_client_secret,
                    "audience":      f"https://{settings.auth0_domain}/api/v2/",
                    "grant_type":    "client_credentials",
                }
            )
            mgmt_token = token_resp.json().get("access_token")

            if mgmt_token:
                await client.patch(
                    f"https://{settings.auth0_domain}/api/v2/users/{user_id}",
                    headers={"Authorization": f"Bearer {mgmt_token}"},
                    json={"app_metadata": {"role": body.role}}
                )
    except Exception as e:
        print(f"[Auth0] app_metadata update failed: {e}")
        # Non-fatal — Cosmos DB is updated, role will work on next login

    return {"message": "Role updated", "role": body.role}


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
