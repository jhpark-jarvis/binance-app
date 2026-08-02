# Verification log

## 2026-07-31 — Docker integration and data integrity check

### Incident found

ETL의 50ms 실시간 저장 배치에 같은 `(symbol, interval, open_time)`을 가진 진행 중 1분봉
갱신 이벤트가 복수 포함됐다. PostgreSQL은 하나의 `INSERT ... ON CONFLICT DO UPDATE` 문에서
같은 conflict key를 두 번 갱신할 수 없으므로 `CardinalityViolationError`가 발생했다.

### Fix

`app.etl.repository.deduplicate_candles`가 배치 안에서 캔들 identity별 마지막 이벤트만 남기도록
수정했다. 이로써 같은 캔들에 대한 여러 WebSocket 갱신이 한 upsert에 포함돼도 하나의 행만
전달된다.

Dashboard의 최근 1시간 누락 수 계산도 수정했다. 진행 중인 캔들을 최근 60행에 포함해 정상
상태를 `1 missing / hr`로 표시하던 문제를 제거하고, 완료된 캔들 60개만 직접 조회한다.

### Executed checks

- `ruff check .`: pass
- `pytest -q`: 6 passed
- `python -m compileall -q app alembic`: pass
- `docker compose up --build -d etl`: pass
- `docker compose up --build -d web`: pass
- FastAPI `/health`: `{"status":"ok"}`

### PostgreSQL integrity result

| Symbol | Candle rows | Closed 1m candles | Completed-candle gaps | Duplicate candle keys |
|---|---:|---:|---:|---:|
| BTCUSDT | 10,090 | 10,089 | 0 | 0 |
| ETHUSDT | 10,090 | 10,089 | 0 | 0 |

두 심볼의 데이터 범위는 2026-07-24부터 2026-07-31(UTC)까지였고, ETL checkpoint는
두 source(`AGG_TRADE`, `KLINE_1M`) 모두 `LIVE`였다. Dashboard도 두 심볼 모두
`missing_last_hour = 0`, `lag_seconds = 0`을 반환했다.

### Recovery evidence

초기 Backfill은 각 심볼에 10,080개 행을 성공적으로 적재했다. ETL 예외 후에는 두 심볼에
대해 3개 행의 overlap Backfill이 `SUCCESS`로 기록됐고, 이후 checkpoint가 `LIVE`로 복귀했다.

WebSocket 강제 종료·재연결 시나리오 검증 결과는 이 문서의 2026-08-01 항목에 추가한다.

## 2026-08-01 — 의도적 ETL 중단 후 재시작 검증

### Scenario

ETL을 중지한 상태에서 Dashboard가 `STALE`, 이벤트 지연 증가, 누락 1분봉 증가를 표시하는지
확인했다. 이후 모든 Docker 서비스를 다시 실행해 ETL의 process-restart Backfill을 검증했다.

### Result

- BTCUSDT Backfill: 1,275개 행, `SUCCESS`
- ETHUSDT Backfill: 1,275개 행, `SUCCESS`
- 복구 범위: 2026-07-31 13:37 UTC ~ 2026-08-01 10:51 UTC
- 완료 1분봉 누락: 두 심볼 모두 0건
- 중복 캔들 키: 0건
- 네 checkpoint: 모두 `LIVE`, 이벤트 경과 시간 0초
- Dashboard: 두 심볼 모두 `missing_last_hour = 0`, `lag_seconds = 0`
- FastAPI `/health`: `{"status":"ok"}`

이 결과로 최초 Backfill, 의도적 ETL 중단, 재시작 Backfill, 운영 상태의 `STALE → LIVE`
전환을 실제 Docker 환경에서 검증했다.

## 2026-08-01 — Redis AOF 손상 복구 및 서비스 재개 검증

### Incident and recovery

`docker compose start` 시 Redis가 `Bad file format reading the append only file`로 종료했다.
진단 결과 `appendonly.aof.1.incr.aof`의 마지막 176 bytes가 불완전했다. PostgreSQL은 healthy
상태였고, Redis는 영속 데이터 기준이 아니므로 PostgreSQL volume에는 변경을 가하지 않았다.

원본 Redis volume을 `binance-app_redis_aof_backup_20260801_1118`에 먼저 복제한 후,
`redis-check-aof --fix`로 원본 incremental AOF를 464,742 bytes에서 464,566 bytes로 정리했다.
Redis 재기동 뒤 AOF 로드 완료와 `redis-cli ping`의 `PONG`을 확인했다.

