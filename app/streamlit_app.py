import json
import os
import sqlite3
from datetime import date as date_cls, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DB_DEFAULT = ROOT / "money_diary.db"
SCHEMA_PATH = ROOT / "schema.sql"

env_path = ROOT / ".env"
load_dotenv(env_path)


try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


def get_conn(db_path: Path) -> sqlite3.Connection:
    need_init = not db_path.exists()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    if need_init:
        conn.executescript(schema_sql)
        conn.commit()
    else:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        )
        views = {row[0] for row in cur.fetchall()}
        required = {
            "v_portfolio_total",
            "v_currency_exposure",
            "v_valuation_enriched",
        }
        if not required.issubset(views):
            conn.executescript(schema_sql)
            conn.commit()
    return conn


def upsert_asset(conn: sqlite3.Connection, ticker: str, ccy: str, name: str | None):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO assets (ticker, ccy, name)
        VALUES (?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
          ccy = excluded.ccy,
          name = excluded.name
        """,
        (ticker, ccy, name),
    )
    conn.commit()


def upsert_fx(conn: sqlite3.Connection, d: str, ccy: str, rate: float):
    pair = f"{ccy}JPY"
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO fx_rates (date, pair, rate)
        VALUES (?, ?, ?)
        ON CONFLICT(date, pair) DO UPDATE SET
          rate = excluded.rate
        """,
        (d, pair, rate),
    )
    conn.commit()


