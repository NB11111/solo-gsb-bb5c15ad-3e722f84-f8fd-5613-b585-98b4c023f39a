"""请求 / 响应的 Pydantic 模型。"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

Angle = Annotated[
    float,
    Field(ge=0, le=360),
]
Distance = Annotated[
    float,
    Field(ge=0),
]


class LightColor:
    """航标灯标准颜色（GB 4696 / IALA）。

    以普通类承载字符串常量，使 OpenAPI 中颜色值直接显示为中文。
    """

    RED = "红"
    GREEN = "绿"
    WHITE = "白"
    YELLOW = "黄"


_COLOR_CHOICES = frozenset(
    {LightColor.RED, LightColor.GREEN, LightColor.WHITE, LightColor.YELLOW}
)


class Light(BaseModel):
    """单盏航标灯的输入参数。"""

    id: Annotated[str, Field(min_length=1, description="灯编号（请求内唯一）")]
    color: Annotated[str, Field(description="灯光颜色：红 / 绿 / 白 / 黄")]
    visible_distance: Annotated[
        float,
        Field(ge=0, description="灯光可见距离（海里），须不小于观察距离才保留"),
    ]
    start: Annotated[Angle, Field(description="方位区间起点（度，顺时针，0=正北）")]
    end: Annotated[
        Angle,
        Field(description="方位区间终点（度，半开区间 [start,end)；start=end 表示整圆）"),
    ]

    @field_validator("color")
    @classmethod
    def _check_color(cls, value: str) -> str:
        if value not in _COLOR_CHOICES:
            raise ValueError("颜色必须为：红 / 绿 / 白 / 黄")
        return value


class SectorRequest(BaseModel):
    """扇区校验请求。"""

    observation_distance: Annotated[
        float,
        Field(
            ge=0,
            description="观察点到灯标的距离（海里）；可见距离小于该值的灯将被滤除",
        ),
    ]
    lights: Annotated[
        list[Light],
        Field(min_length=1, description="参与校验的航标灯列表（至少一盏）"),
    ]

    @model_validator(mode="after")
    def _check_unique_ids(self) -> "SectorRequest":
        ids = [light.id for light in self.lights]
        if len(set(ids)) != len(ids):
            raise ValueError("灯编号必须唯一，不得重复")
        return self


class VisibleLight(BaseModel):
    """通过距离过滤后保留的灯。"""

    id: str
    color: str
    visible_distance: float
    start: float
    end: float
    ranges: Annotated[
        list[tuple[float, float]],
        Field(description="归一化后的不跨 0° 半开区间列表 [start, end)"),
    ]


class Sector(BaseModel):
    """一个合并后的方位扇区。"""

    start: Annotated[float, Field(description="扇区起始方位（度）")]
    end: Annotated[float, Field(description="扇区终止方位（度，不含）")]
    light_ids: Annotated[list[str], Field(description="该扇区内可见的灯编号")]
    colors: Annotated[list[str], Field(description="该扇区内出现的颜色")]
    is_blind: Annotated[bool, Field(description="是否为盲区（无任何灯可见）")]
    is_conflict: Annotated[
        bool, Field(description="是否为颜色冲突区（同时出现不同颜色）")
    ]


class SectorResponse(BaseModel):
    """扇区校验结果。"""

    observation_distance: float
    total_lights: Annotated[int, Field(description="提交的灯总数")]
    visible_lights: Annotated[list[VisibleLight], Field(description="距离过滤后保留的灯")]
    filtered_out: Annotated[
        list[Light], Field(description="被滤除的灯（可见距离小于观察距离）")
    ]
    sectors: Annotated[list[Sector], Field(description="按起始方位升序排列的全部扇区")]
    blind_sectors: Annotated[list[Sector], Field(description="盲区扇区列表")]
    conflict_sectors: Annotated[list[Sector], Field(description="颜色冲突扇区列表")]
