"""
Ratings router
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from security import limiter, require_consumer_or_creator
from schemas import RatingCreate, RatingOut
from azure_clients import get_container

router = APIRouter(tags=["ratings"])


async def _recalculate_avg(post_id: str):
    params = [{"name": "@pid", "value": post_id}]
    ratings_ctr = get_container("ratings")
    avgs   = [v async for v in ratings_ctr.query_items(query="SELECT VALUE AVG(c.score) FROM c WHERE c.post_id = @pid", parameters=params)]
    counts = [v async for v in ratings_ctr.query_items(query="SELECT VALUE COUNT(1) FROM c WHERE c.post_id = @pid", parameters=params)]
    avg   = round(avgs[0], 2) if avgs and avgs[0] is not None else 0.0
    count = counts[0] if counts else 0
    try:
        post = await get_container("posts").read_item(item=post_id, partition_key=post_id)
        post["avg_rating"]   = avg
        post["rating_count"] = count
        await get_container("posts").replace_item(item=post_id, body=post)
    except Exception:
        pass


@router.post("/posts/{post_id}/rate", response_model=RatingOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def rate_post(request: Request, post_id: str, body: RatingCreate, user: dict = Depends(require_consumer_or_creator)):
    try:
        post = await get_container("posts").read_item(item=post_id, partition_key=post_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Post not found")
    if post["creator_id"] == user["sub"]:
        raise HTTPException(status_code=400, detail="Cannot rate your own post")

    ratings_ctr = get_container("ratings")
    existing = [item async for item in ratings_ctr.query_items(
        query="SELECT * FROM c WHERE c.post_id = @pid AND c.user_id = @uid",
        parameters=[{"name": "@pid", "value": post_id}, {"name": "@uid", "value": user["sub"]}],
    )]

    now = datetime.now(timezone.utc).isoformat()
    if existing:
        doc = existing[0]
        doc["score"] = body.score
        doc["created_at"] = now
        await ratings_ctr.replace_item(item=doc["id"], body=doc)
    else:
        doc = {"id": str(uuid.uuid4()), "post_id": post_id, "user_id": user["sub"], "score": body.score, "created_at": now}
        await ratings_ctr.upsert_item(doc)

    await _recalculate_avg(post_id)
    doc["created_at"] = datetime.fromisoformat(now)
    return doc


@router.get("/posts/{post_id}/rating")
@limiter.limit("120/minute")
async def get_rating(request: Request, post_id: str, _user: dict = Depends(require_consumer_or_creator)):
    try:
        post = await get_container("posts").read_item(item=post_id, partition_key=post_id)
        return {"post_id": post_id, "avg_rating": post.get("avg_rating", 0.0), "rating_count": post.get("rating_count", 0)}
    except Exception:
        raise HTTPException(status_code=404, detail="Post not found")
