# Project definition and rules

## Objective

Binance Spot의 `BTCUSDT`, `ETHUSDT` 실시간 체결·시세를 수집하고, 장애 후 누락된
구간을 복구하며, 운영자가 데이터 신선도와 수집 상태를 확인할 수 있는 대시보드를 제공한다.

구현의 우선순위는 화면의 장식이 아니라 데이터 연속성, 수집 안정성, 장애 복구 가능성,
그리고 이를 확인할 수 있는 운영 가시성이다.

## Scope

- Python 기반의 독립 ETL Daemon과 FastAPI Web App
- Binance 공개 REST API 및 WebSocket Streams 사용
- 기본 이력: 최근 7일, 1분봉 기준 연속성 보장
- PostgreSQL 영속화, Redis 이벤트 전달 및 최신 상태 캐시
- Docker Compose 기반의 재현 가능한 로컬 실행

## Non-goals

- 주문 실행, 사용자 계정·자산 데이터, 투자 조언
- 최초 버전에서의 다중 ETL 리더 운영
- 전체 Binance 과거 이력의 무제한 적재

## Data contract

1. 완료된 1분봉은 `(symbol, interval, open_time)` 기준으로 하나만 존재한다.
2. 재시작·재연결 후 첫 누락 완료 1분봉보다 설정된 overlap만큼 앞선 지점부터
   현재 마지막 완료 1분봉까지 백필한다.
3. 가격과 수량은 부동소수점이 아닌 decimal 정책으로 저장한다.
4. 모든 DB 시간은 UTC이며, 이벤트 발생 시간과 시스템 수신 시간을 구분한다.
5. PostgreSQL이 유일한 영속 원천이며 Redis는 복구 기준으로 사용하지 않는다.
6. Aggregate Trade는 실시간 보조 데이터다. 장애 시간의 Trade 공백은 허용하며, 완료 1분봉만
   연속성 검사와 Backfill의 대상이다.

## Operational rules

1. Binance 연결 종료와 API 실패는 재시도 가능한 운영 이벤트로 취급한다.
2. 저장은 유니크 키와 upsert를 통해 멱등적이어야 한다.
3. API 제한 응답에는 `Retry-After`와 지수 백오프를 준수한다.
4. Dashboard는 가격보다 수집 상태·데이터 지연·누락 여부를 우선 표시한다.
5. 완료 기준에는 강제 중지 후 Backfill 복구 검증이 반드시 포함된다.
6. PostgreSQL 백업은 논리 dump와 checksum을 함께 생성하고, 운영 volume이 아닌 격리 대상에서 먼저
   복원 검증한다. 보관 파일 삭제는 명시적으로 설정한 기간에만 수행한다.

## Working rules

1. 기능 변경 전에는 이 문서와 `docs/preflight-decisions.md`의 범위·결정 근거를 확인한다.
2. ETL, Web, DB schema, Docker 설정의 책임을 섞지 않는다.
3. 기존 동작을 바꾸는 변경에는 단위 테스트 또는 재현 가능한 수동 검증 절차를 함께 둔다.
4. 환경별 값과 비밀값은 코드에 넣지 않는다. `.env`는 사용자 로컬 설정이고,
   `.env.example`만 저장소에 유지한다.
5. 마이그레이션이 필요한 스키마 변경은 Alembic revision을 반드시 포함한다.
6. 미검증 사항, 외부 환경 의존 사항, 알려진 제약은 README 또는 handoff 문서에 명시한다.
7. AI Agent는 사용자가 명시적으로 요청하지 않는 한 commit, push, 배포를 실행하지 않는다.

## Commit-point rule

다음 중 하나에 해당하면 작업을 잠시 정리해 사용자가 commit할 수 있게 돕는다.

- 독립적으로 실행 가능한 기능 한 단위가 완성된 경우
- DB schema 또는 Docker/환경 설정이 바뀐 경우
- 장애 복구·데이터 정합성에 영향을 주는 변경이 끝난 경우
- 여러 파일에 걸친 리팩터링 또는 문서 기준 변경이 끝난 경우

정리에는 반드시 다음을 포함한다.

1. 변경 목적과 사용자 영향
2. 변경 파일 및 핵심 구현 내용
3. 실행한 검증과 결과
4. 필요한 환경 변수·마이그레이션·실행 순서
5. 남은 위험 또는 후속 작업
6. 권장 commit message

사용자가 직접 commit한다. Agent는 요청받았을 때만 Git commit을 수행한다.
