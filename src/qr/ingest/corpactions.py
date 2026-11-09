"""Corporate actions: NSE yearly CSV export (manual download, PRD s3) -> bronze.corp_actions.

Price factor (multiply the cum-date price to make it comparable with the ex-date price), PRD s4:
  split F0 -> F1: F1/F0          bonus a:b: b/(a+b)          dividend: no factor, cash D added to the ex-date return
  rights: left UNADJUSTED and counted (DECISIONS D-010)       demerger: ret nulled around ex-date (panel/adjust.py)
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import polars as pl

_RS = r"(?:rs|re|inr)\.?\s*"
NUM = r"([\d]+(?:\.\d+)?)"


def parse_subject(subject: str) -> dict:
    t = (subject or "").lower().strip()
    out = {"action": "other", "a": None, "b": None, "cash_inr": None, "price_factor": None}
    if "split" in t or "sub-division" in t or "sub division" in t or "consolidation" in t:
        m = re.search(r"from\s*" + _RS + NUM + r".*?to\s*" + _RS + NUM, t)
        if m:
            f0, f1 = float(m.group(1)), float(m.group(2))
            if f0 > 0 and f1 > 0:
                out.update(action="split", a=f0, b=f1, price_factor=f1 / f0)
                return out
        out["action"] = "split_unparsed"
        return out
    if "bonus" in t:
        m = re.search(r"bonus\s*(?:issue)?\s*(?:of)?\s*(\d+)\s*:\s*(\d+)", t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > 0 and b > 0:
                out.update(action="bonus", a=a, b=b, price_factor=b / (a + b))
                return out
        out["action"] = "bonus_unparsed"
        return out
    if "rights" in t:
        m = re.search(r"(\d+)\s*:\s*(\d+)", t)
        out["action"] = "rights"
        if m:
            out["a"], out["b"] = int(m.group(1)), int(m.group(2))
        return out
    if any(k in t for k in ("demerger", "de-merger", "spin off", "spin-off", "scheme of arrangement", "hive")):
        out["action"] = "demerger"
        return out
    if "dividend" in t:
        amts = [float(x) for x in re.findall(_RS + NUM, t)]
        if amts:
            out.update(action="dividend", cash_inr=float(sum(amts)))
        else:
            out["action"] = "dividend_unparsed"
        return out
    return out


def _norm(c: str) -> str:
    return re.sub(r"[^a-z0-9]", "", c.lower())


def _to_date(s: pl.Series) -> pl.Series:
    out = None
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d %b %Y"):
        p = s.str.strip_chars().str.to_date(fmt, strict=False)
        out = p if out is None else out.fill_null(p)
    return out


def read_exports(folder: Path = Path("data/raw/corpactions")) -> pl.DataFrame:
    frames = []
    for p in sorted(Path(folder).glob("*.csv")):
        df = pl.read_csv(p, infer_schema_length=0, truncate_ragged_lines=True, encoding="utf8-lossy")
        df = df.rename({c: _norm(c) for c in df.columns})
        need = {"symbol", "subject", "exdate"}
        if not need <= set(df.columns):
            raise ValueError(f"{p}: columns {df.columns} lack {need - set(df.columns)}")
        frames.append(df.select(
            pl.col("symbol").str.strip_chars(),
            (pl.col("series").str.strip_chars() if "series" in df.columns else pl.lit(None, pl.String)).alias("series"),
            pl.col("subject").str.strip_chars(),
            _to_date(pl.col("exdate")).alias("ex_date"),
            (_to_date(pl.col("recorddate")) if "recorddate" in df.columns else pl.lit(None, pl.Date)).alias("record_date"),
            (pl.col("isin").str.strip_chars() if "isin" in df.columns else pl.lit(None, pl.String)).alias("isin"),
            pl.lit(p.name).alias("source_file")))
    if not frames:
        return pl.DataFrame(schema={"symbol": pl.String, "ex_date": pl.Date, "subject": pl.String})
    return pl.concat(frames).filter(pl.col("ex_date").is_not_null()).unique(subset=["symbol", "ex_date", "subject"], keep="first")


def build_corp_actions(folder: Path = Path("data/raw/corpactions")) -> pl.DataFrame:
    df = read_exports(folder)
    parsed = [parse_subject(s) for s in df["subject"].to_list()]
    return df.with_columns(
        pl.Series("action", [p["action"] for p in parsed]),
        pl.Series("a", [p["a"] for p in parsed], dtype=pl.Float64),
        pl.Series("b", [p["b"] for p in parsed], dtype=pl.Float64),
        pl.Series("cash_inr", [p["cash_inr"] for p in parsed], dtype=pl.Float64),
        pl.Series("price_factor", [p["price_factor"] for p in parsed], dtype=pl.Float64),
    ).sort("ex_date", "symbol")
