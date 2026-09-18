"""扇区计算核心的单元测试。"""

import pytest

from app.models import Light, SectorRequest
from app.sectors import analyze, normalize_intervals


def make_req(distance: float, lights: list[dict]) -> SectorRequest:
    return SectorRequest(observation_distance=distance, lights=[Light(**item) for item in lights])


# ---------------------------------------------------------------- normalize

class TestNormalize:
    def test_full_circle_when_start_equals_end(self):
        assert normalize_intervals(90.0, 90.0) == [(0.0, 360.0)]

    def test_zero_to_360_is_full_circle(self):
        assert normalize_intervals(0.0, 360.0) == [(0.0, 360.0)]

    def test_plain_interval(self):
        assert normalize_intervals(45.0, 135.0) == [(45.0, 135.0)]

    def test_wrap_around_zero_is_split(self):
        assert normalize_intervals(315.0, 45.0) == [(315.0, 360.0), (0.0, 45.0)]

    def test_wrap_at_zero_exact(self):
        # 0 起、跨零无意义；end=0 且 start>0 -> [start,360)
        assert normalize_intervals(270.0, 0.0) == [(270.0, 360.0), (0.0, 0.0)]


# --------------------------------------------------------------- filtering

class TestFiltering:
    def test_lights_below_observation_distance_are_filtered(self):
        req = make_req(5.0, [
            {"id": "near", "color": "R", "visible_distance": 4.9, "start": 0, "end": 360},
            {"id": "exact", "color": "G", "visible_distance": 5.0, "start": 0, "end": 360},
            {"id": "far", "color": "W", "visible_distance": 9.0, "start": 0, "end": 360},
        ])
        result = analyze(req)
        assert [light["id"] for light in result["filtered_lights"]] == ["near"]
        assert [light["id"] for light in result["retained_lights"]] == ["exact", "far"]

    def test_all_filtered_means_whole_circle_is_blind(self):
        req = make_req(10.0, [
            {"id": "L1", "color": "R", "visible_distance": 1, "start": 0, "end": 90},
        ])
        result = analyze(req)
        assert result["blind_sectors"] == [{"start": 0.0, "end": 360.0}]
        assert result["sectors"] == [
            {"start": 0.0, "end": 360.0, "light_ids": [], "colors": [],
             "blind": True, "conflict": False}
        ]
        assert result["summary"]["blind_angle"] == 360.0

    def test_empty_request(self):
        result = analyze(make_req(1.0, []))
        assert result["blind_sectors"] == [{"start": 0.0, "end": 360.0}]
        assert result["summary"]["sector_count"] == 1


# --------------------------------------------------------------- merging

class TestMerging:
    def test_adjacent_slices_with_same_light_set_merge(self):
        # L1 整圆；L2 = [0,90)、L3 = [90,180)（仅在边界 90 处变化）
        req = make_req(1.0, [
            {"id": "L1", "color": "R", "visible_distance": 10, "start": 10, "end": 10},
            {"id": "L2", "color": "R", "visible_distance": 10, "start": 0, "end": 90},
            {"id": "L3", "color": "R", "visible_distance": 10, "start": 90, "end": 180},
        ])
        result = analyze(req)
        # 期望: [0,180)={L1 恒在 + L2/L3}，但 L2/L3 集合在 90 切换：
        #   [0,90)   -> {L1,L2}
        #   [90,180) -> {L1,L3}
        #   [180,360)-> {L1}
        ids_per_sector = [tuple(s["light_ids"]) for s in result["sectors"]]
        assert ids_per_sector == [
            ("L1", "L2"),
            ("L1", "L3"),
            ("L1",),
        ]

    def test_identical_boundaries_do_not_create_empty_slices(self):
        req = make_req(1.0, [
            {"id": "L1", "color": "R", "visible_distance": 10, "start": 30, "end": 330},
            {"id": "L2", "color": "R", "visible_distance": 10, "start": 30, "end": 330},
        ])
        result = analyze(req)
        widths = [s["end"] - s["start"] for s in result["sectors"]]
        assert all(width > 0 for width in widths)
        assert sum(widths) == pytest.approx(360.0)

    def test_wrap_around_light_visible_in_both_tails(self):
        req = make_req(1.0, [
            {"id": "L1", "color": "W", "visible_distance": 10, "start": 315, "end": 45},
        ])
        result = analyze(req)
        assert result["blind_sectors"] == [{"start": 45.0, "end": 315.0}]
        visible = [s for s in result["sectors"] if not s["blind"]]
        assert [(s["start"], s["end"]) for s in visible] == [(0.0, 45.0), (315.0, 360.0)]

    def test_full_circle_light_no_blind_zone(self):
        req = make_req(1.0, [
            {"id": "L1", "color": "W", "visible_distance": 10, "start": 200, "end": 200},
        ])
        result = analyze(req)
        assert result["blind_sectors"] == []
        assert len(result["sectors"]) == 1
        assert result["sectors"][0]["light_ids"] == ["L1"]
        assert result["summary"]["covered_angle"] == 360.0


