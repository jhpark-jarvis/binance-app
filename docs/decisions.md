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

