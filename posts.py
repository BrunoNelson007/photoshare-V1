"""
Posts router
"""
import uuid, io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from PIL import Image

from config import get_settings
from security import limiter, require_creator, require_consumer_or_creator, sanitise
from schemas import PostCreate, PostOut, PostSummary, PaginatedPosts
from azure_clients import get_blob_container, get_container, analyse_image_url

router = APIRouter(prefix="/posts", tags=["posts"])
settings = get_settings()

MAX_BYTES = settings.max_upload_size_mb * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _validate_image(data: bytes, content_type: str) -> bytes:
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Unsupported image type")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"File exceeds {settings.max_upload_size_mb} MB limit")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
        buf = io.BytesIO()
        fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP", "image/gif": "GIF"}.get(content_type, "JPEG")
        img.save(buf, format=fmt)
        return buf.getvalue()
    except Exception as exc:
        raise HTTPException(400, f"Invalid image: {exc}")


from azure.storage.blob import ContentSettings

async def _upload_blob(data: bytes, blob_name: str, content_type: str) -> str:
    container = get_blob_container()
    blob_client = container.get_blob_client(blob_name)
    await blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type)
    )
    return blob_client.url


async def _get_post_or_404(post_id: str) -> dict:
    try:
        return await get_container("posts").read_item(item=post_id, partition_key=post_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Post not found")


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_post(
    request: Request,
    title: str = Form(...),
    caption: str = Form(default=""),
    location: str = Form(default=""),
    people_present: str = Form(default=""),
    photo: UploadFile = File(...),
    user: dict = Depends(require_creator),
):
    raw = await photo.read()
    clean_bytes = _validate_image(raw, photo.content_type or "image/jpeg")
    title = sanitise(title, 120)
    caption = sanitise(caption, 500)
    location = sanitise(location, 120)
    people = [sanitise(p.strip(), 80) for p in people_present.split(",") if p.strip()]

    post_id = str(uuid.uuid4())
    ext = (photo.filename or "photo.jpg").rsplit(".", 1)[-1].lower()
    blob_name = f"{user['sub']}/{post_id}.{ext}"
    blob_url = await _upload_blob(clean_bytes, blob_name, photo.content_type or "image/jpeg")

    auto_tags = await analyse_image_url(blob_url)

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": post_id,
        "creator_id": user["sub"],
        "creator_name": user.get("name", "Unknown"),
        "title": title,
        "caption": caption,
        "location": location,
        "people_present": people,
        "blob_url": blob_url,
        "auto_tags": auto_tags,
        "avg_rating": 0.0,
        "rating_count": 0,
        "created_at": now,
    }
    await get_container("posts").upsert_item(doc)
    return {**doc, "created_at": datetime.fromisoformat(now)}


@router.get("", response_model=PaginatedPosts)
@limiter.limit("60/minute")
async def list_posts(
    request: Request,
    q: str | None = Query(default=None),
    location: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _user: dict = Depends(require_consumer_or_creator),
):
    offset = (page - 1) * page_size
    conditions, params = [], []

    if q:
        conditions.append("(CONTAINS(LOWER(c.title), LOWER(@q)) OR CONTAINS(LOWER(c.caption), LOWER(@q)) OR ARRAY_CONTAINS(c.auto_tags, @q, true))")
        params.append({"name": "@q", "value": sanitise(q, 100)})
    if location:
        conditions.append("CONTAINS(LOWER(c.location), LOWER(@loc))")
        params.append({"name": "@loc", "value": sanitise(location, 120)})
    if tag:
        conditions.append("ARRAY_CONTAINS(c.auto_tags, @tag)")
        params.append({"name": "@tag", "value": sanitise(tag, 80)})

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"SELECT c.id, c.title, c.blob_url, c.auto_tags, c.avg_rating, c.creator_name, c.created_at FROM c {where} ORDER BY c._ts DESC OFFSET {offset} LIMIT {page_size}"
    count_query = f"SELECT VALUE COUNT(1) FROM c {where}"

    container = get_container("posts")
    items = [item async for item in container.query_items(query=query, parameters=params)]
    totals = [t async for t in container.query_items(query=count_query, parameters=params)]
    total = totals[0] if totals else 0

    for item in items:
        item["created_at"] = datetime.fromisoformat(item["created_at"])
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/{post_id}", response_model=PostOut)
@limiter.limit("120/minute")
async def get_post(request: Request, post_id: str, _user: dict = Depends(require_consumer_or_creator)):
    doc = await _get_post_or_404(post_id)
    doc["created_at"] = datetime.fromisoformat(doc["created_at"])
    return doc


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_post(request: Request, post_id: str, user: dict = Depends(require_creator)):
    doc = await _get_post_or_404(post_id)
    if doc["creator_id"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Cannot delete another creator's post")
    try:
        container_client = get_blob_container()
        blob_name = doc["blob_url"].split(f"{settings.storage_container}/")[-1]
        await container_client.delete_blob(blob_name)
    except Exception:
        pass
    await get_container("posts").delete_item(item=post_id, partition_key=post_id)
