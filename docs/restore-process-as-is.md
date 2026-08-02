# RESTORE-PROCESS AS-IS

## Baseline

- 기준 commit: `fc99dc8` (`docs: 아키텍처 Overview와 ERD 추가`)
- 대상 서비스: `postgres`, `redis`, `migrate`, `etl`, `web`
- 영속 데이터 기준: PostgreSQL named volume
- 이벤트 전달·최신 상태 계층: Redis AOF volume
- 데이터 연속성 계약: `BTCUSDT`, `ETHUSDT`의 **완료된 1분봉**

이 문서는 다음 안정성 개선 작업의 비교 기준이다. 기준 commit 이후의 미커밋 작업(예: 상세
차트 hover tooltip)은 이 문서의 동작 보장에 포함하지 않는다.

## 현재 복구 흐름

```text
ETL 시작 또는 Binance WebSocket 종료
        │
        ▼
최근 BOOTSTRAP_DAYS 범위의 완료 1분봉을 PostgreSQL에서 검사
        │
        ▼
첫 누락 시각 - BACKFILL_OVERLAP_MINUTES부터 Binance REST Kline 조회
        │
        ▼
(symbol, interval, open_time) upsert → ingestion_runs 기록 → LIVE 복귀
```

`aggregate_trades`는 실시간 표시용으로 저장하지만, 현재 복구 연속성 계약과 Backfill 대상은
완료 1분봉뿐이다.

## 자동으로 동작하는 안전장치

| 상황 | 현재 자동 동작 | 데이터 결과 |
|---|---|---|
| ETL 프로세스 종료 | Compose `restart: unless-stopped`가 ETL 컨테이너를 재기동 | 재기동 시 캔들 Backfill 수행 |
| WebSocket 종료·예외 | ETL 내부의 지수 백오프 재시도, checkpoint를 `RECONNECTING`으로 기록 | 재연결 전 캔들 공백은 Backfill 대상 |
| REST Backfill 실패 | `ingestion_runs`를 `FAILED`로 마감하고 ETL 연결 루프가 재시도 | 실패 원인이 해소될 때까지 재시도 |
| 저장 배치 중 중복 이벤트 | 복합 PK와 upsert | 중복 캔들 행 생성 방지 |
| Web·Dashboard 상태 판정 | 마지막 이벤트가 15초를 넘으면 `STALE`로 파생 | 과거 `LIVE` checkpoint의 오인 방지 |
| 정상 종료 신호 | `SIGINT`/`SIGTERM` 수신 시 스트림·Redis·DB engine 정리 | 완료된 commit 이전 작업은 다음 Backfill로 보정 |

## 현재 수동 조치가 필요한 상황

| 상황 | 현재 상태 | 운영자 조치 |
|---|---|---|
| `web` 컨테이너·프로세스 종료 | restart 정책 없음 | `docker compose up -d web` 후 `/health` 확인 |
| PostgreSQL 또는 Redis 컨테이너 종료 | restart 정책 없음 | 장애 원인 해결 후 해당 서비스를 시작하고 `etl`, `web` 상태 확인 |
| Redis AOF 손상 | 자동 수리 없음 | Redis volume 백업 후 `redis-check-aof --fix`; PostgreSQL volume은 건드리지 않음 |
| Docker Desktop·호스트 중단 | Compose 서비스의 전체 기동 보장 없음 | Docker 복구 뒤 `docker compose up -d`, migration·ETL·Web 상태 확인 |
| 연결은 유지되지만 특정 완료 1분봉만 조용히 누락 | 주기적 reconciliation 없음 | ETL 재시작 또는 연결 재수립 뒤 Backfill 수행 |
| 장애 시간의 Aggregate Trade 공백 | Trade Backfill 미구현 | 현재는 공백을 복원하지 않음 |

## 현재 복구 절차

### 1. 먼저 상태를 분류한다

```bash
docker compose ps
docker compose logs --tail 150 etl web postgres redis
curl -fsS http://localhost:8000/health
```

Dashboard에서 `STALE`, `RECONNECTING`, `FAILED`, `missing / hr`, `Recent recovery runs`를 함께
확인한다. `SUCCESS` 이력만으로 현재 ETL이 정상이라고 판단하지 않는다.

### 2. ETL 또는 Binance 연결 문제

ETL이 재기동됐다면 Backfill이 자동으로 수행된다. 수동으로 재검증할 때는 다음을 사용한다.

```bash
docker compose restart etl
docker compose logs --tail 150 etl
```

두 심볼의 새 `BACKFILL` 이력이 `SUCCESS`인지, `missing / hr = 0`인지, 네 checkpoint가
`LIVE`인지 확인한다.

### 3. Web 문제

```bash
docker compose up -d web
curl -fsS http://localhost:8000/health
```

Web은 PostgreSQL과 Redis에 모두 연결할 수 있을 때만 `/health`에서 성공을 반환한다.

### 4. Redis AOF 손상

README의 Redis AOF 복구 절차를 따른다. **원본 Redis volume을 먼저 백업**하며,
PostgreSQL volume은 수정하지 않는다. Redis가 복구된 뒤 ETL을 재시작하면 PostgreSQL 기준
Backfill이 실행된다.

## 검증된 증적

- 빈 PostgreSQL·Redis volume에서 최초 실행: 각 심볼 7일치 완료 1분봉 10,080건 Backfill 성공
- ETL 중단 뒤 재시작: 누락 완료 1분봉 0, 중복 키 0, `STALE → LIVE` 확인
- WebSocket 차단 뒤 재연결: `LIVE → STALE → RECONNECTING → LIVE`, 두 심볼 Backfill 성공 확인
- Redis AOF 손상 복구: Redis 복구 뒤 PostgreSQL 데이터 유지와 ETL 재개 확인

세부 실행 결과는 [verification-log.md](verification-log.md)를 따른다.

## AS-IS 한계와 변경 금지 항목

1. PostgreSQL은 유일한 영속 기준이다. Redis를 복구 기준으로 승격하지 않는다.
2. 완료 1분봉의 PK와 decimal/NUMERIC 저장 정책을 변경하지 않는다.
3. `docker compose down -v`는 복구 명령이 아니라 모든 로컬 수집 데이터를 삭제하는 초기화 명령이다.
4. 단순 restart 정책은 데이터 손상·디스크 부족·잘못된 환경 변수·Binance 장기 장애를 해결하지 않는다.
5. Docker healthcheck의 `unhealthy` 표시는 그 자체로 컨테이너 재시작을 수행하지 않는다.
