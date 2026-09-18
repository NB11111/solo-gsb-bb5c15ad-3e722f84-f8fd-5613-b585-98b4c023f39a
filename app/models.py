"""请求 / 响应数据模型。

方位角约定（度，顺时针，正北为 0°）：

* 取值范围 0 <= bearing <= 360，360° 按 0° 归一化；
* 灯的可见区间为半开区间 ``[start, end)``；
* ``start == end`` 表示整圆可见（0°～360°）；
* ``start > end`` 表示区间跨越 0°，服务内部拆为
  ``[0, end)`` 与 ``[start, 360)`` 两段。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Light(BaseModel):
    """单盏航标灯的输入参数。"""

    model_config = ConfigDict(extra="forbid")

    id: Annotated[
        str,
        Field(min_length=1, description="灯编号，在一次请求内唯一", examples=["L1"]),
    ]
    color: Annotated[
        str,
        Field(
            min_length=1,
            description="灯质颜色，如 R / W / G / Y；服务按大写归一化",
            examples=["R"],
        ),
    ]
    visible_distance: Annotated[
        float,
        Field(
            ge=0,
            description="灯的额定可见距离（海里），小于观察距离的灯将被滤除",
            examples=[10.0],
        ),
    ]
    start: Annotated[
        float,
        Field(ge=0, le=360, description="顺时针可见区间起点（度，含）", examples=[315.0]),
    ]
    end: Annotated[
        float,
        Field(ge=0, le=360, description="顺时针可见区间终点（度，不含）；start=end 为整圆", examples=[45.0]),
    ]

    @field_validator("id")
    @classmethod
    def _strip_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("灯编号不得为空白字符串")
        return value

    @field_validator("color")
    @classmethod
    def _normalize_color(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("颜色不得为空白字符串")
        return value


class SectorRequest(BaseModel):
    """扇区校验请求。"""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "observation_distance": 5.0,
                    "lights": [
                        {"id": "L1", "color": "W", "visible_distance": 10.0,
                         "start": 0.0, "end": 180.0},
                        {"id": "L2", "color": "R", "visible_distance": 8.0,
                         "start": 90.0, "end": 270.0},
                        {"id": "L3", "color": "G", "visible_distance": 4.0,
                         "start": 0.0, "end": 360.0},
                        {"id": "L4", "color": "W", "visible_distance": 12.0,
                         "start": 315.0, "end": 45.0},
                    ],
                }
            ]
        }
    )

    observation_distance: Annotated[
        float,
        Field(
            gt=0,
            description="观察点的观察距离（海里）；额定可见距离不足此值的灯被滤除",
            examples=[5.0],
        ),
    ]
    lights: Annotated[
        list[Light],
        Field(default_factory=list, description="参与校验的航标灯列表，允许为空"),
    ]

    @model_validator(mode="after")
    def _unique_ids(self) -> SectorRequest:
        ids = [light.id for light in self.lights]
        duplicates = sorted({light_id for light_id in ids if ids.count(light_id) > 1})
        if duplicates:
            raise ValueError(f"灯编号重复: {', '.join(duplicates)}")
        return self


class LightOut(BaseModel):
    """回显的航标灯参数。"""

    id: str
    color: str
    visible_distance: float
    start: float
    end: float


class SectorOut(BaseModel):
    """合并后的一个扇区。"""

    start: Annotated[float, Field(description="扇区起始方位（度，含）")]
    end: Annotated[float, Field(description="扇区结束方位（度，不含）")]
    light_ids: Annotated[list[str], Field(description="该扇区内可见的灯编号（已排序）")]
    colors: Annotated[list[str], Field(description="该扇区内出现的灯质颜色（去重、已排序）")]
    blind: Annotated[bool, Field(description="是否为盲区（无任何可见灯）")]
    conflict: Annotated[bool, Field(description="是否为颜色冲突区（同时出现不同颜色）")]


class BlindSectorOut(BaseModel):
    """盲区扇区。"""

    start: float
    end: float


class ConflictSectorOut(BaseModel):
    """颜色冲突扇区。"""

    start: float
    end: float
    light_ids: list[str]
    colors: list[str]


class Summary(BaseModel):
    """统计汇总。"""

    total_lights: int
    retained_lights: int
    filtered_lights: int
    sector_count: int
    blind_angle: Annotated[float, Field(description="盲区总角度（度）")]
    conflict_angle: Annotated[float, Field(description="颜色冲突总角度（度）")]
    covered_angle: Annotated[float, Field(description="至少有一盏灯可见的总角度（度）")]


class ValidationResponse(BaseModel):
    """扇区校验结果。"""

    observation_distance: float
    total_lights: int
    retained_lights: list[LightOut]
    filtered_lights: list[LightOut]
    sectors: list[SectorOut]
    blind_sectors: list[BlindSectorOut]
    conflict_sectors: list[ConflictSectorOut]
    summary: Summary


class HealthOut(BaseModel):
    status: Literal["ok"]


class RootOut(BaseModel):
    service: str
    version: str
    docs_url: str
    openapi_url: str
    health_url: str
    validate_url: str
