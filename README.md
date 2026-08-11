# Lotto Signal Lab

동행복권 로또 6/45 데이터를 **재현 가능하게 수집·저장·분석·백테스트·추천**하기 위한 Python 실험 프로젝트입니다.

> 이 프로젝트의 목적은 "과거 번호가 미래를 예측한다"는 가정을 믿는 것이 아니라,
> 그 가정이 실제 out-of-sample 데이터에서 랜덤보다 나은지 검증하는 것입니다.

## 핵심 원칙

1. **Walk-forward only**: 회차 `N`을 평가할 때 `N-1`까지만 사용합니다.
2. **랜덤 기준선 필수**: 평균 적중 개수의 이론값 `0.8`과 Monte Carlo 기준선을 항상 같이 봅니다.
3. **통계적 유의성 없는 우위는 우위로 표현하지 않습니다.**
4. **수집기와 분석 코드를 분리**합니다. 동행복권 페이지가 바뀌면 `collector.py`만 교체합니다.
5. **자동 구매 기능은 만들지 않습니다.**

## 개발 환경

- Python 3.11+
- SQLite
- httpx + BeautifulSoup
- pytest + ruff

## 설치

```bash
python -m venv .venv

# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

## 사용 순서

### 1. 전체 데이터 동기화

```bash
lotto-lab sync
```

DB 기본 위치:

```text
data/lotto.db
```

수집기는 공식 결과 페이지 `/lt645/result`에서 최신 회차를 읽고, 로컬 DB에 없는 회차만
추가합니다. 회차 데이터는 저장소 소유자가 실제 Windows 클라이언트에서 확인한 공식 사이트의
내부 JSON 경로 `/lt645/selectPstLt645InfoNew.do`를 사용합니다. 응답의 약 10개 회차 중 요청한
회차를 정확히 찾아 저장합니다.

주의: 이 경로는 안정성이 보장된 공개 API가 아니라 공식 사이트의 내부 엔드포인트이며 계약이
변경될 수 있습니다. `collector.py`에 사이트 가정을 격리했고, 예상하지 못한 응답은 명시적으로
실패합니다.
사이트 변경으로 실패하면 예외를 명확히 내고, 아래 CSV import를 임시 fallback으로 사용합니다.

동기화 후 다음 명령으로 공식 사이트의 최신 완료 회차와 로컬 데이터의 연속성 및 번호
무결성을 검사할 수 있습니다.

```bash
lotto-lab validate
```

### 2. CSV fallback

CSV 형식:

```csv
round,draw_date,n1,n2,n3,n4,n5,n6,bonus
1,2002-12-07,10,23,29,33,37,40,16
```

```bash
lotto-lab import-csv data/draws.csv
```

### 3. 번호별 통계

```bash
lotto-lab stats
lotto-lab stats --window 100
lotto-lab stats --uniformity --simulations 5000
```

`--uniformity`는 실제 번호별 출현 편차가 공정한 6/45 추첨에서도 흔히 나올 수준인지 Monte Carlo로 비교합니다.

### 4. Walk-forward 백테스트

```bash
lotto-lab backtest --strategy uniform
lotto-lab backtest --strategy hot
lotto-lab backtest --strategy cold
lotto-lab backtest --strategy hybrid
```

중요 출력:

- `mean_matches`: 회차당 평균 적중 번호 수
- `random_expected_mean`: 공정한 랜덤 선택의 이론 평균 `0.8`
- `hit_3_plus_rate`: 3개 이상 일치 비율
- `monte_carlo_p_value`: 랜덤 전략이 같은 수준 이상의 평균을 낼 확률 추정

예를 들어 `mean_matches = 0.83`만 보고 개선이라고 판단하면 안 됩니다.
`p-value`와 여러 기간에 대한 재현성을 같이 확인해야 합니다.

### 5. 추천 번호 생성

```bash
lotto-lab recommend --strategy auto --count 5 --seed 20260811
```

seed를 고정하면 결과가 재현됩니다.

기본 `auto`는 `hot/cold/hybrid`를 과거 walk-forward로 비교합니다.
가장 좋아 보이는 전략도 3개 후보를 시험한 선택 편향이 있으므로 Bonferroni 보정을 적용하고,
보정된 기준을 통과하지 못하면 **uniform random으로 자동 폴백**합니다.

`hybrid`를 명시적으로 선택하면 최근/중장기 출현 z-score를 합쳐 작은 확률 가중치만 줍니다.
`z_to_log_weight`와 `max_log_tilt`가 과도한 확률 왜곡을 제한합니다.

## 프로젝트 구조

```text
.
├── AGENTS.md
├── README.md
├── pyproject.toml
├── src/
│   └── lotto_lab/
│       ├── backtest.py
│       ├── cli.py
│       ├── collector.py
│       ├── models.py
│       ├── recommend.py
│       ├── statistics.py
│       ├── storage.py
│       └── strategy.py
├── tests/
└── .github/workflows/
```

## Codex에서 먼저 시킬 작업

아래 순서가 좋습니다.

1. `collector.py`를 실제 네트워크에서 검증하고 현재 동행복권 응답 계약에 맞춰 테스트 추가
2. 1회~현재까지 sync 후 데이터 무결성 검사
3. `uniform/hot/cold/hybrid` 전체 walk-forward 비교 리포트 생성
4. 기간별 안정성 테스트: 200회 단위 rolling evaluation
5. pair/triple feature는 baseline을 이길 때만 단계적으로 추가
6. 과적합 방지용 model selection / holdout 구간 설계
7. 리포트 HTML 또는 Streamlit UI 추가

## Codex 시작 프롬프트

```text
Read AGENTS.md and README.md first.

Goal:
Make Lotto Signal Lab a reproducible statistical research project, not a "magic lottery predictor".

First task:
1. Run the full test suite and ruff.
2. Inspect src/lotto_lab/collector.py.
3. Verify the current official dhlottery.co.kr Lotto 6/45 data retrieval flow with real network requests.
4. Make the smallest change needed so `lotto-lab sync` can reliably collect rounds 1..latest.
5. Add regression tests using saved minimal response fixtures.
6. Do not weaken validation or silently fall back to third-party data.
7. Report exact commands run and test results.
```

## 다음 연구 단계

### A. 번호별 편향 검정

단순 출현 횟수뿐 아니라 다음을 테스트할 수 있습니다.

- 전체 기간 frequency
- 20/50/100/300회 rolling frequency
- max deviation
- pair frequency
- gap distribution
- 장기/단기 frequency drift

핵심은 feature를 추가할 때마다 **미래 회차를 보지 않는 백테스트**로만 평가하는 것입니다.

### B. 전략 선택

추후에는 training window 안에서 여러 전략을 비교하고,
검증 구간에서 랜덤보다 의미 있는 차이가 있을 때만 해당 전략을 선택하도록 만들 수 있습니다.

### C. 기대 당첨금 최적화

당첨확률과 별개로 사람들의 선택이 몰릴 법한 조합을 피하는 `crowding heuristic`을
별도 점수로 구현할 수 있습니다. 단, 실제 구매자 선택분포 데이터가 없으면
이는 "당첨확률 개선"이 아니라 공동당첨 가능성에 대한 가설적 휴리스틱으로만 표시해야 합니다.
