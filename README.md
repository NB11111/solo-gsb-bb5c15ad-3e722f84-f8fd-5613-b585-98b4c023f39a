# 航标灯可视扇区校验 API

基于 **Python + FastAPI** 实现：提交观察距离与多盏航标灯的编号、颜色、额定可见距离和
顺时针可见方位区间，服务自动完成

1. **距离滤除**：丢弃额定可见距离小于观察距离的灯；
2. **区间归一化**：方位区间按半开区间 `[start, end)` 处理——
   - `start = end`：整圆可见（0°～360°）；
   - `start > end`：跨越 0°，自动拆为 `[start, 360)` 与 `[0, end)`；
3. **边界切分**：用全部区间端点切分 0°～360°，以切片中点判定各灯可见性；
4. **扇区合并**：合并相邻且可见灯集合完全相同的切片，得到极大扇区；
5. **结果分类**：
   - **盲区**（`blind_sectors`）：扇区内无任何可见灯；
   - **颜色冲突区**（`conflict_sectors`）：同一扇区内同时出现两种及以上颜色；
   - 普通可见扇区：在 `sectors` 中给出灯编号与颜色集合。

角度约定：单位为度，0° 为正北、顺时针递增，取值范围 `[0, 360]`。

---

## 一条命令启动

```bash
docker compose up -d --build
```

启动后服务地址（默认宿主机端口 8000）：

| 用途 | 地址 |
| --- | --- |
| Swagger UI（可交互调试） | http://localhost:8000/docs |
| ReDoc 文档 | http://localhost:8000/redoc |
| OpenAPI JSON | http://localhost:8000/openapi.json |
| 健康检查 | http://localhost:8000/healthz |
| **扇区校验接口** | `POST http://localhost:8000/api/v1/sectors/validate` |

停止 / 清理：

```bash
docker compose down          # 停止并删除容器
```

> 不想用 Compose 也可以：`docker build -t navigation-light-sector-api . && docker run -p 8000:8000 navigation-light-sector-api`

---

## 配置

全部配置通过环境变量完成（见 `docker-compose.yml`）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_HOST` | `0.0.0.0` | 应用监听地址（容器内） |
| `APP_PORT` | `8000` | 应用监听端口（容器内固定映射 8000） |

修改宿主机映射端口（例如改用 18000）：

```bash
APP_PORT=18000 docker compose up -d --build
# 访问 http://localhost:18000/docs
```

---

## 接口说明

### `POST /api/v1/sectors/validate`

请求体：

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `observation_distance` | number | `> 0` | 观察距离（海里） |
| `lights[]` | array | 灯编号唯一 | 航标灯列表，可为空 |
| `lights[].id` | string | 非空、不重复 | 灯编号 |
| `lights[].color` | string | 非空 | 灯质颜色，服务按大写归一化（如 `r` → `R`） |
| `lights[].visible_distance` | number | `>= 0` | 额定可见距离（海里），小于观察距离则滤除 |
| `lights[].start` | number | `[0, 360]` | 顺时针区间起点（含） |
| `lights[].end` | number | `[0, 360]` | 顺时针区间终点（不含）；`start=end` 为整圆，`start>end` 跨 0° |

请求示例：

```bash
curl -s http://localhost:8000/api/v1/sectors/validate \
  -H 'Content-Type: application/json' \
  -d '{
    "observation_distance": 5,
    "lights": [
      {"id": "L1", "color": "W", "visible_distance": 10, "start": 0,   "end": 180},
      {"id": "L2", "color": "R", "visible_distance": 8,  "start": 90,  "end": 270},
      {"id": "L3", "color": "G", "visible_distance": 4,  "start": 0,   "end": 360},
      {"id": "L4", "color": "W", "visible_distance": 12, "start": 315, "end": 45}
    ]
  }'
```

处理过程：

- `L3` 额定可见距离 4 < 观察距离 5 → **被滤除**；
- `L4` 区间 `[315,45)` 跨 0° → 拆为 `[315,360)` 与 `[0,45)`；
- 按边界 0 / 45 / 90 / 180 / 270 / 315 / 360 切分并合并。

响应示例：

```json
{
  "observation_distance": 5.0,
  "total_lights": 4,
  "retained_lights": [
    {"id": "L1", "color": "W", "visible_distance": 10.0, "start": 0.0, "end": 180.0},
    {"id": "L2", "color": "R", "visible_distance": 8.0,  "start": 90.0, "end": 270.0},
    {"id": "L4", "color": "W", "visible_distance": 12.0, "start": 315.0, "end": 45.0}
  ],
  "filtered_lights": [
    {"id": "L3", "color": "G", "visible_distance": 4.0, "start": 0.0, "end": 360.0}
  ],
  "sectors": [
    {"start": 0.0,   "end": 45.0,  "light_ids": ["L1", "L4"], "colors": ["W"],      "blind": false, "conflict": false},
    {"start": 45.0,  "end": 90.0,  "light_ids": ["L1"],       "colors": ["W"],      "blind": false, "conflict": false},
    {"start": 90.0,  "end": 180.0, "light_ids": ["L1", "L2"], "colors": ["R", "W"], "blind": false, "conflict": true},
    {"start": 180.0, "end": 270.0, "light_ids": ["L2"],       "colors": ["R"],      "blind": false, "conflict": false},
    {"start": 270.0, "end": 315.0, "light_ids": [],            "colors": [],         "blind": true,  "conflict": false},
    {"start": 315.0, "end": 360.0, "light_ids": ["L4"],       "colors": ["W"],      "blind": false, "conflict": false}
  ],
  "blind_sectors": [
    {"start": 270.0, "end": 315.0}
  ],
  "conflict_sectors": [
    {"start": 90.0, "end": 180.0, "light_ids": ["L1", "L2"], "colors": ["R", "W"]}
  ],
  "summary": {
    "total_lights": 4,
    "retained_lights": 3,
    "filtered_lights": 1,
    "sector_count": 6,
    "blind_angle": 45.0,
    "conflict_angle": 90.0,
    "covered_angle": 315.0
  }
}
```

### 其他端点

- `GET /`：服务信息与文档地址；
- `GET /healthz`：健康检查，返回 `{"status": "ok"}`；
- 交互式文档直接访问 `/docs`，完整 Schema 见 `/openapi.json`。

参数非法（方位越界、观察距离 ≤ 0、灯编号重复、出现未知字段等）时返回 `422`，
响应体中包含具体字段级错误信息。

---

## 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest httpx          # 仅测试需要

uvicorn app.main:app --reload --port 8000
python -m pytest -q               # 运行测试（29 个用例）
```

## 项目结构

```
.
├── app/
│   ├── main.py        # FastAPI 入口、路由、OpenAPI 元数据
│   ├── models.py      # Pydantic 请求 / 响应模型（含输入校验）
│   └── sectors.py     # 区间归一化、切分、合并与分类的纯函数核心
├── tests/             # pytest 单元测试 + 接口测试
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```
