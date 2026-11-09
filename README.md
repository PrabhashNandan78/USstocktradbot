# Antigravity Multi-Stock Bullish Trading System

A quantitative, multi-stock US equities trading bot featuring automated market scanning, deterministic Smart Money Concepts (SMC) technical analysis, TradingView Paper Trading Chrome Extension execution, live position tracking, Telegram alerts, and an operations dashboard.

---

## 1. System Architecture

```mermaid
flowchart TD
    A["TradingView Market Data (@mathieuc/tradingview)"] -->|Consolidated Bars 1H/15M/5M + Snapshots| B["Data Validation Engine (backend/data_validator.py)"]
    B -->|Verified Market Data| C["Stock Scanner (backend/scanner.py)"]
    C -->|Screened Candidates| D["Deterministic Strategy Engine (backend/strategy/)"]
    D -->|1H BOS + 15M Zone + 5M Confirmation| E["Signal Manager (backend/signals.py)"]
    E -->|Signal Dispatched & Deduplication| F["Execution Bridge (backend/execution_bridge.py)"]
    F -->|Mandatory Notification 1| G["Telegram Bot (backend/telegram_bot.py)"]
    F <-->|WebSocket / REST| H["Chrome Extension MV3 (extension/)"]
    H <-->|DOM Automation & Safety Verification| I["TradingView Paper Trading Panel"]
    I -->|Fill Confirmation & PnL Sync| H
    H -->|Position Tracking & Exit Scraper| J["Position Monitor (backend/monitor.py)"]
    J -->|Mandatory Notification 2 (Trade Closed)| G
    J -->|Persisted State| K["SQLite Database (data/trading_bot.db)"]
    L["FastAPI REST & WebSocket Server"] -->|Serves Dashboard & API| M["HTML5/CSS3/JS UI (frontend/)"]
```

### Safety & Separation of Concerns
- **TradingView Market Data**: Powered by the community `@mathieuc/tradingview` library via a local bridge service with zero broker execution capabilities. Consolidates NYSE, NASDAQ, and AMEX quotes and multi-timeframe candles.
- **Automated Data Validation**: Verifies symbol format, timestamps, monotonicity, OHLCV structural consistency ($H \ge \max(O,C)$, $L \le \min(O,C)$, $V \ge 0$), and cross-checks indicators before data enters the strategy engine.
- **TradingView Paper Trading**: All trade simulation executes **inside the TradingView Paper Trading web interface** via the Manifest V3 Chrome Extension.
- **Live Broker Protection**: The Chrome Extension checks the active broker in the Trading Panel. If a live broker (e.g., Interactive Brokers, Tradovate, OANDA, etc.) is connected, **trade execution is immediately halted**.
- **Execution Verification**: Signal generation does **not** register as an execution. Orders are marked `EXECUTED` only after the TradingView Paper Trading panel verifies the fill.

---

## 2. Deterministic Strategy Rules

### 1H – Market Structure (Trend & BOS)
1. **5-Candle Confirmed Pivots**:
   - Pivot High: Higher than 2 candles to the left and 2 candles to the right. Confirmed at candle $i+2$.
   - Pivot Low: Lower than 2 candles to the left and 2 candles to the right. Confirmed at candle $i+2$.
   - Never uses future candle information or unconfirmed pivots.
2. **Bullish BOS**:
   - A completed 1H candle must close above the latest confirmed swing high by at least $0.1 \times \text{ATR}(14)$.
3. **Equilibrium (EQ)**:
   - $\text{EQ} = \frac{\text{Swing High} + \text{Swing Low}}{2}$
   - Demand zones in the discount region ($\le \text{EQ}$) are prioritized.

### 15M – Demand Zone & Displacement
1. **Displacement Candle**:
   - Bullish candle ($\text{Close} > \text{Open}$).
   - Body size $\ge 1.5 \times \text{median body of preceding 10 candles}$.
   - Closes above the previous 5-candle high.
2. **Demand Zone Boundaries**:
   - Zone High = Open of the last bearish candle before displacement within the preceding 5 candles.
   - Zone Low = Low of that bearish candle.
3. **Invalidation**:
   - If a completed 15M candle closes below the demand zone low, the setup is **invalidated**.

### 5M – Entry Confirmation & Scoring Matrix
Every candidate is evaluated on a 100-point deterministic matrix:

| Category | Weight | Signals Evaluated |
| :--- | :---: | :--- |
| **Candlestick** | **25** | Bullish Engulfing, Hammer, Bullish Pin Bar, Morning Star, Three White Soldiers |
| **Momentum** | **20** | RSI crossing above 50, MACD bullish crossover, Increasing MACD histogram |
| **Trend** | **20** | EMA 9 > EMA 21, Price > VWAP, Positive EMA 9 slope |
| **Volume** | **15** | Volume > $1.5 \times \text{20-candle average}$, Bullish volume expansion |
| **Price Action** | **20** | 5M Higher Low, Demand zone rejection wick, Break of minor swing high |
| **Total** | **100** | Category scores are capped at their assigned weights |

**Mandatory Qualification Rules**:
- Total Score $\ge 60 / 100$.
- At least one confirmed Bullish Candlestick or Price Action confirmation.
- 5M confirmation candle **must close bullish** ($\text{Close} > \text{Open}$).
- 1H BOS remains intact and 15M demand zone holds without invalidation.
- **Risk/Reward** $\ge 2.0:1$.

