"""Packaged, buildless web interface served by the API application."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

ASSETS = Path(__file__).resolve().parent / "static"
router = APIRouter()


@router.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(ASSETS / "index.html")
