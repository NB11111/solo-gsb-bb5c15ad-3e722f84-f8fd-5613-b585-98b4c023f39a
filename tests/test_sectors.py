"""扇区计算与 API 的单元测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import Light
from app.sectors import Piece, VisibleLight, analyze, merge_same_set, to_pieces


def make_light(
    light_id: str,
    color: str = "红",
    visible_distance: float = 10.0,
    start: float = 0.0,
    end: float = 360.0,
) -> Light:
    return Light(
        id=light_id,
        color=color,
        visible_distance=visible_distance,
        start=start,
        end=end,
    )


# ---------- 区间展开 ----------

def test_to_pieces_full_circle():
    assert to_pieces(0.0, 0.0) == [(0.0, 360.0)]
    assert to_pieces(120.0, 120.0) == [(0.0, 360.0)]


def test_to_pieces_normal():
    assert to_pieces(10.0, 120.0) == [(10.0, 120.0)]


def test_to_pieces_wraparound_split():
    assert to_pieces(315.0, 45.0) == [(315.0, 360.0), (0.0, 45.0)]


# ---------- 过滤 ----------

def test_filter_lights_by_observation_distance():
    lights = [
        make_light("near", visible_distance=4.0),
        make_light("equal", visible_distance=5.0),
        make_light("far", visible_distance=6.0),
    ]
    sectors, filtered, visible = analyze(5.0, lights)

    assert [light.id for light in filtered] == ["near"]
    assert [light.id for light in visible] == ["equal", "far"]
    # 剩余两盏均为整圆灯，整圆内两灯都亮
    assert len(sectors) == 1
    assert sectors[0].light_ids == ["equal", "far"]


# ---------- 切分 / 盲区 / 冲突 ----------

def test_sectors_split_blind_and_conflict():
    lights = [
        make_light("A", color="红", start=0.0, end=120.0),
        make_light("B", color="绿", start=90.0, end=270.0),
    ]
    sectors, _, _ = analyze(0.0, lights)

    # 0-90 仅 A；90-120 A+B 冲突；120-270 仅 B；270-360 盲区
    assert [(s.start, s.end) for s in sectors] == [
        (0.0, 90.0),
        (90.0, 120.0),
        (120.0, 270.0),
        (270.0, 360.0),
    ]
    assert sectors[0].light_ids == ["A"]
    assert sectors[0].is_conflict is False
    assert sectors[1].is_conflict is True
    assert sectors[1].colors == ["红", "绿"]
    assert sectors[3].is_blind is True
    assert sectors[3].light_ids == []


def test_wraparound_light_conflict_around_zero():
    lights = [
        make_light("Y", color="黄", start=315.0, end=45.0),
        make_light("G", color="绿", start=0.0, end=90.0),
    ]
    sectors, _, _ = analyze(0.0, lights)

    # 315-360 仅 Y；0-45 Y+G 冲突；45-90 仅 G；90-315 盲区
    assert [(s.start, s.end) for s in sectors] == [
        (0.0, 45.0),
        (45.0, 90.0),
        (90.0, 315.0),
        (315.0, 360.0),
    ]
    by_range = {(s.start, s.end): s for s in sectors}
    assert by_range[(315.0, 360.0)].light_ids == ["Y"]
    assert by_range[(0.0, 45.0)].is_conflict is True
    assert by_range[(90.0, 315.0)].is_blind is True


def test_full_circle_single_sector():
    sectors, _, _ = analyze(0.0, [make_light("A", start=0.0, end=360.0)])
    assert len(sectors) == 1
    assert sectors[0].start == 0.0
    assert sectors[0].end == 360.0
    assert sectors[0].is_blind is False
    assert sectors[0].is_conflict is False


def test_all_lights_filtered_means_full_blind_circle():
    sectors, filtered, visible = analyze(100.0, [make_light("A")])
    assert len(visible) == 0
    assert len(filtered) == 1
    assert len(sectors) == 1
    assert sectors[0].is_blind is True
    assert (sectors[0].start, sectors[0].end) == (0.0, 360.0)


# ---------- 合并 ----------

def _vl(light_id: str) -> VisibleLight:
    return VisibleLight(
        id=light_id,
        color="红",
        visible_distance=10.0,
        start=0.0,
        end=360.0,
        ranges=[(0.0, 360.0)],
    )


def test_merge_adjacent_same_set():
    pieces = [
        Piece(0.0, 90.0, (_vl("A"),)),
        Piece(90.0, 180.0, (_vl("A"),)),
        Piece(180.0, 360.0, ()),
    ]
    merged = merge_same_set(pieces)
    assert len(merged) == 2
    assert (merged[0].start, merged[0].end) == (0.0, 180.0)
    assert (merged[1].start, merged[1].end) == (180.0, 360.0)


def test_merge_keeps_different_sets_apart():
    pieces = [
        Piece(0.0, 90.0, (_vl("A"),)),
        Piece(90.0, 180.0, (_vl("A"), _vl("B"))),
    ]
    merged = merge_same_set(pieces)
    assert len(merged) == 2


# ---------- HTTP ----------

client = TestClient(app)


def test_api_validate_end_to_end():
    payload = {
        "observation_distance": 5.0,
        "lights": [
            {"id": "L1", "color": "红", "visible_distance": 10.0, "start": 0.0, "end": 120.0},
            {"id": "L2", "color": "绿", "visible_distance": 8.0, "start": 90.0, "end": 270.0},
            {"id": "L4", "color": "黄", "visible_distance": 3.0, "start": 0.0, "end": 360.0},
        ],
    }
    response = client.post("/api/v1/sectors/validate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["total_lights"] == 3
    assert [light["id"] for light in data["filtered_out"]] == ["L4"]
    assert data["blind_sectors"][0]["start"] == 270.0
    assert data["conflict_sectors"][0]["start"] == 90.0
    assert data["conflict_sectors"][0]["light_ids"] == ["L1", "L2"]


def test_api_duplicate_ids_rejected():
    payload = {
        "observation_distance": 1.0,
        "lights": [
            {"id": "X", "color": "红", "visible_distance": 2.0, "start": 0.0, "end": 10.0},
            {"id": "X", "color": "绿", "visible_distance": 2.0, "start": 0.0, "end": 10.0},
        ],
    }
    response = client.post("/api/v1/sectors/validate", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("bad_angle", [-0.1, 360.1])
def test_api_angle_out_of_range_rejected(bad_angle):
    payload = {
        "observation_distance": 1.0,
        "lights": [
            {"id": "X", "color": "红", "visible_distance": 2.0, "start": bad_angle, "end": 10.0},
        ],
    }
    response = client.post("/api/v1/sectors/validate", json=payload)
    assert response.status_code == 422


def test_api_bad_color_rejected():
    payload = {
        "observation_distance": 1.0,
        "lights": [
            {"id": "X", "color": "蓝", "visible_distance": 2.0, "start": 0.0, "end": 10.0},
        ],
    }
    response = client.post("/api/v1/sectors/validate", json=payload)
    assert response.status_code == 422


def test_health_and_docs():
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    openapi = client.get("/openapi.json").json()
    assert "/api/v1/sectors/validate" in openapi["paths"]
