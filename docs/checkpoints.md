# Delivery checkpoints

각 체크포인트는 구현뿐 아니라 검증과 문서 갱신까지 완료되어야 통과로 표시한다.

| ID | Checkpoint | 완료 조건 | 상태 |
|---|---|---|---|
| C0 | 요구사항·규칙 확정 | 범위, 비목표, 완료 기준, Agent/commit 규칙 문서화 | 완료 |
| C1 | 실행 기반 | Python 의존성, Docker Compose, PostgreSQL·Redis, Alembic 구성 | 완료 |
| C2 | 데이터 모델 | 캔들·체결·체크포인트·수집 이력 schema와 유니크 키 적용 | 완료 |
| C3 | 최초 Backfill | 빈 DB에서 설정 기간의 완료 1분봉을 저장 | 검증 완료 |
| C4 | 실시간 수집 | Binance WebSocket 이벤트 저장 및 Redis 전달 | 검증 완료 |
| C5 | 재연결·복구 | 연결/프로세스 중단 뒤 누락 구간 Backfill 및 상태 기록 | 검증 완료 |
| C6 | 운영 Dashboard | 요약 상태와 종목별 캔들·거래량·누락 구간의 서버 렌더링 화면과 API | 검증 완료 |
| C7 | 품질 검증 | lint, test, Docker 기동, 강제 중지 복구 시나리오 증적 | 검증 완료 |
| C8 | 최종 문서화 | README·지표·AI 사용·검증 결과 최신화 | 검증 완료 |

## Reliability improvement phase

초기 과제의 완료 기준과 별개로, 아래 항목은 운영 복원력을 높이기 위한 다음 단계다.

| ID | Checkpoint | 완료 조건 | 상태 |
|---|---|---|---|
| R0 | RESTORE-PROCESS AS-IS / TO-BE | 기준선·현재 한계·개선 우선순위·검증 조건 문서화 | 완료 |
| R1 | Service liveness | Compose 서비스 재기동 정책과 ETL health 관측 검증 | 검증 완료 |
| R2 | Periodic reconciliation | 연결 유지 중 발생한 완료 1분봉 공백의 자동 발견·Backfill 검증 | 검증 완료 |
| R3 | Observability | reconciliation 상태·실패 추세 Dashboard/API 노출, REST 장애 격리 주입 검증 | 검증 완료 |
| R4 | PostgreSQL backup/restore | 별도 환경 복원과 schema·데이터 정합성 검증 | 검증 완료 |
| R5 | Trade recovery decision | Aggregate Trade 공백 허용, 완료 1분봉만 복구·연속성 기준으로 확정 | 결정 완료 |
| R6 | Backup automation | health gate·lock·checksum·선택적 보관 정리와 host scheduler 실행 절차 | 구현·기본 검증 완료 |

## Mandatory end-to-end scenarios

### Fresh start

1. PostgreSQL volume이 없는 상태에서 서비스를 시작한다.
2. 두 심볼 모두 설정 기간의 1분봉을 백필한다.
3. Dashboard에서 `Recent recovery runs`가 성공이고 누락 캔들 수가 0인지 확인한다.

### Process restart

1. ETL을 최소 3분간 중지한다.
2. ETL을 다시 시작한다.
3. 마지막 완료 캔들부터 현재까지 Backfill이 기록되는지 확인한다.
4. 중복 행 없이 누락 캔들 수가 0인지 확인한다.

### WebSocket recovery

1. ETL의 네트워크 연결 또는 WebSocket을 강제로 종료한다.
2. Dashboard에서 `RECONNECTING` 상태와 reconnect count 증가를 확인한다.
3. 재연결 뒤 `LIVE` 상태, Backfill 성공, 데이터 갱신을 확인한다.
