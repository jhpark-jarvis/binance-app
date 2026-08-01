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
