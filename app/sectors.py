"""核心扇区计算：角度区间展开、按边界切分、合并同集扇区。

方位角采用 0°（正北）起顺时针计量的规则：

* ``[start, end)``：普通顺时针半开区间；
* ``start == end``：整圆 ``[0, 360)``；
* ``start > end``：跨越 0°，拆成 ``[start, 360)`` 与 ``[0, end)``。
"""

from __future__ import annotations

from dataclasses import dataclass

from .schemas import Light, Sector, VisibleLight


@dataclass(frozen=True)
class Piece:
    """一段半开角度区间 ``[start, end)`` 及其中点亮的灯（临时结构）。"""

    start: float
    end: float
    lights: tuple[VisibleLight, ...]


def to_pieces(start: float, end: float) -> list[tuple[float, float]]:
    """把一盏灯的方位区间展开为不跨越 0° 的半开区间列表。"""
    if start == end:
        return [(0.0, 360.0)]
    if start < end:
        return [(float(start), float(end))]
    return [(float(start), 360.0), (0.0, float(end))]


def _light_at(lights: list[VisibleLight], angle: float) -> tuple[VisibleLight, ...]:
    """返回在给定方位上可见的灯（按请求顺序）。

    扇区是半开区间，使用扇区中点判定归属，可天然避开 ``[start, end)``
    的端点归属问题（end 边界不包含在内）。
    """
    return tuple(
        light
        for light in lights
        if any(piece_start <= angle < piece_end for piece_start, piece_end in light.ranges)
    )


def merge_same_set(pieces: list[Piece]) -> list[Piece]:
    """合并相邻且灯集合（编号集合）相同的扇区。

    正常由边界切分产生的相邻扇区，其灯集合一定在边界处发生变化；
    合并是防御性步骤，同时也满足题目显式要求。
    """
    if not pieces:
        return []

    merged: list[Piece] = [pieces[0]]
    for piece in pieces[1:]:
        prev = merged[-1]
        prev_ids = {light.id for light in prev.lights}
        cur_ids = {light.id for light in piece.lights}
        if piece.start == prev.end and prev_ids == cur_ids:
            merged[-1] = Piece(prev.start, piece.end, piece.lights)
        else:
            merged.append(piece)
    return merged


def analyze(
    observation_distance: float,
    lights: list[Light],
) -> tuple[list[Sector], list[Light], list[VisibleLight]]:
    """执行扇区校验。

    返回 ``(扇区列表, 被滤除的灯, 可见灯)``，扇区按起始方位升序排列。
    """
    filtered_out: list[Light] = []
    visible: list[VisibleLight] = []

    # 1. 滤除可见距离不足的灯（可见距离须不小于观察距离）
    for light in lights:
        if light.visible_distance < observation_distance:
            filtered_out.append(light)
            continue
        visible.append(
            VisibleLight(
                id=light.id,
                color=light.color,
                visible_distance=light.visible_distance,
                start=light.start,
                end=light.end,
                ranges=to_pieces(light.start, light.end),
            )
        )

    # 2. 收集全部区间端点作为切分边界（含 0° 与 360°）
    boundaries: set[float] = {0.0, 360.0}
    for light in visible:
        for piece_start, piece_end in light.ranges:
            boundaries.add(piece_start)
            boundaries.add(piece_end)

    points = sorted(boundaries)

    # 3. 按边界切分 0°～360°，用中点判定每段内点亮的灯
    pieces: list[Piece] = []
    for i in range(len(points) - 1):
        seg_start, seg_end = points[i], points[i + 1]
        if seg_end <= seg_start:
            continue
        mid = (seg_start + seg_end) / 2.0
        active = _light_at(visible, mid)
        pieces.append(Piece(seg_start, seg_end, active))

    # 4. 合并相邻且灯集合相同的扇区
    pieces = merge_same_set(pieces)

    # 5. 标注盲区与颜色冲突
    sectors: list[Sector] = []
    for piece in pieces:
        colors = {light.color for light in piece.lights}
        sector = Sector(
            start=piece.start,
            end=piece.end,
            light_ids=[light.id for light in piece.lights],
            colors=sorted(colors),
            is_blind=len(piece.lights) == 0,
            is_conflict=len(colors) > 1,
        )
        sectors.append(sector)

    return sectors, filtered_out, visible


def blind_sectors(sectors: list[Sector]) -> list[Sector]:
    """没有任何灯可见的扇区。"""
    return [sector for sector in sectors if sector.is_blind]


def conflict_sectors(sectors: list[Sector]) -> list[Sector]:
    """同时出现不同颜色灯光的扇区。"""
    return [sector for sector in sectors if sector.is_conflict]
