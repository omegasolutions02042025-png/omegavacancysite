"""
Entrypoint for FastAPI application.
Run with: uvicorn main:app --reload
"""
from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)