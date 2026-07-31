# Dashboard metrics

## Pipeline health

| Metric | Definition | Reason |
|---|---|---|
| Connection status | `LIVE`, `RECONNECTING`, `RECOVERED`, or `FAILED` per symbol and source | 가격이 표시되어도 수집기가 중단된 상태를 즉시 구분한다. |
| Last event time | Binance가 전송한 가장 최근 이벤트 시각 | 외부 데이터 흐름의 신선도를 판단한다. |
| Reconnect count | 현재 실행 중 재연결 횟수 | 네트워크 또는 거래소 연결의 불안정성을 발견한다. |
| Missing candles / hour | 최근 완료된 60개 1분봉 중 비어 있는 수 | 데이터 연속성 계약을 운영자가 확인한다. |
| Backfill result | 복구 범위·처리 행 수·성공 여부 | 장애 후 복구가 실제로 수행됐는지 추적한다. |

## Market context

| Metric | Definition | Reason |
|---|---|---|
| Latest price | 가장 최근 수집 캔들의 종가 | 수집 데이터가 실제 시장과 함께 움직이는지 빠르게 확인한다. |
| 24h change | 최신 종가와 약 24시간 전 종가의 변화율 | 급격한 움직임의 운영 맥락을 제공한다. 투자 조언으로 사용하지 않는다. |
| Candle lag | 현재 시각과 가장 최근 캔들 종료 시각의 차이 | 수집 지연을 시장 데이터 기준으로 직관적으로 표현한다. |

Aggregate Trade는 향후 최근 체결·taker flow 테이블을 위한 원본 데이터로 유지한다.
체결 이벤트의 buyer-maker 플래그는 taker 방향을 파생할 때만 사용하며, 투자 신호로 해석하지 않는다.

