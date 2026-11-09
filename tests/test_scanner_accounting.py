import pytest
from backend.scanner import StockScanner
from backend.tradingview_client import TradingViewClient
from backend.database import init_db, get_config_val, set_config_val

def test_scanner_invariants_and_accounting_offline():
    init_db()
    # Save original watchlist
    original_watchlist = get_config_val("scanner_custom_watchlist", [])
    
    # Unconfigured / Mock client for instant offline execution
    client = TradingViewClient()
    client.is_configured = lambda: False
    client.get_bars = lambda *args, **kwargs: []
    scanner = StockScanner(tv_client=client)
    cfg = scanner.get_config()
    cfg["custom_watchlist"] = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]
    cfg["max_stocks_to_analyze"] = 3
    scanner.get_config = lambda: dict(cfg)

    try:
        res = scanner.scan_once()
        assert res["status"] in ("IDLE", "RUNNING")
        assert "accounting" in res

        acct = res["accounting"]
        assert acct["invariants_satisfied"] is True

        # Invariant 1: Candidates = Failures + Liq_Rejected + Liq_Passed
        assert acct["universe_candidates_count"] == (
            acct["data_retrieval_failures_count"]
            + acct["liquidity_rejected_count"]
            + acct["liquidity_passed_count"]
        )

        # Invariant 2: Liq_Passed = Strategy_Evaluated + Exceeding_Batch
        assert acct["liquidity_passed_count"] == (
            acct["strategy_evaluated_count"]
            + acct["exceeding_batch_count"]
        )

        # Invariant 3: Strategy_Evaluated = Strategy_Rejected + Strategy_Qualified
        assert acct["strategy_evaluated_count"] == (
            acct["strategy_rejected_count"]
            + acct["strategy_qualified_count"]
        )

        # Invariant 4: Strategy_Qualified = Execution_Eligible + Duplicate_Zone
        assert acct["strategy_qualified_count"] == (
            acct["execution_eligible_count"]
            + acct["duplicate_zone_count"]
        )

        # Feed metadata check
        assert "feed_metadata" in res
        assert "TradingView" in res["feed_metadata"]["feed"]
        assert "coverage" in res["feed_metadata"]
    finally:
        set_config_val("scanner_custom_watchlist", original_watchlist)

def test_scanner_data_retrieval_failures_not_fabricated():
    init_db()
    # Save original watchlist so we can restore it in teardown
    original_watchlist = get_config_val("scanner_custom_watchlist", [])

    # Mock configured client where snapshots return missing/zero data
    client = TradingViewClient()
    client.is_configured = lambda: True
    scanner = StockScanner(tv_client=client)

    # Mock get_snapshots returning empty snapshot
    def mock_snapshots(symbols):
        return {
            "EMPTY_SYM": {},
            "ZERO_PRICE_SYM": {"dailyBar": {"c": 0.0, "v": 1000}}
        }

    client.get_snapshots = mock_snapshots
    cfg = scanner.get_config()
    cfg["custom_watchlist"] = ["EMPTY_SYM", "ZERO_PRICE_SYM"]
    # Temporarily override watchlist in memory only — do NOT persist to DB
    # by bypassing save_config and using the in-memory approach via scan_once override.
    # We patch scanner.get_config to return our test cfg without writing to shared DB.
    scanner.get_config = lambda: dict(cfg)

    try:
        res = scanner.scan_once()
        acct = res["accounting"]

        # Both symbols MUST be classified as data retrieval failures, NEVER given dummy $100 price!
        assert acct["data_retrieval_failures_count"] == 2
        assert acct["liquidity_passed_count"] == 0
        assert acct["invariants_satisfied"] is True

        reasons = [r["reason"] for r in res["rejections"]]
        assert any("Missing snapshot" in r or "Zero or missing" in r for r in reasons)
    finally:
        # Always restore the original watchlist — never leave test state in shared DB
        set_config_val("scanner_custom_watchlist", original_watchlist)

