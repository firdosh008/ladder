"""Brands CRUD — PRD §8.2"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import user_client
from app.middleware.auth import current_user

router = APIRouter(prefix="/brands", tags=["brands"])


class BrandPayload(BaseModel):
    name: str
    primary_color: str | None = None
    secondary_color: str | None = None
    context_description: str | None = None


class BrandResponse(BaseModel):
    id: str
    name: str
    primary_color: str | None = None
    secondary_color: str | None = None
    context_description: str | None = None
    created_at: str | None = None


@router.get("", response_model=list[BrandResponse])
async def list_brands(ctx: tuple = Depends(current_user)) -> list[BrandResponse]:
    user_id, token = ctx
    client = await user_client(token)
    result = (
        await client.from_("brands")
        .select("id,name,primary_color,secondary_color,context_description,created_at")
        .eq("user_id", str(user_id))
        .order("name")
        .execute()
    )
    return [BrandResponse(**r) for r in (result.data or [])]


@router.post("", response_model=BrandResponse, status_code=201)
async def create_brand(
    payload: BrandPayload, ctx: tuple = Depends(current_user)
) -> BrandResponse:
    user_id, token = ctx
    client = await user_client(token)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Brand name is required")
    result = (
        await client.from_("brands")
        .insert({
            "user_id": str(user_id),
            "name": payload.name.strip(),
            "primary_color": payload.primary_color,
            "secondary_color": payload.secondary_color,
            "context_description": payload.context_description,
        })
        .execute()
    )
    row = result.data[0] if result.data else None
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create brand")
    return BrandResponse(**row)


@router.patch("/{brand_id}", response_model=BrandResponse)
async def update_brand(
    brand_id: str, payload: BrandPayload, ctx: tuple = Depends(current_user)
) -> BrandResponse:
    user_id, token = ctx
    client = await user_client(token)
    patch = {
        k: v for k, v in {
            "name": payload.name.strip() if payload.name else None,
            "primary_color": payload.primary_color,
            "secondary_color": payload.secondary_color,
            "context_description": payload.context_description,
        }.items() if v is not None
    }
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = (
        await client.from_("brands")
        .update(patch)
        .eq("id", brand_id)
        .eq("user_id", str(user_id))
        .execute()
    )
    row = result.data[0] if result.data else None
    if not row:
        raise HTTPException(status_code=404, detail="Brand not found")
    return BrandResponse(**row)


@router.delete("/{brand_id}", status_code=204)
async def delete_brand(
    brand_id: str, ctx: tuple = Depends(current_user)
) -> None:
    user_id, token = ctx
    client = await user_client(token)
    result = (
        await client.from_("brands")
        .delete()
        .eq("id", brand_id)
        .eq("user_id", str(user_id))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Brand not found")