### Risk Management & Order Targets
- **Entry**: Next available 5M candle open.
- **Stop Loss**: $\text{Demand Zone Low} - (0.2 \times \text{5M ATR}(14))$.
- **Take Profit**: Latest confirmed 1H swing high above entry.
- **Risk/Reward**: $\text{RR} = \frac{\text{Take Profit} - \text{Entry}}{\text{Entry} - \text{Stop Loss}} \ge 2.0$.

---

## 3. Telegram Notifications

The bot sends **two mandatory notifications** per trade:

### Mandatory Notification 1 – Signal Dispatched
Sent immediately when the signal is transmitted to the TradingView Extension:
- Symbol
- Direction (`BUY`)
- Signal ID
- Expected Entry Price
- Position Size (Quantity)
- Stop Loss & Take Profit
- Risk/Reward ratio
- Total Signal Score & Breakdown
- Timeframe (`1H BOS + 15M Zone + 5M Entry`)
- Dispatch timestamp
- Execution Status: `SENT_TO_EXTENSION`

### Mandatory Notification 2 – Trade Closed
Dispatched upon detecting trade closure in TradingView Paper Trading:
- Symbol
- Trade ID
- Direction
- Realized Entry Price & Actual Exit Price
- Quantity
- Exit Reason (`TAKE_PROFIT`, `STOP_LOSS`, `MANUAL`)
- Gross P&L, Trading Fees, Net Realized P&L
- Return Percentage (%)
- Holding Duration (Hours, Minutes, Seconds)
- Closing timestamp

---

## 4. Setup and Installation

### A. Python Backend Setup
Requirements: Python 3.10+ (tested on Python 3.14).

```bash
# Navigate to the project directory
cd C:\Users\prabh\.gemini\antigravity\scratch\trading_bot

# Install dependencies
pip install -r requirements.txt
```

### B. Chrome Extension Installation
1. Open Google Chrome and navigate to `chrome://extensions`.
2. Enable **Developer mode** (toggle in top right).
3. Click **Load unpacked**.
4. Select the directory:
   `C:\Users\prabh\.gemini\antigravity\scratch\trading_bot\extension`
5. The extension **TradingView Paper Trading Automated Bridge** will appear in your extension list.

### C. TradingView Setup
1. Open [TradingView Chart](https://www.tradingview.com/chart/).
2. Log into your TradingView account.
3. Open the **Trading Panel** at the bottom of the screen.
4. Click on **Paper Trading by TradingView** and connect.
5. Notice the injected green status pill at the bottom right of the chart:
   `Trading Bot: Active (Paper Trading) | AAPL`

---

## 5. Starting the System

Run the backend server:

```bash
python run_server.py
```

The server binds to `http://127.0.0.1:8000`.

Open your browser to:
[http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## 6. Dashboard Sections

1. **Overview**: Real-time status badges for TradingView Market Data, Extension, Paper Trading, Telegram, and Scanner, plus open positions and total P&L.
2. **Stock Scanner**: Live candidate universe, filtering telemetry, qualified setups table with "Execute in TV" action, and rejection audit logs.
3. **Generated Signals**: Full signal stream with score breakdowns and dispatch controls.
4. **Active Positions**: Open trades actively monitored on TradingView Paper Trading.
5. **Trade History**: Searchable and filterable history of closed trades with realized P&L and duration.
6. **Performance Analytics**: Win rate, profit factor, gross/net P&L, max drawdown, performance by symbol, and performance by score tier.
7. **Integration Test Centre**: Dedicated interactive test buttons for TradingView Market Data, Validation Report, Telegram Bot, Extension, Paper Trading DOM, and End-to-End Workflow with a live diagnostic console and persistent audit log.
8. **Settings**: Configuration for TradingView Market Data Bridge, Telegram notifications, scanner filters, and strategy parameters.

---

## 7. Running the Automated Test Suite

Run the full automated test suite:

```bash
python -m pytest tests/ -v
```

All 45 tests pass with 100% coverage across:
- TradingView market data live retrieval, quote snapshots, and screener querying.
- Automated data verification layer: OHLCV structural consistency ($H \ge \max(O,C)$, $L \le \min(O,C)$, $V \ge 0$), strictly monotonic timestamps, gap detection, and local indicator cross-checking (EMA9, EMA20, ATR14).
- 5-candle pivot high/low confirmation without future candle leaks.
- 1H BOS breakout $\ge 0.1 \times \text{ATR}(14)$ and Equilibrium calculation.
- 15M displacement body size $\ge 1.5 \times \text{median}$ and demand zone detection.
- Candlestick pattern detection (Engulfing, Hammer, Pin Bar, Morning Star, Three Soldiers).
- 5M score calculation with category caps.
- Risk/reward validation ($\ge 2.0$).
- Signal manager CRUD and duplicate zone prevention.
- Telegram notification payload formatting and multi-subscriber management.
- Chrome Extension Paper Trading state machine (4-state verification) and safety halt.
- FastAPI REST endpoints, WebSocket communication, and full end-to-end pipeline simulation.
- Headless Playwright browser test on the dashboard UI.

