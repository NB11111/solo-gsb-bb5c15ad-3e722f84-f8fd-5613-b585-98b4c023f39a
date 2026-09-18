"""FastAPI 接口层测试。"""

import pytest
from fastapi.testclient import TestClient

from app.main import APP_VERSION, app

client = TestClient(app)


def test_root_lists_urls():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "navigation-light-sector-api"
    assert body["version"] == APP_VERSION
    assert body["docs_url"] == "/docs"


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_available():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["title"]
    assert "/api/v1/sectors/validate" in spec["paths"]


def test_validate_full_workflow():
    payload = {
        "observation_distance": 5,
        "lights": [
            {"id": "L1", "color": "W", "visible_distance": 10, "start": 0, "end": 180},
            {"id": "L2", "color": "R", "visible_distance": 8, "start": 90, "end": 270},
            {"id": "L3", "color": "G", "visible_distance": 4, "start": 0, "end": 360},
            {"id": "L4", "color": "W", "visible_distance": 12, "start": 315, "end": 45},
        ],
    }
    resp = client.post("/api/v1/sectors/validate", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    # L3 可见距离 4 < 观察距离 5，被滤除
    assert [light["id"] for light in body["filtered_lights"]] == ["L3"]
    assert [light["id"] for light in body["retained_lights"]] == ["L1", "L2", "L4"]

    sectors = [(s["start"], s["end"], tuple(s["light_ids"]), s["blind"], s["conflict"])
               for s in body["sectors"]]
    assert sectors == [
        (0.0, 45.0, ("L1", "L4"), False, False),
        (45.0, 90.0, ("L1",), False, False),
        (90.0, 180.0, ("L1", "L2"), False, True),    # W 与 R 同现
        (180.0, 270.0, ("L2",), False, False),
        (270.0, 315.0, (), True, False),             # 盲区
        (315.0, 360.0, ("L4",), False, False),
    ]

    assert body["blind_sectors"] == [{"start": 270.0, "end": 315.0}]
    assert body["conflict_sectors"] == [
        {"start": 90.0, "end": 180.0, "light_ids": ["L1", "L2"], "colors": ["R", "W"]}
    ]

    summary = body["summary"]
    assert summary == {
        "total_lights": 4,
        "retained_lights": 3,
        "filtered_lights": 1,
        "sector_count": 6,
        "blind_angle": 45.0,
        "conflict_angle": 90.0,
        "covered_angle": 315.0,
    }


def test_validate_wrap_around_split_seen_by_api():
    payload = {
        "observation_distance": 1,
        "lights": [
            {"id": "L1", "color": "Y", "visible_distance": 3, "start": 350, "end": 10},
        ],
    }
    resp = client.post("/api/v1/sectors/validate", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["blind_sectors"] == [{"start": 10.0, "end": 350.0}]
    assert [(s["start"], s["end"]) for s in body["sectors"] if not s["blind"]] == [
        (0.0, 10.0),
        (350.0, 360.0),
    ]


def test_validate_empty_lights():
    resp = client.post("/api/v1/sectors/validate", json={"observation_distance": 2, "lights": []})
    assert resp.status_code == 200
    body = resp.json()
    assert body["blind_sectors"] == [{"start": 0.0, "end": 360.0}]
    assert body["summary"]["sector_count"] == 1


@pytest.mark.parametrize("payload", [
    {"observation_distance": 0, "lights": []},                    # 观察距离必须 > 0
    {"observation_distance": 5, "lights": [                      # 方位越界
        {"id": "L1", "color": "R", "visible_distance": 9, "start": -1, "end": 90}
    ]},
    {"observation_distance": 5, "lights": [
        {"id": "L1", "color": "R", "visible_distance": 9, "start": 0, "end": 361}
    ]},
    {"observation_distance": 5, "lights": [                      # 负的可见距离
        {"id": "L1", "color": "R", "visible_distance": -1, "start": 0, "end": 90}
    ]},
])
def test_validate_bad_payloads(payload):
    resp = client.post("/api/v1/sectors/validate", json=payload)
    assert resp.status_code == 422


def test_duplicate_light_ids_rejected():
    payload = {
        "observation_distance": 5,
        "lights": [
            {"id": "X", "color": "R", "visible_distance": 9, "start": 0, "end": 90},
            {"id": "X", "color": "G", "visible_distance": 9, "start": 0, "end": 90},
        ],
    }
    resp = client.post("/api/v1/sectors/validate", json=payload)
    assert resp.status_code == 422
    assert "重复" in resp.json()["detail"][0]["msg"]


def test_unknown_field_rejected():
    payload = {
        "observation_distance": 5,
        "lights": [
            {"id": "L1", "color": "R", "visible_distance": 9, "start": 0,
             "end": 90, "unexpected": 1}
        ],
    }
    resp = client.post("/api/v1/sectors/validate", json=payload)
    assert resp.status_code == 422
