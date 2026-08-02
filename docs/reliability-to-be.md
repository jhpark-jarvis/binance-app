# Reliability TO-BE

## Objective

현재의 “ETL 재기동·WebSocket 재연결 뒤 완료 1분봉 Backfill”을 유지하면서, 다음을 추가한다.

1. 서비스 프로세스 종료 뒤 운영자 개입을 줄인다.
2. 연결이 유지돼도 발생할 수 있는 조용한 완료 1분봉 누락을 주기적으로 발견·복구한다.
3. 장애가 감지·복구·미복구 중 어느 상태인지 명확하게 관측한다.
4. PostgreSQL 영속 데이터를 복원할 수 있는 운영 절차를 만든다.

이 단계의 목표는 주문·투자 기능이나 다중 리더 고가용성이 아니다. 완료 1분봉의 연속성과
단일 Compose 환경의 운영 복원력을 강화하는 것이다.

## Target operating model

```text
Container/process failure ─┐
WebSocket interruption ───┼─► service retry / restart
Silent candle gap ────────┘             │
                                        ▼
                           periodic completed-candle reconciliation
                                        │
                                        ▼
                   PostgreSQL coverage check → overlap Backfill → run history
                                        │
                                        ▼
                    health / dashboard / alert channel exposes the result
```

## Workstreams and checkpoints

| ID | Priority | Scope | Completion condition |
|---|---|---|---|
| R0 | Done | AS-IS 기준선과 TO-BE 결정 기록 | 기준 commit·현재 보장·한계·다음 작업이 문서화됨 |
| R1 | Highest | Compose 서비스 liveness | `web`, `postgres`, `redis` 종료 재기동 정책과 ETL health 관측을 검증 — 완료 |
| R2 | Highest | 주기적 candle reconciliation | 연결이 유지된 상태의 인위적 1분봉 공백을 설정된 시간 안에 자동 복구 — 완료 |
| R3 | High | 운영 상태·알림 | `STALE`/`FAILED`/반복 재연결/Backfill 실패를 운영자가 놓치지 않음 |
| R4 | High | PostgreSQL backup/restore runbook | 백업본으로 별도 환경에 복원하고 데이터·schema를 검증 |
| R5 | Decision | Aggregate Trade 복구 계약 | Trade 공백을 허용할지, REST Backfill 범위를 도입할지 결정 |

## R1 — 서비스 liveness

### 구현 방향

- `etl`, `web`, `postgres`, `redis`에 `restart: unless-stopped`를 적용한다. 사용자가
  `docker compose stop` 또는 `down`으로 명시적으로 중지한 서비스는 자동으로 다시 시작하지 않는다.
- `migrate`는 일회성 migration 작업이므로 restart 정책을 적용하지 않는다.
- ETL health는 컨테이너 실행 여부가 아니라 PostgreSQL의 모든 configured symbol·source checkpoint의
  상태와 마지막 Binance 이벤트 최근성을 기준으로 판단한다. `LIVE` 또는 일시적 `RECOVERED` 상태이며
  이벤트가 `ETL_HEALTH_MAX_EVENT_AGE_SECONDS` 이내일 때만 healthy다.
- Docker healthcheck는 문제를 관측하는 장치이고, 종료된 프로세스의 재기동은 Compose restart policy가
  담당한다. healthy가 아닌 실행 중 프로세스를 별도 watchdog으로 재시작하는 범위는 이번 단계에 넣지 않는다.

### 주의 사항

- Redis AOF가 손상된 경우 restart loop는 문제를 고치지 않는다. `redis-check-aof --fix`를
  자동 실행하지 않으며, 항상 backup 후 수동·명시적 복구를 유지한다.
- PostgreSQL의 데이터 손상·디스크 부족은 restart 대상이 아니라 원인 분석과 backup/restore 대상이다.

### 완료 검증

1. ETL·Web·Redis·PostgreSQL 프로세스를 각각 종료해 재기동 정책을 검증한다.
2. ETL 재기동 뒤 Backfill, checkpoint `LIVE`, 누락 0을 확인한다.
3. Web 재기동 뒤 `/health`, Dashboard, SSE 연결을 확인한다.
4. 영속 volume을 유지한 재기동에서 PostgreSQL 데이터가 변하지 않는지 확인한다.

## R2 — 주기적 completed-candle reconciliation

### 구현 방향

- ETL이 연결된 상태에서도 설정 주기(권장: 5분)마다 최근 `BOOTSTRAP_DAYS`의 완료 1분봉
  coverage를 확인한다.