def upsert_snapshot(conn: sqlite3.Connection, d: str, ticker: str, qty: float, price_ccy: float):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO snapshots (date, ticker, qty, price_ccy)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(date, ticker) DO UPDATE SET
          qty = excluded.qty,
          price_ccy = excluded.price_ccy
        """,
        (d, ticker, qty, price_ccy),
    )
    conn.commit()


def q_all(conn: sqlite3.Connection, sql: str, params: tuple = ()):
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def fetch_asset_prices(
    conn: sqlite3.Connection,
    tickers: list[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    if not tickers or not table_exists(conn, "asset_prices"):
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(tickers))
    sql = f"""
        SELECT date, ticker, close
        FROM asset_prices
        WHERE date BETWEEN ? AND ?
          AND ticker IN ({placeholders})
        ORDER BY date, ticker
    """
    rows = q_all(conn, sql, (start, end, *tickers))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_fx_history(
    conn: sqlite3.Connection,
    pairs: list[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    if not pairs or not table_exists(conn, "fx_rates"):
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(pairs))
    sql = f"""
        SELECT date, pair, rate
        FROM fx_rates
        WHERE date BETWEEN ? AND ?
          AND pair IN ({placeholders})
        ORDER BY date, pair
    """
    rows = q_all(conn, sql, (start, end, *pairs))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def get_portfolio_date_range(conn: sqlite3.Connection) -> tuple[date_cls | None, date_cls | None]:
    if not table_exists(conn, "v_portfolio_total"):
        return (None, None)
    rows = q_all(
        conn,
        "SELECT MIN(date) AS min_date, MAX(date) AS max_date FROM v_portfolio_total",
    )
    if not rows:
        return (None, None)
    row = rows[0]
    min_date = row.get("min_date")
    max_date = row.get("max_date")
    if not min_date or not max_date:
        return (None, None)
    return (
        datetime.strptime(min_date, "%Y-%m-%d").date(),
        datetime.strptime(max_date, "%Y-%m-%d").date(),
    )


def fetch_portfolio_history(
    conn: sqlite3.Connection,
    start: str,
    end: str,
) -> pd.DataFrame:
    if not table_exists(conn, "v_portfolio_total"):
        return pd.DataFrame()
    rows = q_all(
        conn,
        """
        SELECT date, total_value_jpy
          FROM v_portfolio_total
         WHERE date BETWEEN ? AND ?
         ORDER BY date
        """,
        (start, end),
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_currency_history(
    conn: sqlite3.Connection,
    start: str,
    end: str,
) -> pd.DataFrame:
    if not table_exists(conn, "v_currency_exposure"):
        return pd.DataFrame()
    rows = q_all(
        conn,
        """
        SELECT date, ccy, value_jpy
          FROM v_currency_exposure
         WHERE date BETWEEN ? AND ?
         ORDER BY date, ccy
        """,
        (start, end),
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def get_attribution_for_date(conn: sqlite3.Connection, date: str):
    return q_all(
        conn,
        """
        SELECT ticker, delta_total, delta_price, delta_fx, delta_cross, flow
          FROM v_attribution
         WHERE date = ?
         ORDER BY CASE WHEN ticker = 'PORTFOLIO' THEN 0 ELSE 1 END, ticker
        """,
        (date,),
    )


def get_attribution_history(conn: sqlite3.Connection, limit: int | None = None):
    sql = """
        SELECT date, ticker, delta_total, delta_price, delta_fx, delta_cross, flow
          FROM v_attribution
         ORDER BY date, CASE WHEN ticker = 'PORTFOLIO' THEN 0 ELSE 1 END, ticker
    """
    rows = q_all(conn, sql)
    if limit:
        rows = rows[-limit:]
    return rows


def get_currency_exposure_for_date(conn: sqlite3.Connection, date: str):
    return q_all(
        conn,
        """
        SELECT ccy, value_jpy
          FROM v_currency_exposure
         WHERE date = ?
         ORDER BY value_jpy DESC
        """,
        (date,),
    )


def get_portfolio_total_for_date(conn: sqlite3.Connection, date: str):
    rows = q_all(
        conn,
        "SELECT total_value_jpy FROM v_portfolio_total WHERE date = ?",
        (date,),
    )
    return rows[0]["total_value_jpy"] if rows else None


def get_portfolio_totals_history(conn: sqlite3.Connection, limit: int | None = None):
    sql = "SELECT date, total_value_jpy FROM v_portfolio_total ORDER BY date"
    rows = q_all(conn, sql)
    if limit:
        rows = rows[-limit:]
    return rows


def openai_available() -> bool:
    return OpenAI is not None and bool(os.getenv("OPENAI_API_KEY"))


def build_day_prompt(date: str, attribution, exposure, total_value) -> str:
    payload = {
        "date": date,
        "portfolio_total_jpy": total_value,
        "attribution": attribution,
        "currency_exposure": exposure,
    }
    return (
        "You are a financial analyst who explains daily portfolio movements in Japanese. "
        "Summarize the key drivers (price, FX, cross, flow) for the portfolio on the given date. "
        "Highlight notable tickers and percent contributions if obvious."
        "\n\nData(JSON):\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\nOutput format: short bullet list in Japanese with overall conclusion."
    )


def build_history_prompt(attribution_history, totals_history) -> str:
    payload = {
        "attribution_history": attribution_history,
        "portfolio_totals": totals_history,
    }
    return (
        "You are a financial analyst. Review the entire attribution history and portfolio totals "
        "to identify major turning points, recurring drivers, and any long-term trends."
        " Provide insights in Japanese, covering key dates, main contributing tickers, and suggestions "
        "for what deserves attention.\n\nData(JSON):\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\nOutput format: short paragraphs with bullet list of highlights in Japanese."
    )


def summarize_with_openai(prompt: str) -> str:
    if OpenAI is None:
        raise RuntimeError("openai パッケージがインストールされていません")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY が設定されていません")
    client = OpenAI(api_key=api_key)
    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=prompt,
        )
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"OpenAI API 呼び出しに失敗しました: {exc}")

    text = getattr(response, "output_text", "")
    if text:
        return text.strip()
    # fallback for older client structures
    chunks = []
    for item in getattr(response, "output", []) or []:
        for block in getattr(item, "content", []) or []:
            if getattr(block, "type", None) == "output_text":
                chunks.append(getattr(block, "text", ""))
    if chunks:
        return "\n".join(chunks).strip()
    return str(response)
def get_prev_snapshot(conn: sqlite3.Connection, ticker: str, d: str):
    rows = q_all(
        conn,
        """
        SELECT date, qty, price_ccy
          FROM snapshots
         WHERE ticker = ? AND date < ?
         ORDER BY date DESC
         LIMIT 1
        """,
        (ticker, d),
    )
    return rows[0] if rows else None


def fx_missing_for_date(conn: sqlite3.Connection, d: str):
    return q_all(
        conn,
        """
        WITH need AS (
          SELECT DISTINCT a.ccy AS ccy
            FROM snapshots s
            JOIN assets a ON a.ticker = s.ticker
           WHERE s.date = ? AND a.ccy <> 'JPY'
        )
        SELECT n.ccy || 'JPY' AS pair
          FROM need n
         WHERE NOT EXISTS (
           SELECT 1 FROM fx_rates f WHERE f.date = ? AND f.pair = n.ccy || 'JPY'
         )
        ORDER BY pair
        """,
        (d, d),
    )


def get_asset_meta(conn: sqlite3.Connection) -> dict[str, dict[str, str | None]]:
    meta: dict[str, dict[str, str | None]] = {}
    for row in q_all(conn, "SELECT ticker, ccy, name FROM assets"):
        meta[row["ticker"]] = {"ccy": row["ccy"], "name": row.get("name") if isinstance(row, dict) else None}
    return meta


def get_price_ccy(conn: sqlite3.Connection, ticker: str, date: str) -> float | None:
    rows = q_all(
        conn,
        "SELECT close FROM asset_prices WHERE ticker = ? AND date = ?",
        (ticker, date),
    )
    if not rows:
        return None
    return float(rows[0]["close"])


def get_fx_rate(conn: sqlite3.Connection, ccy: str, date: str) -> float | None:
    if ccy == "JPY":
        return 1.0
    rows = q_all(
        conn,
        "SELECT rate FROM fx_rates WHERE pair = ? AND date = ?",
        (f"{ccy}JPY", date),
    )
    if not rows:
        return None
    return float(rows[0]["rate"])


def main():
    st.set_page_config(page_title="Money Diary", layout="wide")
    st.title("Money Diary – ローカルGUI")

    db_path_str = st.sidebar.text_input("DBパス", str(DB_DEFAULT))
    db_path = Path(db_path_str).expanduser().resolve()
    conn = get_conn(db_path)

    sel_date = st.sidebar.date_input("対象日付", value=date_cls.today())
    sel_date_str = sel_date.strftime("%Y-%m-%d")

    tabs = st.tabs(["Assets", "FX", "Snapshots", "Views", "Charts"])
    tab_assets, tab_fx, tab_snapshots, tab_views, tab_charts = tabs

    with tab_assets:
        st.subheader("Assets（銘柄マスタ）")
        with st.form("asset_form"):
            ticker = st.text_input("Ticker", placeholder="VTI").strip()
            ccy = st.text_input("通貨3桁", placeholder="USD").upper().strip()
            name = st.text_input("名称（任意）").strip()
            submitted = st.form_submit_button("追加/更新")
            if submitted:
                if not ticker or not ccy or len(ccy) != 3:
                    st.error("Ticker と 通貨3桁 は必須です")
                else:
                    upsert_asset(conn, ticker, ccy, name or None)
                    st.success(f"登録: {ticker} ({ccy})")
        st.caption("一覧")
        st.dataframe(q_all(conn, "SELECT ticker, ccy, COALESCE(name,'') AS name FROM assets ORDER BY ticker"))

    with tab_fx:
        st.subheader("FX 対JPYレート")
        with st.form("fx_form"):
            d = st.date_input("日付", value=sel_date)
            ccy2 = st.text_input("通貨3桁", placeholder="USD").upper().strip()
            rate = st.number_input("レート (例 145.23)", min_value=0.0, step=0.0001, format="%f")
            submitted = st.form_submit_button("追加/更新")
            if submitted:
                if not ccy2 or len(ccy2) != 3 or rate <= 0:
                    st.error("通貨3桁とレート(>0)が必要です")
                else:
                    upsert_fx(conn, d.strftime("%Y-%m-%d"), ccy2, float(rate))
                    st.success(f"登録: {d} {ccy2}JPY={rate}")
        st.caption(f"{sel_date_str} のFX")
        st.dataframe(q_all(conn, "SELECT date, pair, rate FROM fx_rates WHERE date = ? ORDER BY pair", (sel_date_str,)))

    with tab_snapshots:
        st.subheader("Snapshots（日次スナップショット）")
        asset_meta = get_asset_meta(conn)
        tickers = sorted(asset_meta.keys())

        state = st.session_state
        state.setdefault("snap_qty", 0.0)
        state.setdefault("snap_price", 0.0)
        state.setdefault("snap_amount_jpy", 0.0)
        state.setdefault("snap_selection", "")

        if state.get("snap_apply_pending"):
            if "snap_qty_pending" in state:
                state.snap_qty = state.snap_qty_pending
                del state["snap_qty_pending"]
            if "snap_price_pending" in state:
                state.snap_price = state.snap_price_pending
                del state["snap_price_pending"]
            if "snap_amount_pending" in state:
                state.snap_amount_jpy = state.snap_amount_pending
                del state["snap_amount_pending"]
            state.snap_apply_pending = False

        with st.form("snap_form"):
            d = st.date_input("日付", value=sel_date, key="snap_date")
            ticker = (
                st.selectbox("Ticker", options=tickers, key="snap_ticker")
                if tickers
                else st.text_input("Ticker", key="snap_ticker_text")
            )
            date_iso = d.strftime("%Y-%m-%d")
            meta = asset_meta.get(ticker) if ticker else None
            ccy = meta.get("ccy") if meta else None
            price_auto = get_price_ccy(conn, ticker, date_iso) if ticker else None
            fx_auto = get_fx_rate(conn, ccy, date_iso) if ccy else None

            selection_key = f"{ticker}|{date_iso}"
            if selection_key != state.snap_selection:
                state.snap_selection = selection_key
                if price_auto is not None:
                    state.snap_price = float(price_auto)
                # リセットは明示ボタンで行う

            # 情報表示
            info_cols = st.columns(3)
            with info_cols[0]:
                st.metric("通貨", ccy or "?")
            with info_cols[1]:
                st.metric("価格 (price_ccy)", f"{price_auto:.4f}" if price_auto else "-")
            with info_cols[2]:
                st.metric("FXレート", f"{fx_auto:.4f}" if fx_auto else ("1" if ccy == "JPY" else "-"))

            colp1, colp2, colp3 = st.columns([1, 1, 2])
            with colp1:
                load_prev = st.form_submit_button("前回値を読み込む")
            with colp2:
                reset_vals = st.form_submit_button("値をクリア")

            amount_jpy = st.number_input(
                "評価額 (JPY)",
                min_value=0.0,
                step=1000.0,
                key="snap_amount_jpy",
            )
            price = st.number_input(
                "現地通貨建て価格 price_ccy",
                min_value=0.0,
                step=0.0001,
                format="%f",
                key="snap_price",
            )
            qty = st.number_input(
                "数量 qty (手動入力も可)",
                min_value=0.0,
                step=0.0001,
                format="%f",
                key="snap_qty",
            )

            fx_for_calc = fx_auto if fx_auto is not None else (1.0 if ccy == "JPY" else None)
            computed_qty = None
            if amount_jpy > 0 and price > 0 and fx_for_calc:
                computed_qty = amount_jpy / (price * fx_for_calc)
                st.caption(f"推計数量（評価額 ÷ 価格 × FX）: {computed_qty:.4f}")
            elif amount_jpy > 0 and price > 0:
                st.warning("FXレートが不足しているため、自動計算できません。FXタブでレートを追加してください。")

            submitted = st.form_submit_button("追加/更新")

            if reset_vals:
                state.snap_qty_pending = 0.0
                state.snap_price_pending = 0.0
                state.snap_amount_pending = 0.0
                state.snap_apply_pending = True
                st.rerun()

            if load_prev:
                tkr = ticker if tickers else state.get("snap_ticker_text", "").strip()
                if tkr:
                    prev = get_prev_snapshot(conn, tkr, date_iso)
                    if prev:
                        state.snap_qty_pending = float(prev["qty"])
                        state.snap_price_pending = float(prev["price_ccy"])
                        prev_meta = asset_meta.get(tkr)
                        prev_ccy = prev_meta.get("ccy") if prev_meta else "JPY"
                        prev_fx = get_fx_rate(conn, prev_ccy, prev["date"]) or (1.0 if prev_ccy == "JPY" else 0.0)
                        state.snap_amount_pending = float(prev["qty"]) * float(prev["price_ccy"]) * (prev_fx or 0.0)
                        state.snap_apply_pending = True
                        st.success(f"前回 {prev['date']} から qty/price を読み込みました")
                        st.rerun()
                    else:
                        st.info("前回スナップショットは見つかりませんでした")
                else:
                    st.error("Ticker を選択してください")

            if submitted:
                tkr = ticker if tickers else state.get("snap_ticker_text", "").strip()
                if not tkr:
                    st.error("Ticker は必須です")
                else:
                    price_to_store = float(price)
                    if price_to_store <= 0:
                        st.error("価格は 0 より大きい必要があります")
                    else:
                        if amount_jpy > 0:
                            if not fx_for_calc:
                                st.error("FXレートが不足しているため、JPYから数量を算出できません")
                            else:
                                qty_to_store = amount_jpy / (price_to_store * fx_for_calc)
                        else:
                            qty_to_store = float(qty)
                        if amount_jpy == 0 or fx_for_calc:
                            upsert_snapshot(conn, date_iso, tkr, float(qty_to_store), price_to_store)
                            state.snap_qty_pending = float(qty_to_store)
                            state.snap_price_pending = price_to_store
                            state.snap_amount_pending = float(amount_jpy)
                            state.snap_apply_pending = True
                            st.success(
                                f"登録: {date_iso} {tkr} qty={qty_to_store:.4f} price={price_to_store:.4f}"
                            )
                            st.rerun()

        st.caption("登録済み Snapshots 一覧")
        st.dataframe(
            q_all(
                conn,
                "SELECT date, ticker, qty, price_ccy FROM snapshots ORDER BY date DESC, ticker",
            )
        )

    with tab_views:
        st.subheader("Views（評価/原因分解）")
        # ヘルパー：FX不足と合計検証
        with st.expander("データチェック"):
            c1, c2 = st.columns(2)
            with c1:
                if st.button("FX不足チェック（非JPY資産）"):
                    missing = fx_missing_for_date(conn, sel_date_str)
                    if not missing:
                        st.success("指定日のFX不足はありません")
                    else:
                        st.warning("不足しているFX: " + ", ".join(m["pair"] for m in missing))
            with c2:
                # 合計検証
                att = q_all(
                    conn,
                    "SELECT ticker, delta_total, delta_price, delta_fx, delta_cross, flow FROM v_attribution WHERE date = ?",
                    (sel_date_str,),
                )
                if st.button("合計検証（price+fx+cross+flow ≈ total）"):
                    tol = 1e-6
                    fails = []
                    for r in att:
                        lhs = (r["delta_price"] or 0) + (r["delta_fx"] or 0) + (r["delta_cross"] or 0) + (r["flow"] or 0)
                        rhs = r["delta_total"] or 0
                        if abs(lhs - rhs) > tol:
                            fails.append((r["ticker"], lhs - rhs))
                    if not fails:
                        st.success("全行OK（許容誤差内）")
                    else:
                        st.error("不一致: " + ", ".join(f"{tkr} Δ={diff:.6f}" for tkr, diff in fails))

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**v_valuation**")
            val_rows = q_all(
                conn,
                """
                SELECT date, ticker, ccy, qty, price_ccy, fx_rate, value_jpy
                FROM v_valuation WHERE date = ? ORDER BY ticker
                """,
                (sel_date_str,),
            )
            st.dataframe(val_rows)
            if val_rows:
                import pandas as pd

                df = pd.DataFrame(val_rows)
                st.download_button(
                    "Download v_valuation CSV",
                    df.to_csv(index=False).encode("utf-8"),
                    file_name=f"valuation_{sel_date_str}.csv",
                    mime="text/csv",
                )
        with col2:
            st.markdown("**v_attribution**")
            att_rows = q_all(
                conn,
                """
                SELECT date, ticker, delta_total, delta_price, delta_fx, delta_cross, flow
                FROM v_attribution WHERE date = ? ORDER BY ticker
                """,
                (sel_date_str,),
            )
            st.dataframe(att_rows)
            if att_rows:
                import pandas as pd

                df = pd.DataFrame(att_rows)
                st.download_button(
                    "Download v_attribution CSV",
                    df.to_csv(index=False).encode("utf-8"),
                    file_name=f"attribution_{sel_date_str}.csv",
                    mime="text/csv",
                )

        st.markdown("---")
        st.markdown("**v_portfolio_total**")
        total_rows = q_all(
            conn,
            """
            SELECT date, total_value_jpy
              FROM v_portfolio_total
             WHERE date = ?
            """,
            (sel_date_str,),
        )
        st.dataframe(total_rows)
        if total_rows:
            import pandas as pd

            df_total = pd.DataFrame(total_rows)
            st.download_button(
                "Download v_portfolio_total CSV",
                df_total.to_csv(index=False).encode("utf-8"),
                file_name=f"portfolio_total_{sel_date_str}.csv",
                mime="text/csv",
            )

        col3, col4 = st.columns(2)
        with col3:
            st.markdown("**v_currency_exposure**")
            exposure_rows = q_all(
                conn,
                """
                SELECT date, ccy, value_jpy
                  FROM v_currency_exposure
                 WHERE date = ?
                 ORDER BY value_jpy DESC
                """,
                (sel_date_str,),
            )
            st.dataframe(exposure_rows)
            if exposure_rows:
                import pandas as pd

                df_exp = pd.DataFrame(exposure_rows)
                st.download_button(
                    "Download v_currency_exposure CSV",
                    df_exp.to_csv(index=False).encode("utf-8"),
                    file_name=f"currency_exposure_{sel_date_str}.csv",
                    mime="text/csv",
                )
        with col4:
            st.markdown("**v_valuation_enriched**")
            enriched_rows = q_all(
                conn,
                """
                SELECT date, ticker, value_jpy, portfolio_value_jpy, weight
                  FROM v_valuation_enriched
                 WHERE date = ?
                 ORDER BY value_jpy DESC
                """,
                (sel_date_str,),
            )
            st.dataframe(enriched_rows)
            if enriched_rows:
                import pandas as pd

                df_enriched = pd.DataFrame(enriched_rows)
                st.download_button(
                    "Download v_valuation_enriched CSV",
                    df_enriched.to_csv(index=False).encode("utf-8"),
                    file_name=f"valuation_enriched_{sel_date_str}.csv",
                    mime="text/csv",
                )

        st.markdown("---")
        st.markdown("**推移（折れ線グラフ）**")
        min_hist, max_hist = get_portfolio_date_range(conn)
        if not min_hist or not max_hist:
            st.info("ポートフォリオ履歴を表示するには v_portfolio_total にデータが必要です")
        else:
            max_hist = min(max_hist, sel_date)
            if max_hist < min_hist:
                st.info("選択中の日付より前の履歴がありません")
            else:
                default_start = max(min_hist, max_hist - timedelta(days=29))
                start_date_hist, end_date_hist = st.slider(
                    "表示期間",
                    min_value=min_hist,
                    max_value=max_hist,
                    value=(default_start, max_hist),
                    format="%Y-%m-%d",
                    key="views_history_range",
                )

                start_iso_hist = start_date_hist.strftime("%Y-%m-%d")
                end_iso_hist = end_date_hist.strftime("%Y-%m-%d")

                portfolio_hist = fetch_portfolio_history(conn, start_iso_hist, end_iso_hist)
                currency_hist = fetch_currency_history(conn, start_iso_hist, end_iso_hist)

                chart_col1, chart_col2 = st.columns(2)
                with chart_col1:
                    st.caption("ポートフォリオ合計（JPY）")
                    if portfolio_hist.empty:
                        st.info("表示可能な履歴がありません")
                    else:
                        chart_df = portfolio_hist.set_index("date")["total_value_jpy"]
                        st.line_chart(chart_df, height=240)
        with chart_col2:
            st.caption("通貨別エクスポージャ（JPY）")
            if currency_hist.empty:
                st.info("表示可能な履歴がありません")
            else:
                pivot_df = (
                    currency_hist.pivot(index="date", columns="ccy", values="value_jpy")
                    .sort_index()
                )
                st.line_chart(pivot_df, height=240)

        st.markdown("---")
        with st.expander("AI要約 (OpenAI)"):
            if OpenAI is None:
                st.info("`openai` パッケージがインストールされていません。`pip install -r requirements.txt` を実行してください。")
            elif not os.getenv("OPENAI_API_KEY"):
                st.warning("環境変数 OPENAI_API_KEY を設定すると要約機能が利用できます。例: `.env` にキーを保存し、起動前に読み込んでください。")
            else:
                st.caption("OpenAI API を利用して変動要因を要約します。API利用料が発生する点に注意してください。")
                day_col, hist_col = st.columns(2)
                day_summary_key = f"ai_summary_day_{sel_date_str}"
                hist_summary_key = "ai_summary_history"

                if day_col.button("選択日の要因を要約", key=f"btn_ai_day_{sel_date_str}"):
                    attribution = get_attribution_for_date(conn, sel_date_str)
                    if not attribution:
                        st.info("この日付の原因分解データがありません。")
                    else:
                        exposure = get_currency_exposure_for_date(conn, sel_date_str)
                        total_value = get_portfolio_total_for_date(conn, sel_date_str)
                        prompt = build_day_prompt(sel_date_str, attribution, exposure, total_value)
                        with st.spinner("OpenAI に問い合わせ中..."):
                            try:
                                summary = summarize_with_openai(prompt)
                                st.session_state[day_summary_key] = summary
                            except RuntimeError as exc:
                                st.error(str(exc))

                if hist_col.button("全履歴を要約", key="btn_ai_history"):
                    attribution_history = get_attribution_history(conn)
                    if not attribution_history:
                        st.info("原因分解の履歴データがありません。")
                    else:
                        totals_history = get_portfolio_totals_history(conn)
                        prompt = build_history_prompt(attribution_history, totals_history)
                        with st.spinner("OpenAI に問い合わせ中..."):
                            try:
                                summary = summarize_with_openai(prompt)
                                st.session_state[hist_summary_key] = summary
                            except RuntimeError as exc:
                                st.error(str(exc))

                if day_summary_key in st.session_state:
                    st.markdown("#### 選択日の要約")
                    st.markdown(st.session_state[day_summary_key])

                if hist_summary_key in st.session_state:
                    st.markdown("#### 履歴要約")
                    st.markdown(st.session_state[hist_summary_key])

    with tab_charts:
        st.subheader("チャートビュー")
        default_end = sel_date
        default_start = max(sel_date - timedelta(days=30), date_cls(2000, 1, 1))
        date_range = st.date_input(
            "期間",
            value=(default_start, default_end),
            max_value=date_cls.today(),
        )
        if isinstance(date_range, tuple):
            start_date, end_date = date_range
        else:
            start_date = date_range
            end_date = date_range
        if end_date < start_date:
            st.error("終了日は開始日以降にしてください")
        else:
            start_iso = start_date.strftime("%Y-%m-%d")
            end_iso = end_date.strftime("%Y-%m-%d")

            price_tickers = [
                row["ticker"]
                for row in q_all(
                    conn,
                    "SELECT DISTINCT ticker FROM asset_prices ORDER BY ticker",
                )
            ] if table_exists(conn, "asset_prices") else []

            fx_pairs = [
                row["pair"]
                for row in q_all(
                    conn,
                    "SELECT DISTINCT pair FROM fx_rates ORDER BY pair",
                )
            ] if table_exists(conn, "fx_rates") else []

            col_price, col_fx = st.columns(2)

            with col_price:
                st.markdown("**Asset Prices**")
                selected_prices = st.multiselect(
                    "表示するティッカー",
                    options=price_tickers,
                    default=price_tickers[:2],
                    help="asset_prices テーブルの終値を使用します",
                )
                df_prices = fetch_asset_prices(conn, selected_prices, start_iso, end_iso)
                if df_prices.empty:
                    st.info("指定期間に価格データがありません")
                else:
                    chart_df = (
                        df_prices.pivot(index="date", columns="ticker", values="close")
                        .sort_index()
                    )
                    st.line_chart(chart_df)

            with col_fx:
                st.markdown("**FX Rates**")
                selected_pairs = st.multiselect(
                    "表示する通貨ペア",
                    options=fx_pairs,
                    default=[p for p in fx_pairs if p.endswith("JPY")][:2],
                    help="fx_rates テーブルのレートを使用します",
                )
                df_fx = fetch_fx_history(conn, selected_pairs, start_iso, end_iso)
                if df_fx.empty:
                    st.info("指定期間にFXデータがありません")
                else:
                    chart_df = (
                        df_fx.pivot(index="date", columns="pair", values="rate")
                        .sort_index()
                    )
                    st.line_chart(chart_df)


if __name__ == "__main__":
    main()