# --------------------------------------------------------------- conflict

class TestConflict:
    def test_different_colors_overlap_is_conflict(self):
        req = make_req(1.0, [
            {"id": "R1", "color": "r", "visible_distance": 10, "start": 0, "end": 180},
            {"id": "G1", "color": "g", "visible_distance": 10, "start": 90, "end": 270},
        ])
        result = analyze(req)
        assert result["conflict_sectors"] == [
            {"start": 90.0, "end": 180.0, "light_ids": ["G1", "R1"], "colors": ["G", "R"]}
        ]
        conflict_marks = [s["conflict"] for s in result["sectors"]]
        assert conflict_marks == [False, True, False, False]
        assert result["summary"]["conflict_angle"] == 90.0

    def test_same_color_overlap_is_not_conflict(self):
        req = make_req(1.0, [
            {"id": "R1", "color": "R", "visible_distance": 10, "start": 0, "end": 180},
            {"id": "R2", "color": "R", "visible_distance": 10, "start": 90, "end": 270},
        ])
        result = analyze(req)
        assert result["conflict_sectors"] == []
        assert all(not s["conflict"] for s in result["sectors"])

    def test_color_case_insensitive(self):
        req = make_req(1.0, [
            {"id": "R1", "color": "r", "visible_distance": 10, "start": 0, "end": 90},
            {"id": "R2", "color": "R", "visible_distance": 10, "start": 0, "end": 90},
        ])
        result = analyze(req)
        # 两灯颜色归一化后同为 R -> 不冲突，且集合相同合并为一个扇区
        assert len(result["sectors"]) == 2  # [0,90) 可见 + [90,360) 盲区
        assert not result["sectors"][0]["conflict"]


# --------------------------------------------------------------- half-open

class TestHalfOpenSemantics:
    def test_end_boundary_exclusive(self):
        # L1=[0,90), L2=[90,180)：边界 90 上中点归属清晰，二者绝不冲突
        req = make_req(1.0, [
            {"id": "L1", "color": "R", "visible_distance": 10, "start": 0, "end": 90},
            {"id": "L2", "color": "G", "visible_distance": 10, "start": 90, "end": 180},
        ])
        result = analyze(req)
        assert result["conflict_sectors"] == []
        assert [(s["start"], s["end"], s["light_ids"]) for s in result["sectors"]] == [
            (0.0, 90.0, ["L1"]),
            (90.0, 180.0, ["L2"]),
            (180.0, 360.0, []),
        ]

    def test_angle_sum_is_360(self):
        req = make_req(3.0, [
            {"id": "A", "color": "W", "visible_distance": 5, "start": 10, "end": 120},
            {"id": "B", "color": "R", "visible_distance": 6, "start": 200, "end": 30},
            {"id": "C", "color": "G", "visible_distance": 2, "start": 0, "end": 360},  # 被滤除
        ])
        result = analyze(req)
        total = sum(s["end"] - s["start"] for s in result["sectors"])
        assert total == pytest.approx(360.0)
        assert result["summary"]["blind_angle"] + result["summary"]["covered_angle"] == pytest.approx(360.0)
