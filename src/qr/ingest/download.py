"""Polite, resumable downloader for NSE static archives (PRD section 3).

Rules (CLAUDE.md non-negotiable 6):
  * at most 1 request/s (global limiter), honest User-Agent, no personal email
  * every file stored byte-for-byte under data/raw/<dataset>/ with SHA-256 in an append-only manifest
  * a cached file (or a confirmed 404) is never requested again
  * 403/429 after retries => stop and report. We never work around a block.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

CFG = yaml.safe_load((Path(__file__).resolve().parents[3] / "config" / "research.yaml").read_text())
HOST = CFG["download"]["host"]
UA = CFG["download"]["user_agent"]
MIN_INTERVAL = float(CFG["download"]["min_interval_s"])
RETRIES = int(CFG["download"]["retries"])

MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
LEGACY_END = dt.date(2024, 7, 5)  # last legacy CM file (PRD s3); F&O end date confirmed on Day 1


class Blocked(RuntimeError):
    """NSE answered 403/429 after all retries. Stop; do not circumvent."""


def url_for(dataset: str, d: dt.date) -> str:
    y, m, dd = d.year, MON[d.month - 1], f"{d.day:02d}"
    ymd, dmy = d.strftime("%Y%m%d"), d.strftime("%d%m%Y")
    return {
        "cm_legacy": f"{HOST}/content/historical/EQUITIES/{y}/{m}/cm{dd}{m}{y}bhav.csv.zip",
        "cm_udiff": f"{HOST}/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip",
        "mto": f"{HOST}/archives/equities/mto/MTO_{dmy}.DAT",
        "fo_legacy": f"{HOST}/content/historical/DERIVATIVES/{y}/{m}/fo{dd}{m}{y}bhav.csv.zip",
        "fo_udiff": f"{HOST}/content/fo/BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip",
        "indices": f"{HOST}/content/indices/ind_close_all_{dmy}.csv",
    }[dataset]


# One-time static reference files (sector snapshots, symbol master). Keyed by file name in the manifest.
STATIC = {
    "ind_nifty500list.csv": "/content/indices/ind_nifty500list.csv",
    "ind_niftytotalmarket_list.csv": "/content/indices/ind_niftytotalmarket_list.csv",
    "ind_niftymicrocap250_list.csv": "/content/indices/ind_niftymicrocap250_list.csv",
    "ind_niftysmallcap250list.csv": "/content/indices/ind_niftysmallcap250list.csv",
    "ind_niftymidcap150list.csv": "/content/indices/ind_niftymidcap150list.csv",
    "EQUITY_L.csv": "/content/equities/EQUITY_L.csv",
    "fo_mktlots.csv": "/content/fo/fo_mktlots.csv",
}

EXT = {"cm_legacy": "csv.zip", "cm_udiff": "csv.zip", "mto": "DAT", "fo_legacy": "csv.zip",
       "fo_udiff": "csv.zip", "indices": "csv"}


def datasets_for(d: dt.date, fo_legacy_end: dt.date = LEGACY_END) -> list[str]:
    """Which datasets to request for a weekday. Overlap windows get both formats."""
    out = []
    # CM: legacy through 2024-07-05; UDiFF from 2024-01-02 (6-month overlap = parser cross-check)
    if d <= LEGACY_END:
        out.append("cm_legacy")
    if d >= dt.date(2024, 1, 2):
        out.append("cm_udiff")
    out.append("mto")
    if d <= fo_legacy_end:
        out.append("fo_legacy")
    if d >= dt.date(2024, 7, 1):
        out.append("fo_udiff")
    out.append("indices")  # files exist from mid-2012; earlier dates are logged as missing
    return out


@dataclass
class Fetcher:
    root: Path = Path("data/raw")
    _last: float = 0.0

    def __post_init__(self):
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "_manifest.jsonl"
        self.done: dict[tuple[str, str], str] = {}
        if self.manifest.exists():
            for line in self.manifest.read_text().splitlines():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:  # partial last line from a killed run: that file is simply re-fetched
                    continue
                self.done[(r["dataset"], r["date"])] = r["status"]
        self.client = httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=False)
        self._lock = threading.Lock()

    def _wait(self):
        """Global limiter: request STARTS are >= MIN_INTERVAL apart across all worker threads (<= 1 request/s, D-027)."""
        with self._lock:
            dtw = MIN_INTERVAL - (time.monotonic() - self._last)
            if dtw > 0:
                time.sleep(dtw)
            self._last = time.monotonic()

    def _log(self, **r):
        r["ts"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            with self.manifest.open("a") as f:
                f.write(json.dumps(r) + "\n")
            self.done[(r["dataset"], r["date"])] = r["status"]

    def fetch(self, dataset: str, d: dt.date) -> str:
        """Return 'ok' | 'cached' | 'missing' (404 confirmed). Raises Blocked on 403/429."""
        key = (dataset, d.isoformat())
        if key in self.done:
            return "cached" if self.done[key] == "ok" else self.done[key]
        url = url_for(dataset, d)
        dest = self.root / dataset / f"{d.isoformat()}.{EXT[dataset]}"
        last_status = None
        for attempt in range(RETRIES + 1):
            self._wait()
            try:
                r = self.client.get(url)
            except httpx.HTTPError as e:
                last_status = f"exc:{type(e).__name__}"
                time.sleep(2 ** (attempt + 1))
                continue
            last_status = r.status_code
            if r.status_code == 200 and r.content:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
                self._log(dataset=dataset, date=d.isoformat(), status="ok", url=url,
                          bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest())
                return "ok"
            if r.status_code == 404:
                # DECISIONS D-005: a 404 is confirmed once more, then recorded as missing (holiday).
                if attempt >= 1:
                    self._log(dataset=dataset, date=d.isoformat(), status="missing", url=url, http=404)
                    return "missing"
                time.sleep(2)
                continue
            if r.status_code in (403, 429) or r.status_code >= 500:
                wait = float(r.headers.get("Retry-After", 2 ** (attempt + 2)))
                time.sleep(min(wait, 60))
                continue
            break
        if last_status in (403, 429):
            raise Blocked(f"{dataset} {d}: HTTP {last_status} after {RETRIES} retries ({url})")
        self._log(dataset=dataset, date=d.isoformat(), status=f"error:{last_status}", url=url)
        return f"error:{last_status}"


def fetch_statics(f: "Fetcher") -> dict:
    """Fetch each static reference file once (snapshot date = today). Same limiter, same rules."""
    out = {}
    for name, path in STATIC.items():
        key = ("static", name)
        if key in f.done:
            out[name] = "cached" if f.done[key] == "ok" else f.done[key]
            continue
        f._wait()
        r = f.client.get(HOST + path)
        if r.status_code in (403, 429):
            raise Blocked(f"static {name}: HTTP {r.status_code}")
        if r.status_code == 200 and r.content:
            dest = f.root / "static" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            f._log(dataset="static", date=name, status="ok", url=HOST + path, bytes=len(r.content),
                   sha256=hashlib.sha256(r.content).hexdigest(), snapshot=dt.date.today().isoformat())
            out[name] = "ok"
        else:
            f._log(dataset="static", date=name, status="missing" if r.status_code == 404 else f"error:{r.status_code}",
                   url=HOST + path, http=r.status_code)
            out[name] = f"http{r.status_code}"
    return out


def weekdays(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def run(start: dt.date, end: dt.date, root: Path = Path("data/raw"), only: list[str] | None = None,
        fo_legacy_end: dt.date = LEGACY_END, workers: int = 2) -> dict:
    """`workers` requests may be in flight at once (server latency ~1.9 s), but starts stay >= MIN_INTERVAL apart (D-027)."""
    from concurrent.futures import ThreadPoolExecutor

    f = Fetcher(root)
    print("static:", fetch_statics(f), flush=True)
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for d in weekdays(start, end):
            jobs = [ex.submit(f.fetch, ds, d) for ds in datasets_for(d, fo_legacy_end) if not (only and ds not in only)]
            for j in jobs:                       # a day's files finish before the next day is queued; Blocked propagates
                s = j.result()
                counts[s.split(":")[0]] = counts.get(s.split(":")[0], 0) + 1
            if d.day == 1 or d.weekday() == 0 and d.day <= 7:
                print(d, counts, flush=True)
    return counts
