# PostgreSQL backup and isolated restore runbook

## 목적과 범위

PostgreSQL은 이 프로젝트의 캔들·체결·checkpoint·복구 이력의 유일한 영속 원천이다. 이 문서는
논리 백업을 만들고, 원본 Compose volume과 분리된 PostgreSQL 컨테이너에서 해당 dump를 복원·검증하는
절차를 정의한다.

이 절차는 Redis AOF 복구나 `docker compose down -v`를 대체하지 않는다. Redis는 영속 기준이 아니며,
`down -v`는 백업·복원이 아니라 로컬 데이터를 제거하는 초기화 명령이다.

## 안전 규칙

1. 원본 `postgres_data` volume에 `pg_restore`하지 않는다.
2. dump 파일과 SHA-256 checksum을 함께 보관한다.
3. 복원은 항상 이름이 다른 임시 container·volume에서 먼저 검증한다.
4. 검증 스크립트가 만드는 임시 container·volume만 자동 제거한다.
5. `backups/`는 Git에서 제외된다. 백업을 저장소에 commit하거나 비밀번호와 함께 공유하지 않는다.

## Logical dump와 named volume의 역할

| 방식 | 용도 | 장점 | 주의 사항 |
|---|---|---|---|
| `pg_dump --format=custom` | 이관·복원 연습·장기 보관 | PostgreSQL 버전 호환 범위에서 선택적 복원·검증 가능 | host 밖의 안전한 보관 위치와 보존 정책이 필요 |
| named volume snapshot/copy | Docker host의 빠른 로컬 보존 | 동일 host·환경의 신속한 복구에 유용 | PostgreSQL이 실행 중일 때 파일 단위 복사는 일관된 DB backup이 아님 |

이 프로젝트의 표준은 첫 번째 방식이다. volume 복제는 호스트 운영 절차로만 별도 관리한다.

## 백업 생성

사전 조건은 Docker Compose의 `postgres` service가 healthy인 것이다. 스크립트는 container 내부의
`pg_dump`로 custom-format dump를 만든 다음 `backups/`로 복사하고 container의 임시 파일을 제거한다.

### Windows PowerShell

```powershell
.\scripts\backup_postgres.ps1
```

### macOS / Linux

```bash
sh scripts/backup_postgres.sh
```

출력 파일은 다음과 같다.

```text
backups/binance_ops_YYYYMMDDTHHMMSSZ.dump
backups/binance_ops_YYYYMMDDTHHMMSSZ.dump.sha256
```

Windows에서는 `Get-FileHash -Algorithm SHA256 <dump path>`, Linux에서는 `sha256sum -c <checksum path>`,
macOS에서는 `shasum -a 256 <dump path>`로 파일 무결성을 확인할 수 있다.

## 격리 복원 검증

다음 스크립트는 새 PostgreSQL 17 container와 이름이 고유한 named volume을 생성한다. dump를 복원한
뒤 `alembic_version`, 필수 테이블 5개, `market_candles`의 `(symbol, interval, open_time)` 중복 0건을
확인하고, 성공·실패와 관계없이 임시 대상만 정리한다.

### Windows PowerShell

```powershell
.\scripts\verify_postgres_restore.ps1 -BackupPath .\backups\binance_ops_YYYYMMDDTHHMMSSZ.dump
```

### macOS / Linux

```bash
sh scripts/verify_postgres_restore.sh backups/binance_ops_YYYYMMDDTHHMMSSZ.dump
```

성공 시 네 데이터 테이블의 row count와 아래 형식의 결과가 표시된다.

```text
Restore verification passed: revision=<alembic revision>, duplicate_candles=0
```

## 실제 장애 복원 시

1. 기존 Compose 상태, volume 이름, `docker compose ps`, `docker compose logs`를 보존한다.
2. 가장 최근 checksum 검증된 dump를 **격리 복원 검증**한다.
3. 복원한 revision·테이블·중복 키·최근 완료 분봉 coverage를 기록한다.
4. 운영 volume 교체는 별도 변경 승인과 데이터 손실 범위 확인 후 수행한다.
5. 운영 PostgreSQL이 다시 준비되면 `docker compose up -d`로 ETL·Web을 기동하고, ETL Backfill과
   Dashboard의 `missing / hr`, checkpoint, reconciliation 상태를 확인한다.

현재 제공하는 스크립트는 1~3단계까지만 자동화한다. 운영 volume에 대한 in-place restore는 의도적으로
제공하지 않는다.
