# 航标灯可视扇区校验 API

基于 **Python + FastAPI** 的航标灯可视扇区校验服务。提交观察距离与多盏航标灯
（编号、颜色、可见距离、顺时针方位区间），服务会：

1. 滤除**可见距离小于观察距离**的灯；
2. 按全部灯的区间边界切分 `0°～360°`；
3. 合并相邻且灯集合相同的扇区；
4. 输出每个扇区可见的灯编号，并标注**盲区**与不同颜色同时出现的**颜色冲突区**。

## 方位区间规则

方位角以正北为 `0°`，顺时针计量，取值 `0～360`（度）：

| 写法 | 含义 |
| --- | --- |
| `[start, end)`，`start < end` | 从 `start` 顺时针到 `end` 的半开区间（含 start，不含 end） |
| `start == end` | **整圆**，等价于 `[0, 360)` |
| `start > end` | **跨越 0°**，自动拆分为 `[start, 360)` 与 `[0, end)` |

距离单位为**海里**（请求与响应一致，服务不做单位换算）。

## 一键启动（Docker Compose）

前置条件：已安装 Docker 与 Docker Compose 插件。

```bash
docker compose up -d --build
```

启动后访问：

| 地址 | 说明 |
| --- | --- |
| http://localhost:8000/docs | Swagger UI（可在线调试，含请求示例） |
| http://localhost:8000/redoc | ReDoc 文档 |
| http://localhost:8000/openapi.json | OpenAPI 3.1 规范（JSON） |
| http://localhost:8000/api/v1/health | 健康检查 |
| http://localhost:8000/api/v1/sectors/validate | 扇区校验接口（POST） |

> 访问根路径 `http://localhost:8000/` 会自动跳转到 `/docs`。

停止与清理：

```bash
docker compose down          # 停止并删除容器
docker compose down -v       # 同时清理卷（本服务无持久化卷）
```

## 配置

唯一可配置项是宿主机映射端口（容器内固定监听 8000）。默认 `8000`，
可通过环境变量 `SECTOR_API_PORT` 覆盖：

```bash
SECTOR_API_PORT=9000 docker compose up -d --build
# 文档地址变为 http://localhost:9000/docs
```

也可以在项目根目录创建 `.env` 文件：

```dotenv
SECTOR_API_PORT=9000
```

其他部署方式（直接改端口 / 反向代理）：

```bash
# 仅用 Docker
docker build -t beacon-sector-api .
docker run -d -p 8000:8000 beacon-sector-api
```

## 本地开发（不使用 Docker）

需要 Python 3.11+：

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# 运行测试
pytest -q
```

## API 用法

### 请求

`POST /api/v1/sectors/validate`

```json
{
  "observation_distance": 5.0,
  "lights": [
    {"id": "L1", "color": "红", "visible_distance": 10.0, "start": 0.0,   "end": 120.0},
    {"id": "L2", "color": "绿", "visible_distance": 8.0,  "start": 90.0,  "end": 270.0},
    {"id": "L3", "color": "白", "visible_distance": 12.0, "start": 315.0, "end": 45.0},
    {"id": "L4", "color": "黄", "visible_distance": 3.0,  "start": 0.0,   "end": 360.0}
  ]
}
```

字段说明：

| 字段 | 类型 | 约束 / 说明 |
| --- | --- | --- |
| `observation_distance` | number | `>= 0`，观察距离（海里） |
| `lights[].id` | string | 非空，且请求内唯一 |
| `lights[].color` | string | `红` / `绿` / `白` / `黄` |
| `lights[].visible_distance` | number | `>= 0`，灯光可见距离（海里） |
| `lights[].start` | number | `0～360`，区间起点（度） |
| `lights[].end` | number | `0～360`，区间终点（度，半开）；等于 start 表示整圆 |

上例的实际含义：

* `L4` 可见距离 3 海里 < 观察距离 5 海里 → 被滤除；
* `L3` 的 `315°→45°` 跨越 0° → 拆成 `[315,360)` 与 `[0,45)`；
* `[0,45)` 同时有红、白两盏灯 → 颜色冲突区；
* `[270,315)` 无任何灯 → 盲区。

### 调用示例（curl）

```bash
curl -X POST http://localhost:8000/api/v1/sectors/validate \
  -H "Content-Type: application/json" \
  -d '{
    "observation_distance": 5.0,
    "lights": [
      {"id":"L1","color":"红","visible_distance":10.0,"start":0.0,"end":120.0},
      {"id":"L2","color":"绿","visible_distance":8.0,"start":90.0,"end":270.0},
      {"id":"L3","color":"白","visible_distance":12.0,"start":315.0,"end":45.0},
      {"id":"L4","color":"黄","visible_distance":3.0,"start":0.0,"end":360.0}
    ]
  }'
