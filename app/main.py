"""FastAPI 应用入口。

启动（本地）::

    uvicorn app.main:app --host 0.0.0.0 --port 8000

容器内直接运行 ``python -m app.main``，主机 / 端口由环境变量
``APP_HOST`` / ``APP_PORT`` 控制（默认 0.0.0.0:8000）。
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models import (
    HealthOut,
    RootOut,
    SectorRequest,
    ValidationResponse,
)
from app.sectors import analyze

APP_VERSION = "1.0.0"

app = FastAPI(
    title="航标灯可视扇区校验 API",
    version=APP_VERSION,
    summary="校验多盏航标灯在各方位上的可见性、盲区与颜色冲突",
    description=(
        "## 功能\n\n"
        "1. 提交观察距离及多盏航标灯（编号、颜色、额定可见距离、顺时针可见方位区间）；\n"
        "2. 区间采用半开区间 `[start, end)`，**start = end 表示整圆**，"
        "**start > end 表示跨越 0°**（服务自动拆分为 `[start,360)` 与 `[0,end)`）；\n"
        "3. 服务先滤除额定可见距离小于观察距离的灯；\n"
        "4. 按全部区间边界切分 0°～360°，再合并相邻且可见灯集合相同的扇区；\n"
        "5. 返回各扇区可见灯编号、**盲区**（无任何灯可见）以及"
        "**颜色冲突区**（同一扇区同时出现不同颜色的灯）。\n\n"
        "## 方位约定\n\n"
        "* 角度单位：度；0° 为正北，顺时针递增，取值范围 `[0, 360]`；\n"
        "* 360° 按 0° 归一化处理。"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=RootOut, tags=["meta"], summary="服务信息")
def root() -> RootOut:
    """返回服务名、版本与主要文档地址。"""
    return RootOut(
        service="navigation-light-sector-api",
        version=APP_VERSION,
        docs_url="/docs",
        openapi_url="/openapi.json",
        health_url="/healthz",
        validate_url="/api/v1/sectors/validate",
    )


@app.get(
    "/healthz",
    response_model=HealthOut,
    tags=["meta"],
    summary="健康检查",
)
def healthz() -> HealthOut:
    """容器 / 负载均衡探活。"""
    return HealthOut(status="ok")


@app.post(
    "/api/v1/sectors/validate",
    response_model=ValidationResponse,
    tags=["sectors"],
    summary="航标灯可视扇区校验",
    responses={
        422: {"description": "请求参数校验失败（字段越界、灯编号重复等）"},
    },
)
def validate_sectors(request: SectorRequest) -> ValidationResponse:
    """滤除距离不足的灯，切分并合并扇区，返回可见性 / 盲区 / 冲突结果。"""
    return ValidationResponse.model_validate(analyze(request))


def main() -> None:
    """容器入口：读取 APP_HOST / APP_PORT 后启动 uvicorn。"""
    import uvicorn

    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
