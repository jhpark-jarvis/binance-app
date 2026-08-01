# Dashboard metrics

## Pipeline health

| Metric | Definition | Reason |
|---|---|---|
| Connection status | `LIVE`, `RECONNECTING`, `RECOVERED`, or `FAILED` per symbol and source | 가격이 표시되어도 수집기가 중단된 상태를 즉시 구분한다. |
| Last event time | Binance가 전송한 가장 최근 이벤트 시각 | 외부 데이터 흐름의 신선도를 판단한다. |
| Reconnect count | 현재 실행 중 재연결 횟수 | 네트워크 또는 거래소 연결의 불안정성을 발견한다. |
| Missing candles / hour | 최근 완료된 60개 1분봉 중 비어 있는 수 | 데이터 연속성 계약을 운영자가 확인한다. |
| Backfill result | 복구 범위·처리 행 수·성공 여부 | 장애 후 복구가 실제로 수행됐는지 추적한다. |

`LIVE`는 DB에 마지막으로 기록된 상태값만 뜻하지 않는다. Dashboard 조회 시 마지막 Binance
이벤트가 15초를 초과하면 `STALE`로 파생해, ETL 컨테이너가 중지된 경우에도 운영 화면에서
실시간 수집 중단을 구분한다. `Recent recovery runs`의 `SUCCESS`는 과거 Backfill의 성공 기록이며,
현재 수집기의 정상 상태를 의미하지 않는다.

## Market context

| Metric | Definition | Reason |
|---|---|---|
| Latest price | 가장 최근 수집 캔들의 종가 | 수집 데이터가 실제 시장과 함께 움직이는지 빠르게 확인한다. |
| 24h change | 최신 종가와 약 24시간 전 종가의 변화율 | 급격한 움직임의 운영 맥락을 제공한다. 투자 조언으로 사용하지 않는다. |
| Candle lag | 현재 시각과 가장 최근 캔들 종료 시각의 차이 | 수집 지연을 시장 데이터 기준으로 직관적으로 표현한다. |

Aggregate Trade는 향후 최근 체결·taker flow 테이블을 위한 원본 데이터로 유지한다.
체결 이벤트의 buyer-maker 플래그는 taker 방향을 파생할 때만 사용하며, 투자 신호로 해석하지 않는다.

## Market detail chart

| Metric / visual | Definition | Reason |
|---|---|---|
| 1-minute candlestick | PostgreSQL에 저장된 실제 1분봉 OHLC. 진행 중인 현재 봉은 점선으로 구분 | 최신 가격뿐 아니라 시간축의 연속성과 봉 갱신을 함께 본다. |
| Volume bars | 동일한 1분봉의 거래량 | 가격 변화 시 수집된 거래량이 함께 갱신되는지 확인한다. |
| Missing completed-minute shading | 선택 구간에서 완료돼야 했지만 DB에 없는 1분봉 | 없는 데이터를 보간하지 않고, 복구가 필요한 실제 공백을 눈에 띄게 만든다. |
| Recent trades | Aggregate Trade의 최근 12개 체결 | 캔들 갱신 외에도 실시간 체결 흐름이 들어오는지 확인한다. |
| Recovery history | 선택 종목의 최근 Backfill 실행 | 시각적 공백과 복구 이력을 같은 종목 맥락에서 확인한다. |

상세 화면의 구간은 `1h`, `6h`, `24h`, `7d`로 제한한다. 임의로 긴 조회를 허용하지 않아 운영
화면이 PostgreSQL에 과도한 범위 조회를 보내지 않게 한다. 7일 구간은 브라우저 렌더링 시 화면
폭에 맞춰 캔들을 묶어 그리지만, 누락 판정과 API 원본 데이터는 1분 해상도를 유지한다.
