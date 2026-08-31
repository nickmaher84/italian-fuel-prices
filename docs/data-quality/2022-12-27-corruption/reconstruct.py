"""Rebuild a best-effort `prezzo_alle_8-20221227.csv` from its corrupt original
plus the surrounding daily files.

The 2022-12-27 "prezzo alle 8" file shipped inside
`categorized/prezzo_alle_8/2022/2022_4_tr.tar.gz` is corrupt: the last ~8.7 KB of
real data was overwritten with fragments of an uncompressed tar of the same
archive, and the file was then truncated mid-row. See README.md for the full
analysis.

Because "prezzo alle 8" is a snapshot at a fixed time (~08:01) and every row
carries `dtComu` (the instant the operator last communicated that price), a
missing row can be inferred deterministically from the neighbouring days:

  * if the 28th file has the row and its dtComu precedes the 27th snapshot,
    that same row was in the 27th file  -> take the 28th line verbatim;
  * otherwise the 27th snapshot still held the previous value
    -> take the 26th line verbatim.

Run from this directory:  python reconstruct.py
Outputs (overwritten):    prezzo_alle_8-20221227.reconstructed.csv
                          reconstruction-provenance.csv
It also prints a hold-out accuracy check (rebuild the *25th* from the 24th+26th
and compare against the real 25th).
"""
from __future__ import annotations

import collections
import datetime
import re
import tarfile
import tempfile
import urllib.request
from pathlib import Path

TAR_URL = "https://opendatacarburanti.mise.gov.it/categorized/prezzo_alle_8/2022/2022_4_tr.tar.gz"
MEMBER = "ftproot/osservaprezzi/copied/prezzo_alle_8-{ymd}.csv"
SNAPSHOT_27 = datetime.datetime(2022, 12, 27, 8, 1, 17)  # mtime of the corrupt member
HERE = Path(__file__).parent

ROW = re.compile(r"^(\d+);([^;\x00]*);(\d+\.\d+);([01]);(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})$")


def load(text: str):
    """text -> ({(station, fuel, is_self): raw_line}, {station: [key, ...] in file order})"""
    rows: dict[tuple, str] = {}
    order: dict[int, list] = collections.defaultdict(list)
    for line in text.split("\n"):
        line = line.rstrip("\r")
        m = ROW.match(line)
        if not m:
            continue
        key = (int(m.group(1)), m.group(2), m.group(4))
        rows[key] = line
        if key not in order[key[0]]:
            order[key[0]].append(key)
    return rows, order


def dtcomu(line: str) -> datetime.datetime:
    return datetime.datetime.strptime(line.rsplit(";", 1)[-1], "%d/%m/%Y %H:%M:%S")


def fetch_days(days: list[str]) -> dict[str, str]:
    """Return {ymd: file text}. Caches the tarball next to this script."""
    cache = Path(tempfile.gettempdir()) / "opendatacarburanti-2022_4_tr.tar.gz"
    if not cache.exists():
        print(f"downloading {TAR_URL} ...")
        urllib.request.urlretrieve(TAR_URL, cache)
    out = {}
    with tarfile.open(cache) as t:
        for ymd in days:
            out[ymd] = t.extractfile(MEMBER.format(ymd=ymd)).read().decode("latin1")
    return out


def reconstruct(corrupt: str, d26: str, d28: str):
    rows_c, _ = load(corrupt)
    rows_26, order_26 = load(d26)
    rows_28, order_28 = load(d28)

    # A key belongs on the 27th only if the intact original still has it, or if
    # *both* neighbours have it (a price stable across the gap). Keys that appear
    # only on the 28th are that day's own churn - new stations, new products,
    # added self-service variants - and must not be invented for the 27th.
    expected = set(rows_c) | (set(rows_26) & set(rows_28))

    out: dict[tuple, tuple[str, str, str]] = {}   # key -> (line, source, reason)
    for key in expected:
        if key in rows_c:
            out[key] = (rows_c[key], "file", "")
            continue
        l28, l26 = rows_28.get(key), rows_26.get(key)
        if l28 and l26 and dtcomu(l28) < SNAPSHOT_27:
            out[key] = (l28, "28th", f"unchanged since {dtcomu(l28):%Y-%m-%d %H:%M}, before the 27th 08:01 snapshot")
        elif l28 and l26:
            out[key] = (l26, "26th", "price changed after the 27th 08:01 snapshot, which still held the 26th value")

    def fuel_rank(station: int):
        seen = order_28.get(station) or order_26.get(station) or []
        return {k: i for i, k in enumerate(seen)}

    ordered = sorted(out, key=lambda k: (k[0], fuel_rank(k[0]).get(k, 99), k[1], k[2]))
    return out, ordered


def holdout(d24: str, d25: str, d26: str) -> tuple[int, int]:
    """Rebuild the 25th from the 24th + 26th, score exact-line matches."""
    rows_24, _ = load(d24)
    rows_25, _ = load(d25)
    rows_26, _ = load(d26)
    snap = datetime.datetime(2022, 12, 25, 8, 1, 0)
    ok = 0
    for key, real in rows_25.items():
        l26, l24 = rows_26.get(key), rows_24.get(key)
        pred = l26 if (l26 and dtcomu(l26) < snap) else (l24 or l26)
        ok += pred == real
    return ok, len(rows_25)


def main() -> None:
    corrupt = (HERE / "prezzo_alle_8-20221227.original.csv").read_bytes().decode("latin1")
    days = fetch_days(["20221224", "20221225", "20221226", "20221228"])

    out, ordered = reconstruct(corrupt, days["20221226"], days["20221228"])

    with (HERE / "prezzo_alle_8-20221227.reconstructed.csv").open("w", encoding="latin1", newline="") as f:
        f.write("Estrazione del 2022-12-27\n")
        f.write("idImpianto;descCarburante;prezzo;isSelf;dtComu\n")
        for key in ordered:
            f.write(out[key][0] + "\n")

    inferred = sorted(k for k in out if out[k][1] != "file")
    with (HERE / "reconstruction-provenance.csv").open("w", encoding="latin1", newline="") as f:
        f.write("idImpianto;descCarburante;isSelf;prezzo;dtComu;source;reason\n")
        for (station, fuel, is_self) in inferred:
            line, source, reason = out[(station, fuel, is_self)]
            price, dtcomu_str = line.split(";")[2], line.split(";")[4]
            f.write(f"{station};{fuel};{is_self};{price};{dtcomu_str};{source};{reason}\n")

    by_source = collections.Counter(v[1] for v in out.values())
    print(f"reconstructed {len(out):,} rows: "
          f"{by_source['file']:,} verbatim from the file, "
          f"{by_source['28th']} inferred from the 28th, "
          f"{by_source['26th']} from the 26th")

    ok, total = holdout(days["20221224"], days["20221225"], days["20221226"])
    print(f"hold-out (rebuild the 25th from the 24th + 26th): {ok:,}/{total:,} exact-line = {ok / total:.1%}")


if __name__ == "__main__":
    main()
