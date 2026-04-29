# 🤖 Auto DayTrading Bot

An automated day trading bot for US stocks, built on **Alpaca Markets** and powered by **Claude Haiku** for news sentiment analysis. Runs 24/7 in Docker on any Linux VPS, with auto-deployment via GitHub Actions.

> ⚠️ **Disclaimer:** This bot is for educational and experimental purposes. Trading involves substantial risk of loss. Always test in **paper trading** mode before using real money. Past performance does not guarantee future results.

---

## Features

- **Technical Analysis** — Dual EMA crossover strategy (EMA 9/21) with RSI 14 confirmation
- **News Sentiment Filter** — Fetches recent headlines via Alpaca News API and scores them with Claude Haiku; blocks BUY signals when sentiment is negative
- **Fractional Shares** — Orders use `notional` (dollar amount), not whole shares, enabling fine-grained position sizing
- **Manual SL/TP** — Since Alpaca doesn't support bracket orders for fractional shares, stop-loss and take-profit are monitored on every cycle and closed automatically
- **Persistent State** — Open positions survive bot restarts via a JSON state file
- **T+1 Cash Account Friendly** — Two analysis windows per day (9:35am and 12:30pm ET) plus 30-minute SL/TP monitoring; avoids over-trading with next-day settlement
- **Graceful Degradation** — The bot runs normally without `ANTHROPIC_API_KEY`; sentiment module simply stays silent
- **Docker + GitHub Actions** — One-command deploy; pushes to `master` auto-deploy to your VPS

---

## Architecture

```
main.py  (TradingBot — orchestrator)
│
├── src/config.py      Module 1 — AppConfig dataclass, env validation
├── src/broker.py      Module 1 — Alpaca client initialization, account info
├── src/data_feed.py   Module 2 — Historical OHLCV bars, latest bar/quote
├── src/analysis.py    Module 3 — EMA crossover + RSI signals (AnalysisResult)
├── src/execution.py   Module 4 — Fractional orders, SL/TP monitoring, state persistence
└── src/sentiment.py   Module 5 — Alpaca News → Claude Haiku → sentiment score
```

### Trading Schedule (US Eastern Time)

| Time | Action |
|------|--------|
| 09:35 ET | Full analysis cycle — signals + possible BUY |
| 12:30 ET | Full analysis cycle — signals + possible BUY or SELL |
| Every 30 min | SL/TP monitoring only |

### Signal Logic

```
BUY  → EMA9 crosses ABOVE EMA21 (golden cross) AND RSI < 70
        AND sentiment score ≥ 0 (not blocked by negative news)

SELL → EMA9 crosses BELOW EMA21 (death cross)
        OR RSI > 70 (overbought)

HOLD → No crossover detected
```

### Risk Parameters (configurable in `src/execution.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `risk_per_trade` | 10% | % of available cash invested per trade |
| `stop_loss_pct` | 2% | Max drawdown from entry before closing |
| `take_profit_pct` | 4% | Profit target from entry (1:2 risk/reward ratio) |
| `min_notional` | $1.00 | Minimum order size (Alpaca limit for fractional) |

---

## SOLID Design Principles

This codebase applies Clean Code and SOLID principles throughout:

| Principle | Implementation |
|-----------|---------------|
| **S**ingle Responsibility | Each module has one clear job; `TradingBot` owns state, individual functions own one action |
| **O**pen/Closed | `StrategyConfig` and `RiskConfig` dataclasses let you change parameters without touching logic; signal dispatch uses a dict (add signals without modifying `ejecutar_senal`) |
| **L**iskov Substitution | Consistent return types and dataclass contracts across all modules |
| **I**nterface Segregation | Functions accept only the specific client they need (`TradingClient` or `StockHistoricalDataClient`) |
| **D**ependency Inversion | `get_clients(config)` receives `AppConfig` instead of calling `get_config()` internally; no hidden coupling |

---

## Quick Start (Local / Paper Trading)

### Prerequisites

