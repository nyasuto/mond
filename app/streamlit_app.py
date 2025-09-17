import os
import sqlite3
from pathlib import Path
from datetime import date as date_cls

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DB_DEFAULT = ROOT / "money_diary.db"
SCHEMA_PATH = ROOT / "schema.sql"


def get_conn(db_path: Path) -> sqlite3.Connection:
    need_init = not db_path.exists()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if need_init:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            sql = f.read()
        conn.executescript(sql)
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


def main():
    st.set_page_config(page_title="Money Diary", layout="wide")
    st.title("Money Diary – ローカルGUI")

    db_path_str = st.sidebar.text_input("DBパス", str(DB_DEFAULT))
    db_path = Path(db_path_str).expanduser().resolve()
    conn = get_conn(db_path)

    sel_date = st.sidebar.date_input("対象日付", value=date_cls.today())
    sel_date_str = sel_date.strftime("%Y-%m-%d")

    tabs = st.tabs(["Assets", "FX", "Snapshots", "Views"])

    with tabs[0]:
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

    with tabs[1]:
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

    with tabs[2]:
        st.subheader("Snapshots（日次スナップショット）")
        assets = q_all(conn, "SELECT ticker FROM assets ORDER BY ticker")
        tickers = [a["ticker"] for a in assets]
        # セッション状態の初期化
        if "prefill_qty" not in st.session_state:
            st.session_state.prefill_qty = 0.0
        if "prefill_price" not in st.session_state:
            st.session_state.prefill_price = 0.0

        with st.form("snap_form"):
            d = st.date_input("日付", value=sel_date, key="snap_date")
            ticker = (
                st.selectbox("Ticker", options=tickers, key="snap_ticker")
                if tickers
                else st.text_input("Ticker", key="snap_ticker_text")
            )
            # 前回値の読み込みボタン（フォーム内）
            colp1, colp2, colp3 = st.columns([1, 1, 2])
            with colp1:
                load_prev = st.form_submit_button("前回値を読み込む")
            with colp2:
                reset_vals = st.form_submit_button("値をクリア")

            # 数値入力（セッション状態から初期値を反映）
            qty = st.number_input(
                "数量 qty",
                min_value=0.0,
                step=0.0001,
                format="%f",
                value=float(st.session_state.prefill_qty),
                key="snap_qty",
            )
            price = st.number_input(
                "現地通貨建て価格 price_ccy",
                min_value=0.0,
                step=0.0001,
                format="%f",
                value=float(st.session_state.prefill_price),
                key="snap_price",
            )
            submitted = st.form_submit_button("追加/更新")

            # ハンドリング（ボタンの優先順序: クリア > 読込 > 保存）
            if reset_vals:
                st.session_state.prefill_qty = 0.0
                st.session_state.prefill_price = 0.0
                st.rerun()
            if load_prev:
                tkr = ticker if tickers else st.session_state.get("snap_ticker_text", "").strip()
                if tkr:
                    prev = get_prev_snapshot(conn, tkr, d.strftime("%Y-%m-%d"))
                    if prev:
                        st.session_state.prefill_qty = float(prev["qty"])
                        st.session_state.prefill_price = float(prev["price_ccy"])
                        st.success(f"前回 {prev['date']} から qty/price を読み込みました")
                        st.rerun()
                    else:
                        st.info("前回スナップショットは見つかりませんでした")
                else:
                    st.error("Ticker を選択してください")
            if submitted:
                tkr = ticker if tickers else st.session_state.get("snap_ticker_text", "")
                if not tkr:
                    st.error("Ticker は必須です")
                else:
                    upsert_snapshot(conn, d.strftime("%Y-%m-%d"), tkr, float(qty), float(price))
                    st.success(f"登録: {d} {tkr} qty={qty} price={price}")
        st.caption(f"{sel_date_str} のSnapshots")
        st.dataframe(q_all(conn, "SELECT date, ticker, qty, price_ccy FROM snapshots WHERE date = ? ORDER BY ticker", (sel_date_str,)))

    with tabs[3]:
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


if __name__ == "__main__":
    main()
