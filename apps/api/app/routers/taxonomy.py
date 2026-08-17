"""Public taxonomy reference — sectors and career fields.

Served straight from the generated module (no DB round trip) with cache
headers: this data changes only when the taxonomy workbook is regenerated
and redeployed, so clients and the CDN may hold it for a day.
"""
from __future__ import annotations

from fastapi import APIRouter, Response

from app.util.taxonomy_api import TAXONOMY_AVAILABLE, sn_taxonomy

router = APIRouter(tags=["taxonomy"])


@router.get("/taxonomy")
async def get_taxonomy(response: Response) -> dict:
    if not TAXONOMY_AVAILABLE:
        return {"sectors": [], "fields": []}
    response.headers["Cache-Control"] = "public, max-age=86400"
    return {
        "sectors": [
            {"code": code, **{k: v for k, v in meta.items()}}
            for code, meta in sn_taxonomy.SECTORS.items()
        ],
        "fields": [
            {"code": code, "name": f["name"], "sectors": f["sectors"], "is_other": f["is_other"]}
            for code, f in sn_taxonomy.FIELDS.items()
        ],
    }