- Python 3.12+
- [Alpaca Markets account](https://alpaca.markets) (free paper trading account)
- (Optional) [Anthropic API key](https://console.anthropic.com) for sentiment analysis

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/TradingBot.git
cd TradingBot
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
ALPACA_API_KEY=your_paper_api_key
ALPACA_SECRET_KEY=your_paper_secret_key
ALPACA_MODE=paper

# Optional — enables news sentiment module
ANTHROPIC_API_KEY=your_anthropic_key
```

Get your Alpaca paper trading keys at [app.alpaca.markets/paper-trading](https://app.alpaca.markets/paper-trading).

### 3. Run

```bash
python main.py
```

The bot connects, prints an account summary, and enters the scheduler loop. It will act at 9:35am and 12:30pm ET (US Eastern Time).

---

## Docker (Recommended for VPS)

```bash
# Build and run
docker compose up --build -d tradingbot

# View logs
docker logs -f tradingbot-tradingbot-1

# Stop
docker compose down tradingbot
```

The container restarts automatically on crash or VPS reboot (`restart: unless-stopped`).

---

## VPS Deployment (Google Cloud Free Tier)

Google Cloud offers a **permanently free** `e2-micro` instance — enough for this bot (~250 MB RAM).

### 1. Create a free VM

On [cloud.google.com](https://cloud.google.com):
- **Compute Engine → VM instances → Create**
- Machine type: `e2-micro`
- Region: `us-central1`, `us-east1`, or `us-west1` (required for free tier)
- OS: Ubuntu 22.04 LTS
- Disk: 30 GB HDD

### 2. Set up the VPS

SSH into your new VM and run:

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/TradingBot/master/scripts/setup_vps.sh | bash
```

The script installs Docker, clones the repo, and guides you through `.env` configuration.

### 3. Configure GitHub Actions for auto-deploy

Every push to `master` will automatically deploy to your VPS. Add these secrets in your GitHub repo under **Settings → Secrets and variables → Actions**:

| Secret | Value |
|--------|-------|
| `VPS_HOST` | Your VM's external IP address |
| `VPS_USER` | SSH username (e.g. `ubuntu`) |
| `VPS_SSH_KEY` | Full content of your private SSH key (`~/.ssh/id_rsa`) |
| `VPS_PORT` | SSH port (usually `22`) |
| `VPS_APP_DIR` | Absolute path to the project on the VPS (e.g. `/home/ubuntu/TradingBot`) |

After that, every `git push origin master` from your local machine triggers an automatic deploy — no manual SSH needed.

### Manual deploy (without Actions)

```bash
# From inside the VPS
cd ~/TradingBot
bash scripts/deploy.sh
```

---

## Project Structure

```
TradingBot/
├── main.py                    # Entry point — TradingBot class + scheduler
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example               # Template — copy to .env and fill credentials
├── .gitignore
│
├── src/
│   ├── config.py              # AppConfig dataclass + env validation
│   ├── broker.py              # Alpaca client setup, market status, account info
│   ├── data_feed.py           # Historical bars, latest bar/quote
│   ├── analysis.py            # EMA + RSI signal engine (StrategyConfig)
│   ├── execution.py           # Orders, SL/TP monitoring, state persistence (RiskConfig)
│   └── sentiment.py           # News headlines → Claude Haiku → sentiment score
│
├── scripts/
│   ├── setup_vps.sh           # One-shot VPS provisioning script
│   └── deploy.sh              # Manual redeploy script (pull + rebuild + restart)
│
├── logs/                      # Runtime logs and posiciones.json (gitignored)
│
└── .github/
    └── workflows/
        └── deploy.yml         # GitHub Actions: auto-deploy on push to master
```

---

## Customization

### Change the symbols

Edit `SYMBOLS` in `main.py`:

```python
SYMBOLS = ["SPY", "AAPL", "TSLA", "NVDA"]
```

### Change the strategy parameters

Edit `StrategyConfig` defaults in `src/analysis.py`:

```python
DEFAULT_STRATEGY = StrategyConfig(
    ema_fast=9,
    ema_slow=21,
    rsi_period=14,
    rsi_ob=70,
    rsi_os=30,
    min_bars=30,
)
```

### Change risk parameters

Edit `RiskConfig` defaults in `src/execution.py`:

```python
DEFAULT_RISK = RiskConfig(
    risk_per_trade=0.10,   # 10% of available cash per trade
    stop_loss_pct=0.02,    # 2% stop loss
    take_profit_pct=0.04,  # 4% take profit
    min_notional=1.0,
)
```

### Change analysis times

Edit the constants in `main.py`:

```python
ANALISIS_APERTURA = (9, 35)   # 9:35am ET
ANALISIS_MEDIODIA = (12, 30)  # 12:30pm ET
```

---

## Estimated Costs

| Resource | Cost |
|----------|------|
| GCP e2-micro VM (free tier regions) | **$0 / month** |
| Alpaca Markets API | **$0 / month** (free paper & live) |
| Alpaca News API | **$0 / month** (included) |
| Claude Haiku (sentiment, ~2 calls/day) | **~$0.06 / month** |
| **Total** | **< $0.10 / month** |

---

## Requirements

```
alpaca-py>=0.38.0
pandas>=2.0.0
pandas-ta>=0.4.0b0
python-dotenv>=1.0.0
schedule>=1.2.0
anthropic>=0.40.0
```

---

## License

MIT — use freely, modify, share. No warranties. Trade at your own risk.

---

## Contributing

Pull requests are welcome. For major changes please open an issue first to discuss what you'd like to change.

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-improvement`)
3. Commit your changes (`git commit -m 'Add RSI divergence filter'`)
4. Push to the branch (`git push origin feature/my-improvement`)
5. Open a Pull Request
