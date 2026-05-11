from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    email: Optional[str] = ""
    display_name: str = Field(..., min_length=2, max_length=80)
    role: str = Field(default="consumer", pattern="^(creator|consumer)$")

class UserCreate(UserBase):
    pass

class UserOut(UserBase):
    id: str
    created_at: datetime
    class Config:
        from_attributes = True


class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    caption: str = Field(default="", max_length=500)
    location: str = Field(default="", max_length=120)
    people_present: list[str] = Field(default_factory=list)

class PostOut(BaseModel):
    id: str
    creator_id: str
    creator_name: str
    title: str
    caption: str
    location: str
    people_present: list[str]
    blob_url: str
    auto_tags: list[str]
    avg_rating: float
    rating_count: int
    created_at: datetime

class PostSummary(BaseModel):
    id: str
    title: str
    blob_url: str
    auto_tags: list[str]
    avg_rating: float
    creator_name: str
    created_at: datetime

class PaginatedPosts(BaseModel):
    items: list[PostSummary]
    page: int
    page_size: int
    total: int


class CommentCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)

class CommentOut(BaseModel):
    id: str
    post_id: str
    user_id: str
    user_name: str
    text: str
    sentiment: str
    sentiment_score: float
    created_at: datetime


class RatingCreate(BaseModel):
    score: int = Field(..., ge=1, le=5)

class RatingOut(BaseModel):
    id: str
    post_id: str
    user_id: str
    score: int
    created_at: datetime


class MessageResponse(BaseModel):
    message: str