### Result after application restart

- `postgres`, `redis`, `etl`, `web` 모두 running/healthy 상태로 복귀
- ETL 재개 Backfill: BTCUSDT 17개, ETHUSDT 17개, 모두 `SUCCESS`
- 네 checkpoint: 모두 `LIVE`, 이벤트 경과 시간 0초
- Dashboard: 두 심볼 모두 `missing_last_hour = 0`, `lag_seconds = 0`
- FastAPI `/health`: `{"status":"ok"}`

Redis 복구는 WebSocket 강제 종료 시나리오를 대체하지 않으며, 해당 별도 검증 결과는 아래에
기록한다.

## 2026-08-01 — WebSocket 강제 종료 및 Backfill 복구 검증

### Scenario

ETL 컨테이너의 네트워크 namespace에 임시 진단 컨테이너를 연결했다. Binance WebSocket 포트
`9443`의 TCP 수신·송신만 약 80초 동안 차단해, PostgreSQL·Redis·Binance REST API는 유지한 채
WebSocket 장애를 재현했다. 테스트가 끝날 때 임시 iptables 규칙은 모두 제거했다.

### Observed state transition

- 기준 reconnect count: 네 checkpoint 모두 2
- 짧은 강제 reset 후: 네 checkpoint 모두 3으로 증가
- 장시간 차단 중: Dashboard에서 `LIVE → STALE → RECONNECTING`을 확인
- 장시간 차단 중 reconnect count: 3에서 5까지 증가
- 차단 해제·재연결 후: 네 checkpoint 모두 `LIVE`, reconnect count 6

### Recovery result

- BTCUSDT Backfill: 3개 행, `SUCCESS`
- ETHUSDT Backfill: 3개 행, `SUCCESS`
- Backfill 범위: 2026-08-01 11:22 UTC ~ 11:24 UTC (UTC)
- Dashboard: 두 심볼 모두 `missing_last_hour = 0`, `lag_seconds = 0`
- FastAPI `/health`: `{"status":"ok"}`

이로써 WebSocket 강제 종료, 상태 전환, 지수 백오프 재시도, 완료 1분봉 Backfill, 실시간 상태
복귀를 실제 Docker 환경에서 검증했다.

## 2026-08-01 — Dashboard SSE 실시간 전달 검증

### Scenario and result

ETL을 정상 실행한 상태에서 Dashboard의 `/events` endpoint에 8초간 연결했다. 연결 확인용
SSE comment 1건을 받고, Redis Pub/Sub를 중계한 이벤트 29건을 수신했다.

- `trade`: 23건 (BTCUSDT·ETHUSDT 체결 이벤트)
- `candle`: 6건 (진행 중 1분봉 갱신 이벤트)
- 연결 뒤 네 checkpoint: 모두 `LIVE`, 이벤트 경과 시간 0초

시간 제한으로 클라이언트가 연결을 종료해 `curl` 종료 코드 28이 반환된 것은 의도된 결과다.
수신 이벤트 형식은 Dashboard JavaScript의 `EventSource` 처리와 호환되는 `data: {json}` SSE
메시지임을 확인했다.

## 2026-08-01 — 종목 상세 차트 API·화면 통합 검증

### Implemented behavior

메인 Dashboard의 BTCUSDT·ETHUSDT 카드를 종목 상세 페이지로 연결했다. 상세 페이지는
PostgreSQL의 실제 1분봉을 native Canvas로 그리며, `1h`, `6h`, `24h`, `7d` 구간 선택,
거래량·최근 체결·종목별 Backfill 이력·완료 1분봉 누락 음영을 제공한다. Redis/SSE는 화면의
갱신 신호로만 사용한다.

### Executed checks

- `GET /markets/BTCUSDT`: 200, 심볼·캔버스·상세 JavaScript·대시보드 복귀 링크 포함
- `GET /api/markets/BTCUSDT/history?window=6h`: 360개 캔들, 완료 분봉 누락 0개, 최근 체결 12개
- `GET /api/markets/ETHUSDT/history?window=7d`: 10,080개 캔들, 완료 분봉 누락 0개
- 지원하지 않는 `window=365d`: 422
- 구성하지 않은 `XRPUSDT`: 404
- `/events` 5초 구독: 16개 이벤트 수신, 이 중 BTCUSDT 이벤트 7개. 이후 1시간 상세 API 재조회도
  정상 수행
