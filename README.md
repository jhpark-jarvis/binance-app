# Binance Operations Dashboard

Binance Spot의 BTCUSDT·ETHUSDT 실시간 시장 데이터를 수집하고, 데이터 연속성과
수집 상태를 확인하는 내부 운영 대시보드입니다.

이 프로젝트는 투자 판단 서비스가 아니라, 시장 데이터 수집 파이프라인의 상태와 복구 결과를
확인하기 위한 내부 운영 도구입니다.

## Architecture

- `app.etl`: WebSocket 수집, REST backfill, 데이터 품질 검사와 영속화를 담당하는 Daemon
- `app.web`: FastAPI 기반 REST API 및 서버 렌더링 운영 대시보드
- PostgreSQL: 캔들·체결·수집 이력의 영속 원천
- Redis: 최신 상태 캐시와 ETL → Web 실시간 이벤트 전달

상세 설계와 운영 규칙은 [docs/project-rules.md](docs/project-rules.md)를 참고하세요.

## Key features

- Binance WebSocket 기반 실시간 Aggregate Trade·1분봉 수집
- 빈 DB 최초 실행 시 설정 기간의 1분봉 REST Backfill
- 재시작·재연결 시 완료된 1분봉 누락 구간 검사와 중복 없는 Backfill
- PostgreSQL의 캔들·체결·수집 체크포인트·복구 이력 영속화
- Redis Pub/Sub을 통한 ETL → FastAPI 실시간 이벤트 전달
- 연결 상태, 재연결 횟수, 데이터 지연, 누락 캔들, 최근 복구 이력을 보여 주는 Dashboard

## Prerequisites

- Python 3.13 이상
- Docker Desktop 및 Docker Compose (권장 실행 방식)
- Binance 공개 API에 연결 가능한 네트워크

Binance 공개 시장 데이터만 사용하므로 API key는 필요하지 않습니다.

## Configuration

`.env`는 저장소에 포함하지 않습니다. 아래 명령으로 예시 파일을 복사한 뒤 사용자가 값을 설정합니다.

```bash
copy .env.example .env
```

PowerShell에서는 `Copy-Item .env.example .env`도 사용할 수 있습니다.

주요 환경 변수는 다음과 같습니다.

| Variable | Example | Description |
|---|---|---|
| `POSTGRES_DB` | `binance_ops` | PostgreSQL database 이름 |
| `POSTGRES_USER` | `binance_ops` | PostgreSQL 사용자 |
| `POSTGRES_PASSWORD` | `change-me` | PostgreSQL 비밀번호 |
| `DATABASE_URL` | `postgresql+asyncpg://...` | ETL/Web의 async PostgreSQL 연결 문자열 |
| `REDIS_URL` | `redis://redis:6379/0` | Redis 연결 문자열 |
| `SYMBOLS` | `BTCUSDT,ETHUSDT` | 수집 대상 심볼 목록 |
| `BOOTSTRAP_DAYS` | `7` | 빈 DB에서 최초로 채울 완료 1분봉 이력 일수 |
| `BACKFILL_OVERLAP_MINUTES` | `2` | 누락 지점보다 앞서 재적재할 분 수 |
| `BINANCE_REST_URL` | `https://api.binance.com` | Binance Spot REST base URL |
| `BINANCE_WS_URL` | `wss://stream.binance.com:9443/stream` | Binance combined stream URL |

## Run with Docker

```bash
docker compose up --build
```

`migrate` 컨테이너가 Alembic 마이그레이션을 먼저 적용한 뒤 ETL과 Web을 실행합니다.

- Dashboard: `http://localhost:8000`
- Dependency health: `http://localhost:8000/health`
- Dashboard JSON: `http://localhost:8000/api/dashboard`

서비스를 종료하되 데이터를 유지하려면 `docker compose down`을 사용합니다. PostgreSQL과 Redis
named volume까지 삭제하는 명령은 이력 데이터를 삭제하므로 검증 목적이 아닌 한 사용하지 않습니다.

## Local development

```bash
python -m pip install -e .
alembic upgrade head
python -m app.etl.main
uvicorn app.web.main:app --reload
```

로컬 개발 모드에서도 PostgreSQL과 Redis가 먼저 실행되어 있어야 합니다. 일반적으로는 Docker
Compose 실행 방식을 권장합니다.

## Data recovery behavior

ETL은 시작·재연결 때 최근 `BOOTSTRAP_DAYS` 범위의 완료된 1분봉을 검사합니다. 첫 누락
시점보다 `BACKFILL_OVERLAP_MINUTES`만큼 앞선 지점부터 현재의 마지막 완료 분봉까지 REST로
다시 조회하고, 유니크 키 기반 upsert로 중복 없이 저장합니다.

따라서 ETL이 중단된 시간 동안의 1분봉 이력은 재시작 후 복구됩니다. Dashboard의
`Recent recovery runs`와 `missing / hr`를 통해 결과를 확인할 수 있습니다.

## Verification

```bash
pytest -q
ruff check .
```

강제 종료 복구 검증은 ETL 컨테이너를 몇 분간 중지한 뒤 다시 시작하고, Dashboard의
`Recent recovery runs`와 `missing / hr` 값으로 확인합니다.

상세 완료 기준과 통합 검증 절차는 [docs/checkpoints.md](docs/checkpoints.md)를 참고하세요.
