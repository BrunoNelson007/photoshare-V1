"""
Comments router
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from security import limiter, require_consumer_or_creator, sanitise
from schemas import CommentCreate, CommentOut
from azure_clients import get_container, analyse_sentiment

router = APIRouter(tags=["comments"])


@router.post("/posts/{post_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def add_comment(request: Request, post_id: str, body: CommentCreate, user: dict = Depends(require_consumer_or_creator)):
    try:
        await get_container("posts").read_item(item=post_id, partition_key=post_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Post not found")

    clean_text = sanitise(body.text, 500)
    sentiment_label, sentiment_score = await analyse_sentiment(clean_text)

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "post_id": post_id,
        "user_id": user["sub"],
        "user_name": user.get("name", "Anonymous"),
        "text": clean_text,
        "sentiment": sentiment_label,
        "sentiment_score": sentiment_score,
        "created_at": now,
    }
    await get_container("comments").upsert_item(doc)
    doc["created_at"] = datetime.fromisoformat(now)
    return doc


@router.get("/posts/{post_id}/comments", response_model=list[CommentOut])
@limiter.limit("60/minute")
async def list_comments(request: Request, post_id: str, _user: dict = Depends(require_consumer_or_creator)):
    items = [
        item async for item in get_container("comments").query_items(
            query="SELECT * FROM c WHERE c.post_id = @post_id ORDER BY c._ts DESC",
            parameters=[{"name": "@post_id", "value": post_id}],
        )
    ]
    for item in items:
        item["created_at"] = datetime.fromisoformat(item["created_at"])
    return items


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_comment(request: Request, comment_id: str, user: dict = Depends(require_consumer_or_creator)):
    container = get_container("comments")
    items = [item async for item in container.query_items(
        query="SELECT * FROM c WHERE c.id = @id",
        parameters=[{"name": "@id", "value": comment_id}],
    )]
    if not items:
        raise HTTPException(status_code=404, detail="Comment not found")
    doc = items[0]
    if doc["user_id"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Cannot delete another user's comment")
    await container.delete_item(item=comment_id, partition_key=doc["post_id"])
