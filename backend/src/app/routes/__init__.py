"""Modular FastAPI API routers for the Best Buy Catalog Comparison Agent."""

from app.routes.compare import router as compare_router

__all__ = ["compare_router"]