- `/health`: `{"status":"ok"}`

이 대화 환경에는 제어 가능한 브라우저 탭이 없어 Canvas의 실제 픽셀 렌더링과 버튼 클릭은 자동
시각 검증하지 못했다. HTTP·API·정적 자산 검증은 완료됐으며, 최종 사용 전 브라우저에서 두
종목 카드와 각 구간 버튼을 한 번씩 확인하면 된다.

## 2026-08-02 — Restore R1/R2: service liveness와 주기적 reconciliation

### Implemented behavior

- `postgres`, `redis`, `etl`, `web`에 Compose `restart: unless-stopped`를 적용했다. `migrate`는
  일회성 migration이므로 재시작 대상이 아니다.
- ETL은 PostgreSQL에 저장된 모든 configured symbol의 `KLINE_1M`, `AGG_TRADE` checkpoint가
  최근 Binance 이벤트를 가진 `LIVE` 또는 `RECOVERED` 상태인지 검사하는 Docker healthcheck를 가진다.
- ETL은 `RECONCILIATION_INTERVAL_SECONDS`(기본 300초)마다 최근 `BOOTSTRAP_DAYS`의 완료 1분봉
  coverage를 검사한다. 공백이 있으면 overlap REST Backfill·upsert 후 같은 범위를 재검사한다.
- 주기 검사마다 `RECONCILIATION` run을 남긴다. 공백이 없으면 0행 `SUCCESS`, 복구가 발생하면
  실제 upsert 행 수가 기록된다.

### Code-level validation

- `ruff check .`: pass
- `pytest -q`: 11 passed
- `python -m compileall -q app alembic`: pass
- `docker compose config --quiet`: pass
- Docker ETL health command: `ETL healthy`
- Compose restart policy inspect: `postgres`, `redis`, `etl`, `web` 모두 `unless-stopped`
- Web PID 1 종료 뒤 Dashboard 컨테이너 재기동, healthcheck `healthy`, `/health`:
  `{"status":"ok"}`

### Silent-gap recovery scenario

빠른 검증을 위해 `.env`는 바꾸지 않고 Compose 실행 시에만 reconciliation 주기를 60초로
주입했다. WebSocket을 유지한 상태에서 `BTCUSDT`의 완료 1분봉 `2026-08-01 17:03:00 UTC`
(`open_time=1785603780000`) 한 건을 삭제했다.

다음 주기에서 `RECONCILIATION`이 공백을 발견해 2분 overlap을 포함한 6개 행을 적재했고,
`RECONCILIATION SUCCESS`로 마감했다. 대상 분봉은 다시 1건 존재했고, BTCUSDT의
`(symbol, interval, open_time)` 중복 키 조회 결과는 0건이었다. 검증 후 ETL 컨테이너는
운영 기본값 `RECONCILIATION_INTERVAL_SECONDS=300`으로 다시 생성했다.

## 2026-08-02 — Restore R3: reconciliation 운영 관측

### Implemented behavior

- Dashboard와 `/api/dashboard`에 심볼별 `reconciliation` 상태를 추가했다.
- 각 항목은 최신 검사 상태·시각, 마지막 성공·실패 시각, 마지막 실패 오류, 최신 run 기준 연속
  실패 횟수를 포함한다.
- 연속 실패는 최신 run이 `FAILED`인 경우에만 마지막 `SUCCESS` 이후의 `FAILED` run 수를 표시한다.
  `RUNNING` 상태 또는 과거에만 실패가 있는 경우에는 0으로 표시해 현재 실패 추세와 구분한다.
- `/health`는 Web의 PostgreSQL·Redis 의존성 확인으로 유지하고, ETL freshness는 ETL healthcheck,
  복구 이력은 Dashboard API로 분리했다.

### Executed checks

- `ruff check .`: pass
- `pytest -q`: 13 passed
- `python -m compileall -q app alembic`: pass
- `node --check app/web/static/dashboard.js`: pass
- `docker compose up --build -d web`: pass
- `/health`: `{"status":"ok"}`
- `/api/dashboard`: BTCUSDT·ETHUSDT 모두 `reconciliation.latest_status = SUCCESS`,
  `consecutive_failures = 0` 반환
