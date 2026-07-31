# AI usage and verification

AI는 다음 범위에서 보조 도구로 활용한다.

- 요구사항을 데이터 연속성, 실시간 수집, 운영 가시성으로 분해
- ETL/Web/DB/Redis 책임 분리와 장애 복구 시나리오 초안 검토
- 테스트 케이스와 문서 구조 초안 작성

AI 제안은 그대로 신뢰하지 않는다. 구현자는 다음으로 결과를 검증한다.

1. Binance 공식 문서의 REST·WebSocket 제약 조건 확인
2. 공개 REST API를 대상으로 Kline 조회 동작 확인
3. 수집 데이터의 유니크 키·upsert·시간대 정책 검토
4. 빈 DB 초기 실행, 강제 중지 후 재시작, 연결 실패를 재현하는 테스트 수행
5. Docker Compose 환경에서 마이그레이션과 서비스 health check 확인

검증하지 못한 환경 의존 결과는 완료로 기록하지 않는다.

