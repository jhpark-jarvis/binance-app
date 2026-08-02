# Architecture decisions

## AD-001: Python ETL Daemon and FastAPI Web are separate applications

WebSocket 수집기는 장기 실행·재연결·백필 책임을 가지며, 웹 요청의 수명과 분리되어야 한다.
따라서 ETL은 독립 Daemon, Dashboard는 FastAPI App으로 실행한다.

## AD-002: Completed 1-minute candles are the recovery contract

개별 체결은 실시간 수집 중 일부 이벤트를 놓쳤는지 판정하기 어렵고 저장량도 크다.
Kline REST API로 시간 범위를 지정해 복구할 수 있는 완료 1분봉을 연속성 기준으로 삼는다.
Aggregate Trade는 최신 체결과 taker flow 용도로 보존한다.

## AD-003: PostgreSQL is authoritative; Redis is ephemeral

PostgreSQL은 시세·체결·체크포인트·복구 이력을 저장한다. Redis는 ETL에서 Web으로의
실시간 이벤트 전달과 최신 상태의 짧은 캐시만 맡는다. Redis 장애나 Pub/Sub 유실 뒤에도
Web App은 PostgreSQL을 조회해 현재 상태를 복원할 수 있다.

## AD-004: Server-rendered dashboard first

핵심 평가 대상인 데이터 수집·복구·운영 가시성에 시간을 집중하기 위해 FastAPI + Jinja2와
작은 JavaScript만 사용한다. React 등 프론트엔드 프레임워크는 기능·복구 검증 완료 후
상호작용과 시각화 고도화가 필요할 때 도입한다.

## AD-005: Detail charts query PostgreSQL and render missing intervals explicitly

종목 상세 화면은 Redis cache를 조회하지 않고 PostgreSQL의 1분봉·체결·복구 이력을 조회한다.
Redis Pub/Sub와 SSE는 새 데이터 도착을 알리는 갱신 신호로만 사용한다. 따라서 Redis 재기동이나
Pub/Sub 유실 뒤에도 상세 화면을 새로 열면 영속 데이터에서 동일한 차트 상태를 복원한다.

캔들은 외부 프론트엔드 프레임워크나 차트 의존성을 추가하지 않고 native Canvas로 그린다. 완료된
1분봉이 없는 구간은 임의의 가격으로 채우지 않고 음영 공백으로 표시한다. 이는 차트를 투자 판단
화면보다 데이터 연속성 확인을 위한 운영 도구로 유지하기 위한 선택이다.

## AD-006: Periodic reconciliation verifies completed-candle coverage independently of WebSocket state

WebSocket 연결이 유지돼도 특정 이벤트 또는 DB 쓰기만 조용히 누락될 수 있다. 따라서 ETL은
연결·재연결 시점뿐 아니라 설정 주기마다 최근 `BOOTSTRAP_DAYS`의 완료 1분봉 coverage를
PostgreSQL에서 다시 검사한다. 공백이 발견되면 기존 REST Backfill과 overlap upsert를 재사용한
뒤 coverage를 재검증하며, 끝까지 남은 공백은 성공으로 기록하지 않는다.

주기 검사 결과는 `RECONCILIATION` ingestion run으로 남긴다. 데이터가 이미 연속적인 경우도
0행 `SUCCESS` 이력을 남겨 “마지막 자동 검사 시각”을 운영자가 확인할 수 있게 한다. 이력은
관측 용도이며 PostgreSQL의 캔들 데이터나 checkpoint를 대체하지 않는다.

## AD-007: PostgreSQL recovery starts with a logical dump and isolated restore

PostgreSQL volume을 곧바로 덮어쓰는 복원은 현재 상태와 복구 가능성을 함께 잃을 위험이 있다. 따라서
`pg_dump` custom format을 표준 backup으로 사용하고, 항상 이름이 다른 PostgreSQL container·volume에
먼저 `pg_restore`한다. 이 단계에서 Alembic revision, 필수 테이블, 캔들 PK 중복을 확인한다.

실제 운영 volume 교체는 자동화하지 않는다. 데이터 손실 범위, 원본 보존, backup 보관 정책이 환경마다
달라 별도 운영 승인 대상이기 때문이다.