- `GET /`: 200, `Reconciliation watch` markup 포함
- `GET /static/dashboard.js`: 200, reconciliation renderer 포함

제어 가능한 브라우저 탭이 없어 카드의 실제 픽셀 렌더링은 자동 확인하지 못했다. 또한 실제
Binance REST 장애를 격리해 `FAILED` run을 생성하는 장애 주입은 아직 수행하지 않았다. 다만
실패 상태·연속 실패 표시 규칙은 단위 테스트로 검증했다.

## 2026-08-02 — Restore R4: PostgreSQL logical backup and isolated restore

### Implemented behavior

- `pg_dump --format=custom --compress=6` 기반의 Windows PowerShell·macOS/Linux backup script를 추가했다.
- dump와 SHA-256 checksum은 Git에서 제외되는 `backups/`에 생성한다.
- restore verification은 운영 Compose volume 대신 이름이 고유한 PostgreSQL 17 container·named volume에서
  실행한다.
- `alembic_version`, 5개 필수 테이블, `market_candles` 복합 PK 중복 0건을 확인한 뒤 임시 대상만 삭제한다.

### Executed check

- dump: `binance_ops_20260802T021213Z.dump` (7,817,400 bytes)
- restored Alembic revision: `20260731_0001`
- restored rows: `market_candles` 21,644 / `aggregate_trades` 384,697 /
  `ingestion_checkpoints` 4 / `ingestion_runs` 224
- duplicate completed-candle keys: 0
- 검증 후 임시 restore volume이 남지 않았고, 원본 Compose 서비스는 모두 healthy 상태 유지

## 2026-08-02 — Restore R5: Aggregate Trade recovery contract

### Decision

- `aggregate_trades`는 최근 체결·taker flow를 위한 실시간 보조 데이터로 유지한다.
- ETL 또는 WebSocket 장애 시간의 Trade 공백은 허용한다. Aggregate Trade REST Backfill은 현재
  시작·재연결·reconciliation 경로에 도입하지 않는다.
- 완료 1분봉만 누락 검사·Backfill·재검증의 연속성 계약으로 유지한다.

### Verification scope

이번 단계는 데이터 계약 결정과 문서 정합성 갱신이므로 DB schema, 환경 변수, Docker 실행 경로를
변경하지 않았다. Trade 행 수 또는 시간 간격을 복구 완료 조건으로 사용하지 않는 것을 README,
운영 규칙, 지표 문서, AS-IS/TO-BE 문서에 일관되게 반영했다.

## 2026-08-02 — Restore R3 follow-up: REST failure handling

### Executed checks

- HTTP mock transport로 Binance Kline REST의 503 응답을 주입해, 클라이언트가 총 5회 요청 후
  `HTTPStatusError`를 반환하는지 확인했다. 테스트에서는 대기만 제거했고 운영 재시도 정책은 변경하지 않았다.
- 실패하는 Kline client를 Collector의 Backfill 경로에 주입해, `RECONCILIATION` run이 `FAILED`,
  처리 행 수 `0`, 오류 메시지 기록으로 마감되고 `KLINE_1M` checkpoint도 `FAILED`로 기록되는지 확인했다.

### Docker integration fault injection

- 운영 `binance-app`과 다른 `binance-r3verify` Compose project와 별도 PostgreSQL·Redis named
  volume을 기동했다.
- 그 프로젝트의 ETL에만 `BINANCE_REST_URL=http://127.0.0.1:9`를 주입했다. 실제 Binance Kline
  Backfill은 연결 실패를 5회 재시도한 뒤 `BACKFILL FAILED`, 처리 행 수 `0`,
  `All connection attempts failed` 오류로 기록됐다.
- ETL은 예외를 종료로 처리하지 않고 `RECONNECTING` checkpoint와 reconnect count `1`을 기록한 뒤
  다음 Backfill을 재시도했다. `/api/dashboard`는 같은 실패 run, 오류 메시지와 checkpoint 상태를 반환했고,
  격리 Web의 `/health`는 `ok`였다.
- 검증 후 `binance-r3verify` 컨테이너·network·두 named volume을 제거했다. 운영 `binance-app`의
  `postgres`, `redis`, `etl`, `web`은 모두 healthy 상태를 유지했다.
