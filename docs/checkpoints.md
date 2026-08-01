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
| C6 | 운영 Dashboard | 상태·지연·누락·백필 이력의 서버 렌더링 화면과 API | 검증 완료 |
| C7 | 품질 검증 | lint, test, Docker 기동, 강제 중지 복구 시나리오 증적 | 검증 완료 |
| C8 | 최종 문서화 | README·지표·AI 사용·검증 결과 최신화 | 검증 완료 |

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