- 누락이 있으면 기존 Backfill 함수를 재사용하고 overlap부터 idempotent upsert한다.
- REST 적재 뒤 동일 범위를 재조회한다. 남은 공백이 하나라도 있으면 run을 `SUCCESS`로 마감하지 않는다.
- 정상적으로 누락이 없을 때도 `RECONCILIATION` 0행 `SUCCESS` 이력을 남겨 마지막 자동 검사 시각을
  Dashboard의 최근 run 목록에서 확인할 수 있게 한다.
- ETL의 단일 연결 루프 안에서 reconciliation과 재연결 Backfill을 순차 실행한다. 최초 버전은 다중
  ETL 리더를 지원하지 않으므로 별도 distributed lock은 도입하지 않는다.
- 새 설정값이 필요하면 `.env`가 아니라 `.env.example`과 README에만 추가한다.

### 완료 검증

1. WebSocket을 끊지 않은 상태에서 완료 1분봉 한 건을 테스트 환경에서 제거한다.
2. 다음 reconciliation 주기 안에 공백이 발견되고 `RECONCILIATION SUCCESS`가 기록되는지 확인한다.
3. 원래 PK 기준 중복 행이 없는지, 완료 분봉 공백이 0인지 확인한다.
4. REST 장애·rate limit 상황에서 retry와 실패 이력이 올바르게 기록되는지 확인한다.

## R3 — 관측과 알림

### 구현 방향

- Dashboard와 `/api/dashboard`에 심볼별 “마지막 reconciliation”, “마지막 성공·실패”, “마지막 오류”,
  “연속 실패 횟수”를 추가한다. `ingestion_runs`를 원천으로 사용하며 별도 상태 저장소는 만들지 않는다.
- `/health`는 PostgreSQL·Redis에 대한 Web 의존성 확인으로 유지한다. ETL freshness와 reconciliation
  상태는 Dashboard API 및 ETL 컨테이너 healthcheck에서 확인하도록 책임을 구분한다.
- 외부 알림 채널은 아직 선택하지 않는다. 첫 구현은 상태 API·Docker logs·Dashboard 관측을
  확실히 하고, 이후 Slack/메일/모니터링 시스템 연동을 결정한다.

### 완료 검증

- `STALE`, `FAILED`, 반복 `RECONNECTING`, Backfill 실패를 각각 재현했을 때 원인과 시각이
  화면·API·로그에서 일관되게 확인된다. — Dashboard/API 구현 완료, 실패 주입 시나리오 검증은
  외부 Binance REST 장애를 격리할 수 있는 환경에서 후속 수행

## R4 — PostgreSQL backup and restore

### 구현 방향

- PostgreSQL named volume의 단순 복제와 논리 백업(`pg_dump`)의 사용 목적을 분리한다.
- 백업 파일의 보관 위치·보관 주기·복원 연습 주기를 운영 환경별로 결정한다.
- 복원은 기존 운영 volume을 덮어쓰지 않고 별도 이름의 검증 환경에서 먼저 수행한다.
- schema revision, 캔들 건수, PK 중복, 최근 완료 분봉 누락 여부를 복원 검증 항목으로 둔다.

### 완료 검증

- 별도 PostgreSQL volume 또는 컨테이너에 복원한 뒤 Alembic revision과 데이터 정합성을 확인한다.

## R5 — Aggregate Trade contract decision

현재 `aggregate_trades`는 실시간 최근 체결 표시용이다. 다음 중 하나를 명시적으로 선택한다.

| Option | Effect |
|---|---|
| 현재 정책 유지 | 장애 시간의 Trade 공백을 허용하고, 완료 1분봉만 연속성 보장 |
| Trade Backfill 도입 | Binance Aggregate Trade REST 조회의 시간·ID 범위, rate limit, 대량 적재 정책을 추가 설계 |

R5를 결정하기 전에는 Trade 행 수를 캔들 연속성의 완료 기준으로 사용하지 않는다.

## Implementation rules

1. R1부터 R4까지는 분리된 commit point로 진행한다.
2. 각 단계는 코드·Compose·문서·재현 가능한 검증 기록을 함께 갱신한다.
3. 새로운 자동 삭제·자동 복구 명령은 기존 데이터를 덮어쓰지 않도록 먼저 대상 volume과 backup을 확인한다.
4. PostgreSQL 스키마 변경은 Alembic revision을 포함한다.
5. Docker 통합 검증을 하지 못한 항목은 완료로 표시하지 않는다.

## Next implementation recommendation

R1·R2가 완료됐으므로 다음 작업은 **R3 운영 상태·알림**이다. 우선 Dashboard 또는 상태 API에서
마지막 reconciliation 시각·성공/실패·연속 실패 횟수를 분명히 보여 주고, 외부 알림 채널은 그
관측 기준이 안정된 뒤 선택한다. Redis AOF 손상 자동 수리나 PostgreSQL volume 덮어쓰기는 이
단계에도 포함하지 않는다.