```

### 响应

```json
{
  "observation_distance": 5.0,
  "total_lights": 4,
  "visible_lights": [
    {"id": "L1", "color": "红", "visible_distance": 10.0, "start": 0.0,   "end": 120.0, "ranges": [[0.0, 120.0]]},
    {"id": "L2", "color": "绿", "visible_distance": 8.0,  "start": 90.0,  "end": 270.0, "ranges": [[90.0, 270.0]]},
    {
      "id": "L3",
      "color": "白",
      "visible_distance": 12.0,
      "start": 315.0,
      "end": 45.0,
      "ranges": [[315.0, 360.0], [0.0, 45.0]]
    }
  ],
  "filtered_out": [
    {"id": "L4", "color": "黄", "visible_distance": 3.0, "start": 0.0, "end": 360.0}
  ],
  "sectors": [
    {"start": 0.0,   "end": 45.0,  "light_ids": ["L1", "L3"], "colors": ["白", "红"], "is_blind": false, "is_conflict": true},
    {"start": 45.0,  "end": 90.0,  "light_ids": ["L1"],       "colors": ["红"],       "is_blind": false, "is_conflict": false},
    {"start": 90.0,  "end": 120.0, "light_ids": ["L1", "L2"], "colors": ["红", "绿"], "is_blind": false, "is_conflict": true},
    {"start": 120.0, "end": 270.0, "light_ids": ["L2"],       "colors": ["绿"],       "is_blind": false, "is_conflict": false},
    {"start": 270.0, "end": 315.0, "light_ids": [],           "colors": [],           "is_blind": true,  "is_conflict": false},
    {"start": 315.0, "end": 360.0, "light_ids": ["L3"],       "colors": ["白"],       "is_blind": false, "is_conflict": false}
  ],
  "blind_sectors": [
    {"start": 270.0, "end": 315.0, "light_ids": [], "colors": [], "is_blind": true, "is_conflict": false}
  ],
  "conflict_sectors": [
    {"start": 0.0,  "end": 45.0,  "light_ids": ["L1", "L3"], "colors": ["白", "红"], "is_blind": false, "is_conflict": true},
    {"start": 90.0, "end": 120.0, "light_ids": ["L1", "L2"], "colors": ["红", "绿"], "is_blind": false, "is_conflict": true}
  ]
}
```

说明：

* `sectors` 覆盖完整的 `0°～360°`，按起始方位升序排列，互不重叠且彼此相接；
  跨 0° 的情况分别位于首尾两段（如 `[315,360)` 与 `[0,45)`）。
* `is_blind = true`：该扇区无任何可见灯（同时 `light_ids` 与 `colors` 为空）。
* `is_conflict = true`：该扇区同时出现两种及以上颜色的灯光。
* 距离相等（`visible_distance == observation_distance`）时灯**保留**，仅严格小于时滤除。
* 参数非法（角度越界、颜色非法、编号重复、距离为负、灯列表为空等）返回 `422`，错误明细见响应体。

## 算法说明

1. **距离过滤**：逐盏比较 `visible_distance` 与 `observation_distance`。
2. **区间归一化**：`start == end` 展开为整圆；`start > end` 在 0° 处拆成两段。
3. **切分**：把所有区间端点连同 `0°、360°` 排序，相邻端点构成候选扇区。
4. **归属判定**：取每个候选扇区的中点（避开半开区间端点归属问题），
   判断各灯是否在该方位点亮，得到该扇区的灯集合。
5. **合并**：相邻扇区若灯的编号集合相同则合并（实现见
   `app/sectors.py` 的 `merge_same_set`）。
6. **标注**：灯集合为空 → 盲区；灯集合含多种颜色 → 颜色冲突。

## 项目结构

```
.
├── app/
│   ├── __init__.py
│   ├── main.py        # FastAPI 应用与路由
│   ├── schemas.py     # 请求/响应模型与参数校验
│   └── sectors.py     # 区间展开、切分、合并、盲区/冲突判定
├── tests/
│   └── test_sectors.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```
