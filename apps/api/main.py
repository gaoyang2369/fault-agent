"""FastAPI application entry point."""

from fastapi import FastAPI

from apps.api.routers.health import router as health_router


def create_app() -> FastAPI:
    """Build the HTTP application without external infrastructure connections."""
    application = FastAPI(title="faultAgent API", version="0.1.0")
    application.include_router(health_router)
    return application


app = create_app()


def run() -> None:
    """Run the API development server."""
    import uvicorn

    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
