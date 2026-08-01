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

### Remaining scenario

WebSocket 연결을 강제로 종료한 뒤 재연결과 Backfill을 확인하는 시나리오는 아직 별도로
실행하지 않았다. 이 검증은 `docs/checkpoints.md`의 WebSocket recovery 절차를 따른다.

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
