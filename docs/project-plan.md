# Project direction and goal

## Direction

이 프로젝트는 Binance Spot 공개 시장 데이터를 이용하는 내부 운영 도구다. 핵심은 가격을
보여 주는 화면이 아니라, 데이터 수집이 정상인지와 장애 뒤 데이터가 복구됐는지를 운영자가
빠르게 판단할 수 있게 하는 것이다.

초기 버전은 Python 중심으로 구성한다.

```text
Binance REST / WebSocket
            │
            ▼
      Python ETL Daemon ──► PostgreSQL
            │                    │
            └──── Redis ───► FastAPI Dashboard
```

- ETL Daemon은 장기 실행, 수집, 백필, 재연결, 저장을 담당한다.
- FastAPI는 조회 API, 서버 렌더링 화면, 브라우저 실시간 이벤트 전달을 담당한다.
- PostgreSQL은 복구 판단을 포함한 유일한 영속 데이터 원천이다.
- Redis는 이벤트 전달과 짧은 최신 상태 캐시로만 사용한다.
- 메인 Dashboard는 전체 운영 상태를 요약하고, 종목 카드는 PostgreSQL 기반 상세 차트 화면으로
  이동한다. 상세 화면은 실제 1분봉·거래량·누락 구간을 함께 표시한다.

프론트엔드 프레임워크는 기능·복구 검증이 완료된 뒤, 상호작용·시각화 고도화가 필요할 때
도입 여부를 다시 판단한다.

## Goals

1. `BTCUSDT`, `ETHUSDT`의 실시간 Aggregate Trade와 1분봉을 수집한다.
2. 빈 DB의 최초 실행 시 설정된 기간의 완료 1분봉을 백필한다.
3. 프로세스·연결 장애 뒤, 그리고 연결 유지 중의 주기 검사에서 누락된 완료 1분봉을 중복 없이 복구한다.
4. 운영자가 연결 상태, 최근 수신 시각, 누락 여부, 백필 결과를 Dashboard에서 확인한다.
5. 운영자가 종목별 상세 화면에서 실제 1분봉 차트와 데이터 공백을 확인한다.
6. Docker Compose로 개발·검증 환경을 재현한다.
7. PostgreSQL 논리 백업을 host scheduler로 자동 실행할 수 있고, 격리 restore verification과 보관 정책을 운영자가 명시한다.

## Definition of done

아래 항목이 모두 충족되고 검증 결과가 문서화됐을 때 초기 버전을 완료로 판단한다.

- 최초 실행과 재시작 Backfill 시나리오가 성공한다.
- 완료 1분봉의 복구 대상 구간에 누락이 없다.
- 중복 백필을 수행해도 유니크 키와 upsert로 중복 행이 생성되지 않는다.
- ETL과 Web이 독립 컨테이너로 실행된다.
- Dashboard의 운영 지표가 DB 상태와 일치한다.
- 종목별 상세 화면이 PostgreSQL의 실제 1분봉을 그리고, 누락된 완료 분봉을 공백으로 표현한다.
- 백업 script가 healthy PostgreSQL에서 checksum을 가진 logical dump를 만들고, 격리 restore verification을 수행한다.
- README, 결정 근거, Agent handoff, 검증 결과가 최신이다.
