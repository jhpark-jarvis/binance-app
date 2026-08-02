# Preflight decision checklist

새 기능이나 구조 변경을 시작하기 전 아래 선택과 근거가 여전히 유효한지 확인한다.

| Decision | Selected option | Why | Reconsider when |
|---|---|---|---|
| Primary language | Python | 비동기 ETL, FastAPI, 데이터 처리의 일관성을 확보한다. | 팀 표준 또는 분석 파이프라인 요구가 달라질 때 |
| Application boundary | ETL Daemon / Web 분리 | 장기 실행 수집기의 장애·재시작이 웹 요청 처리와 독립적이어야 한다. | 배포 단위 단순화가 더 큰 가치를 가질 때 |
| Market source | Binance Spot public market data | API key 없이 BTCUSDT·ETHUSDT 공개 시세와 스트림을 제공한다. | 선물·계정 데이터가 요구될 때 |
| Recovery contract | 완료된 1분봉 + 주기적 coverage 검사 | REST 조회와 재검증으로 재시작·재연결·조용한 공백의 연속성을 증명한다. | 더 짧은 해상도 또는 원시 체결 완전성이 요구될 때 |
| Aggregate Trade recovery | 공백 허용, REST Backfill 미도입 | 최근 체결은 실시간 관측 용도이며, 체결 단위 복구의 페이지네이션·제한·보관 비용보다 완료 1분봉의 연속성을 우선한다. | 체결 감사·포렌식 또는 체결 기반 분석이 필요할 때 |
| Database | PostgreSQL | 유니크 제약, upsert, 마이그레이션, 운영 이력을 안정적으로 제공한다. | 대규모 시계열 보관 비용이 우선 과제가 될 때 |
| Redis role | Pub/Sub + short TTL cache | 분리된 ETL/Web의 실시간 전달을 단순하게 만들며 DB를 대체하지 않는다. | 메시지 영속 전달 또는 다중 소비자 재처리가 필요할 때 Redis Streams/queue 검토 |
| Dashboard UI | FastAPI + Jinja2 + small JS + native Canvas | 수집·복구 기능을 먼저 검증하면서도 외부 프레임워크 없이 종목별 캔들·거래량·누락 구간을 표현한다. | 고급 필터·지표·상호작용 요구가 커질 때 |
| Deployment | Docker Compose | 로컬 재현, VM 이전, 서비스 분리와 향후 확장을 준비한다. | 오케스트레이션·고가용성 요구가 생길 때 |
| Backup automation | Host scheduler + logical dump + opt-in retention | 백업을 Docker volume 밖에 남기고, 운영자만 보관 기간·외부 복제 위치를 결정하게 한다. | 중앙 백업 플랫폼 또는 클라우드 object storage가 표준이 될 때 |

## Before implementation checklist

- [ ] 변경이 현재 목표·비목표 안에 있는가?
- [ ] 데이터 복구 계약 또는 유니크 키에 영향을 주는가?
- [ ] DB migration, 환경 변수, Docker 변경이 필요한가?
- [ ] 실패·재시도·재시작 시 동작을 정의했는가?
- [ ] Dashboard에서 새 상태를 관찰해야 하는가?
- [ ] 테스트 또는 재현 절차와 문서 갱신 항목을 정했는가?
