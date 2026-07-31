# Agent handoff guide

이 저장소에서 작업하는 Agent는 먼저 `docs/project-rules.md`,
`docs/project-plan.md`, `docs/preflight-decisions.md`, `docs/checkpoints.md`를 읽는다.

## Current architecture

- `app/etl`: Binance REST/WebSocket 수집, Backfill, 재연결, PostgreSQL 저장
- `app/web`: FastAPI API, Jinja2 Dashboard, Redis Pub/Sub → SSE 중계
- `app/core`: 설정, DB 연결, SQLAlchemy 모델, Redis 이벤트 공통 계층
- `alembic`: PostgreSQL schema migration
- `compose.yaml`: postgres, redis, migrate, etl, web 서비스

## Non-negotiable data rules

1. 완료된 1분봉의 primary identity는 `(symbol, interval, open_time)`이다.
2. Aggregate Trade의 primary identity는 `(symbol, aggregate_trade_id)`이다.
3. 가격·수량은 float가 아닌 decimal/NUMERIC으로 보존한다.
4. PostgreSQL만 영속 데이터의 기준이다. Redis만으로 상태를 복구하지 않는다.
5. 재시작·재연결 시 첫 누락 캔들보다 overlap만큼 앞서부터 완료 캔들을 다시 적재한다.

## Development workflow

1. 작업 전 `docs/preflight-decisions.md`의 체크리스트를 확인한다.
2. 코드·migration·문서 변경을 함께 반영한다.
3. 최소 `ruff check .`, `pytest -q`, `python -m compileall -q app alembic`을 실행한다.
4. 외부 연동 변경은 가능하면 실제 Binance 공개 API로 가볍게 확인한다.
5. Docker 통합 검증을 못 했다면 완료라고 표현하지 않고 `docs/checkpoints.md`에 남긴다.

## Environment

- 사용자는 `.env`를 직접 관리한다. Agent는 `.env`를 만들거나 수정하지 않는다.
- 필요한 값은 `.env.example`에만 추가한다.
- Docker Desktop이 실행 중이어야 `docker compose up --build` 통합 검증이 가능하다.

## Commit handoff

Agent는 자동으로 commit하지 않는다. 의미 있는 commit point에서 다음을 사용자에게 정리한다.

- 목적과 사용자 영향
- 주요 변경 파일
- 검증 결과
- migration·환경 변수·실행 순서
- 알려진 제한과 후속 작업
- 권장 commit message

