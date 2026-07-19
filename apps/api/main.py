"""FastAPI 应用进程入口。"""

from fastapi import FastAPI

from apps.api.routers.health import router as health_router


def create_app() -> FastAPI:
    """创建并装配 HTTP 应用，启动阶段不连接外部基础设施。"""
    application = FastAPI(title="faultAgent API", version="0.1.0")
    application.include_router(health_router)
    return application


app = create_app()


def run() -> None:
    """使用 Uvicorn 启动本地 API 开发服务器。"""
    import uvicorn

    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
