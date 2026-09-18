"""扇区切分 / 合并 / 分类的纯函数核心。

规则
----

1. 先滤除 ``visible_distance < observation_distance`` 的灯；
2. 每盏保留灯的顺时针区间 ``[start, end)`` 归一化：
   * ``start == end``：整圆 ``[0, 360)``；
   * ``start < end``：单段；
   * ``start > end``：跨越 0°，拆为 ``[start, 360)`` 与 ``[0, end)``；
3. 收集所有区间端点，并加入 0、360，按顺序切分整圆；
4. 以每个切片中点判断哪些灯覆盖该切片（半开区间语义）；
5. 合并相邻且可见灯集合完全相同的切片，得到极大扇区；
6. 无灯 -> 盲区；灯集合中出现两种及以上颜色 -> 颜色冲突区。
"""

from __future__ import annotations

from app.models import Light, SectorRequest

FULL_CIRCLE = 360.0
# 角度比较容差，避免浮点误差导致本应重合的边界无法合并
_EPS = 1e-9


def normalize_intervals(start: float, end: float) -> list[tuple[float, float]]:
    """把顺时针方位区间归一化为若干个不跨 0° 的 ``[a, b)`` 段。"""
    if abs(start - end) <= _EPS:
        # start == end 表示整圆
        return [(0.0, FULL_CIRCLE)]
    if start < end:
        return [(start, end)]
    # start > end：跨越 0°
    return [(start, FULL_CIRCLE), (0.0, end)]


def _round(value: float) -> float:
    """输出角度统一保留 6 位小数，抹去计算噪声（360.0 原样保留）。"""
    if abs(value - FULL_CIRCLE) <= 1e-7:
        return FULL_CIRCLE
    if abs(value) <= 1e-7:
        return 0.0
    return round(value, 6)


def analyze(request: SectorRequest) -> dict:
    """执行完整的扇区校验流程，返回可直接序列化的结果字典。"""

    # ---------- 1. 滤除可见距离不足的灯 ----------
    retained: list[Light] = []
    filtered: list[Light] = []
    for light in request.lights:
        if light.visible_distance + _EPS >= request.observation_distance:
            retained.append(light)
        else:
            filtered.append(light)

    # ---------- 2. 归一化区间 + 3. 收集全部边界 ----------
    segments: list[tuple[Light, tuple[float, float]]] = []
    boundaries: set[float] = {0.0, FULL_CIRCLE}
    for light in retained:
        for interval in normalize_intervals(light.start, light.end):
            segments.append((light, interval))
            boundaries.add(interval[0])
            boundaries.add(interval[1])

    cuts = sorted(boundaries)

    # ---------- 4. 按中点判定每个切片的可见灯集合 ----------
    raw_sectors: list[dict] = []
    for left, right in zip(cuts, cuts[1:]):
        if right - left <= _EPS:
            continue
        midpoint = (left + right) / 2.0
        visible_ids: list[str] = []
        colors: set[str] = set()
        for light, (seg_start, seg_end) in segments:
            if seg_start <= midpoint < seg_end:
                visible_ids.append(light.id)
                colors.add(light.color)

        visible_ids.sort()
        raw_sectors.append(
            {
                "start": left,
                "end": right,
                "light_ids": visible_ids,
                "colors": sorted(colors),
                "key": tuple(visible_ids),
            }
        )

    # ---------- 5. 合并相邻且灯集合相同的切片 ----------
    merged: list[dict] = []
    for sector in raw_sectors:
        if merged and merged[-1]["key"] == sector["key"]:
            merged[-1]["end"] = sector["end"]
        else:
            merged.append(dict(sector))

    # ---------- 6. 分类并汇总 ----------
    sectors_out: list[dict] = []
    blind_sectors: list[dict] = []
    conflict_sectors: list[dict] = []
    blind_angle = 0.0
    conflict_angle = 0.0
    covered_angle = 0.0

    for sector in merged:
        is_blind = not sector["light_ids"]
        is_conflict = len(sector["colors"]) >= 2
        start = _round(sector["start"])
        end = _round(sector["end"])
        width = end - start

        if is_blind:
            blind_angle += width
            blind_sectors.append({"start": start, "end": end})
        else:
            covered_angle += width
        if is_conflict:
            conflict_angle += width
            conflict_sectors.append(
                {
                    "start": start,
                    "end": end,
                    "light_ids": sector["light_ids"],
                    "colors": sector["colors"],
                }
            )

        sectors_out.append(
            {
                "start": start,
                "end": end,
                "light_ids": sector["light_ids"],
                "colors": sector["colors"],
                "blind": is_blind,
                "conflict": is_conflict,
            }
        )

    def _as_light_out(light: Light) -> dict:
        return {
            "id": light.id,
            "color": light.color,
            "visible_distance": light.visible_distance,
            "start": _round(light.start),
            "end": _round(light.end),
        }

    return {
        "observation_distance": request.observation_distance,
        "total_lights": len(request.lights),
        "retained_lights": [_as_light_out(light) for light in retained],
        "filtered_lights": [_as_light_out(light) for light in filtered],
        "sectors": sectors_out,
        "blind_sectors": blind_sectors,
        "conflict_sectors": conflict_sectors,
        "summary": {
            "total_lights": len(request.lights),
            "retained_lights": len(retained),
            "filtered_lights": len(filtered),
            "sector_count": len(sectors_out),
            "blind_angle": _round(blind_angle),
            "conflict_angle": _round(conflict_angle),
            "covered_angle": _round(covered_angle),
        },
    }
