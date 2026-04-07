from fastapi import APIRouter

router = APIRouter(prefix="/products", tags=["products"])

PRODUCT_CATEGORIES = [
    {"category": "health", "examples": ["calorie tracker", "water intake logger", "workout log", "sleep tracker"]},
    {"category": "finance", "examples": ["budget tracker", "savings goal", "bill reminder", "net worth calculator"]},
    {"category": "productivity", "examples": ["pomodoro timer", "habit tracker", "daily planner", "note-taking app"]},
    {"category": "business", "examples": ["contact manager", "invoice generator", "project tracker", "time tracker"]},
    {"category": "entertainment", "examples": ["movie watchlist", "recipe box", "book tracker", "travel bucket list"]},
]

@router.get("/")
def list_categories():
    """Product categories used to seed scenario generation."""
    return {"categories": PRODUCT_CATEGORIES}
