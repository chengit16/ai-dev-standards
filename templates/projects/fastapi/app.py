"""装配 FastAPI 应用和健康端点，启动无需外部数据服务。"""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """支持通过环境变量或本机 .env 覆盖公开服务名称。"""

    model_config = SettingsConfigDict(env_prefix="STARTER_", env_file=".env", extra="ignore")
    title: str = "工程示例 API"


class HealthResponse(BaseModel):
    """探测响应仅表明 HTTP 服务可用。"""

    status: Literal["ok"] = "ok"


def health() -> HealthResponse:
    """返回稳定的健康响应，不访问外部服务。"""
    return HealthResponse()


def create_app() -> FastAPI:
    """按当前环境配置装配独立应用，供服务入口和测试使用。"""
    app = FastAPI(title=Settings().title)
    app.get("/api/health", response_model=HealthResponse, operation_id="health")(health)
    return app
