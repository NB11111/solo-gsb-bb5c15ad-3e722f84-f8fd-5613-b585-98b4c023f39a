"""FastAPI 应用入口与路由。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Body, FastAPI
from fastapi.responses import RedirectResponse

from .schemas import SectorRequest, SectorResponse
from .sectors import analyze, blind_sectors, conflict_sectors

DESCRIPTION = """航标灯可视扇区校验服务。

## 功能

1. 提交观察距离及多盏航标灯（编号、颜色、可见距离、顺时针方位区间）；
2. 先滤除 **可见距离小于观察距离** 的灯；
3. 按全部区间边界切分 0°～360°；
4. 合并相邻且灯集合相同的扇区；
5. 返回各扇区可见的灯编号、**盲区** 以及不同颜色同时出现的 **颜色冲突区**。

## 方位区间规则

* `[start, end)`：从 start 顺时针到 end 的半开区间；
* `start == end`：整圆 `[0, 360)`；
* `start > end`：跨越 0°，自动拆成 `[start, 360)` 与 `[0, end)`。
"""

app = FastAPI(
    title="航标灯可视扇区校验 API",
    description=DESCRIPTION,
    version="1.0.0",
    contact={"name": "Navigation Aid Sector Validator"},
    license_info={"name": "MIT"},
)


_EXAMPLE_REQUEST = {
    "observation_distance": 5.0,
    "lights": [
        {"id": "L1", "color": "红", "visible_distance": 10.0, "start": 0.0, "end": 120.0},
        {"id": "L2", "color": "绿", "visible_distance": 8.0, "start": 90.0, "end": 270.0},
        {
            "id": "L3",
            "color": "白",
            "visible_distance": 12.0,
            "start": 315.0,
            "end": 45.0,
        },
        {"id": "L4", "color": "黄", "visible_distance": 3.0, "start": 0.0, "end": 360.0},
    ],
}


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """根路径重定向到 Swagger UI。"""
    return RedirectResponse(url="/docs")


@app.post(
    "/api/v1/sectors/validate",
    response_model=SectorResponse,
    summary="校验航标灯可视扇区",
    tags=["扇区校验"],
)
def validate_sectors(
    request: Annotated[
        SectorRequest,
        Body(
            openapi_examples={
                "example": {
                    "summary": "示例：含跨 0° 灯、颜色冲突与被滤除灯",
                    "value": _EXAMPLE_REQUEST,
                }
            }
        ),
    ],
) -> SectorResponse:
    """滤除距离不足的灯，切分并合并扇区，标注盲区与颜色冲突区。"""
    sectors, filtered, visible = analyze(
        request.observation_distance,
        request.lights,
    )
    return SectorResponse(
        observation_distance=request.observation_distance,
        total_lights=len(request.lights),
        visible_lights=visible,
        filtered_out=filtered,
        sectors=sectors,
        blind_sectors=blind_sectors(sectors),
        conflict_sectors=conflict_sectors(sectors),
    )


@app.get(
    "/api/v1/health",
    tags=["系统"],
    summary="健康检查",
)
def health() -> dict[str, str]:
    """容器健康检查探针。"""
    return {"status": "ok"}
