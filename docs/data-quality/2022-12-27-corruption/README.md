# A corrupt daily file: `prezzo_alle_8-20221227.csv`

During the historical backfill, one member of the quarterly archive
`categorized/prezzo_alle_8/2022/2022_4_tr.tar.gz` failed to load. This directory
keeps the evidence and walks through what happened, because it is a good example
of a data-source failure that is invisible until you try to parse the bytes.

| file | what it is |
| --- | --- |
| `prezzo_alle_8-20221227.original.csv` | the member exactly as shipped by the publisher (contains NUL bytes; ends mid-row) |
| `prezzo_alle_8-20221227.reconstructed.csv` | best-effort repair — see [Reconstruction](#reconstruction) |
| `reconstruction-provenance.csv` | every row in the repair that did **not** come verbatim from the original, with its source and reasoning |
| `reconstruct.py` | regenerates the two files above from the original + the neighbouring days (downloads the quarterly archive; caches it in `$TMPDIR`) |

## Background: what these files are

`opendatacarburanti` (Italian MIMIT, formerly MISE) publishes a **"prezzo alle 8"**
file per day: a snapshot of every fuel price as it stood at roughly 08:00 that
morning. The format is:

```
Estrazione del 2022-12-27
idImpianto;descCarburante;prezzo;isSelf;dtComu
3464;Benzina;2.009;0;23/12/2022 14:00:09
...
```

One row per `(station, fuel, self-service)` combination. `dtComu` is the moment
the operator last *communicated* that price — so a row only changes between daily
files when the price actually changes, and `dtComu` can be days or weeks old.
That property is what makes the reconstruction below possible.

The daily files are bundled per quarter into a gzipped tar
(`2022_4_tr.tar.gz`), and that is what the scraper downloads.

## The symptom

The loader aborted on this member with:

```
Failed to insert into price_change: (psycopg2.errors.InvalidDatetimeFormat)
invalid input syntax for type timestamp: "NaT"
```

`tarfile` extracted the member without complaint (3,926,901 bytes), and it
decodes as valid UTF‑8 — NUL is a legal code point — so nothing upstream noticed.
The parser only fell over when a mangled `dtComu` reached Postgres.

## Anatomy of the corruption

Every sibling file in the archive is 3,926,092–3,926,898 bytes, contains **no**
NUL bytes, and ends with a newline. This one is 3,926,901 bytes, contains
**1,012 NUL bytes**, and ends mid-row: `...;1.599;1;24/12/2022 2`.

The damage is a single region flush against the end of the file. Clean, in-order
data runs to `55164;Benzina;1.769;0;15/12/2022 17:42:31` at byte **3,917,824** (a
512-byte boundary). That row then runs straight into a mid-row fragment
(`Super;1.979;0;…`) — the stations jump 55164 → 55216 — which carries genuine
27th rows for 55216‥55220 but ends at `55220;Benzina;1.`. From byte **3,918,197**
(373 bytes into that record) to EOF the file is out of order: NUL padding, two tar
headers, ~10 opening rows each of the 28th and 29th members, and three reshuffled
fragments of the 27th's own tail. The disturbed region is **exactly 8,704 bytes,
17 × 512**.

### The tail, record by record

512 bytes is tar's fundamental unit: every header is one 512-byte *record*, file
data is written in 512-byte records, and a member's short final record is
zero-padded to 512. Number the CSV's own records from 0; byte 3,917,824 is the
start of **record 7652**, and records 7652–7669 are the disturbed tail:

| record | offset | contents | verdict |
| --- | --- | --- | --- |
| 0–7651 | 0 | ~3.92 MB of rows, ascending to `55164;Benzina;…;0` | clean |
| **7652** | 3,917,824 | 27th rows 55216‥55220 — 373 B, starts mid-row (`…Super;1.979;0`), ends mid-row (`55220;Benzina;1.`), then 139 B `00` | genuine, torn both ends |
| 7653 | 3,918,336 | tar header → `…-20221229.csv` | **foreign** |
| 7654 | 3,918,848 | 29th opening: banner, column header, stations 3464‥3471 | **foreign** |
| **7655** | 3,919,360 | 27th rows 55224‥55226 — 512 B, first row's head lost at the seam | genuine, lead row severed |
| **7656** | 3,919,872 | 27th rows 55226‥55228 — 373 B, ends `55228;Gasolio;…;27/12/2022 01:29:05` + newline, then 139 B `00` | genuine, **complete — the file's true last record** |
| 7657 | 3,920,384 | tar header → `…-20221228.csv` | **foreign** |
| 7658 | 3,920,896 | 28th opening: banner, column header, stations 3464‥3471 | **foreign** |
| 7659–7668 | 3,921,408 | 27th rows 55164‥~55202 — ten clean 512 B records | genuine, intact |
| **7669** | 3,926,528 | 27th rows ~55202‥55206 — 373 B, ends mid-row (`55206;Benzina;1.599;1;24/12/2022 2`), no padding | genuine, truncated at EOF |

**Only four records are foreign** — two tar headers and one opening record each
from the 28th and 29th members. Their 3464‥3471 rows carry `dtComu` on the 27th
afternoon (`27/12 14:00`) and the 28th, impossible in a 27 Dec 08:00 snapshot.
Everything else is the 27th's own data. The 55224‥55228 rows are the 27th's, not
the 29th's: the 55228 rows read `27/12 01:29`, not the 29th's `28/12 10:52`, and
skip 55227, which the 29th has.

**Record 7656 is the genuine end of the file.** Its last row is newline-terminated
and 55228 is the highest station on the 27th — the reconstruction ends there too.
The file *should* have stopped at byte 3,919,872 + 373; instead those last 139
bytes are `00` and it runs on. Record 7669, by contrast, has no padding at all —
a hard truncation mid-row.

**Three records break at exactly +373.** Records 7652, 7656 and 7669 each hold
373 bytes of real data. For 7652 and 7656 the remaining 139 bytes are `00` — tar's
inter-member padding, and `373 + 139 = 512` drops the following header (7653,
7657) exactly onto the CSV's grid. For 7669 the 373 bytes just run into EOF. The
disturbed span, byte 3,918,197 to EOF, is `17 × 512 = 8,704` bytes, offset 373
into the grid at both ends: whatever rewrote the tail rewrote a whole number of
blocks. The NUL bytes then account for themselves exactly: `139 + 367 + 139 + 367
= 1,012` (the two `00` tails plus the empty back half of each tar header) —
*every* NUL byte in the file.

### What is actually lost

The 27th's own rows survive in three fragments — 55164‥55206 (records 7659–7669),
55216‥55220 (7652), 55224‥55228 (7655–7656). In logical order the file ran
`…55164 → 55206 → ⟨gap⟩ → 55216 → 55220 → ⟨gap⟩ → 55224 → 55228`, and only the
55164‥55206 fragment is badly out of place — moved to sit *after* the true last
record and then cut short. Genuinely gone: stations 55210‥55215 and 55221‥55223
in full, plus scattered rows at 55164, 55206, 55216, 55220 and 55224 — **58 rows
across 13 stations**, ~2.5 KB. That is almost exactly the combined footprint of
the four foreign records, the two `00` tails and the truncation; nothing is lost
beyond the visible damage.

### Two things stand out

1. **It is tar, byte-for-byte.** The injected records are aligned to the CSV's
   512-byte grid, carry the `ustar\0` magic and octal `mode` / `uid` / `gid` /
   `size` / `mtime` fields of a real tar header, and name members of *this same
   archive*. This is a slice of an uncompressed `2022_4_tr.tar`.

2. **The injected data is from the future.** The two foreign data records are the
   openings of the 28th and 29th members. Per their own tar metadata both files
   were (re)generated together at **2022-12-29 11:31:47**, whereas this member's
   mtime is **2022-12-27 08:01:17**; their 3464‥3471 rows carry `dtComu`
   timestamps on the 27th afternoon and the 28th. Content that postdates a file's
   own mtime did not get there through that file's inode.

Supporting detail — the publisher rewrites historical daily files after the
fact. mtimes in the same archive:

| member | mtime |
| --- | --- |
| `…-20221223.csv` | 2022-12-28 09:11:32 |
| `…-20221227.csv` | 2022-12-27 08:01:17 |
| `…-20221228.csv` | 2022-12-29 11:31:47 |
| `…-20221229.csv` | 2022-12-29 11:31:47 |
| `…-20221230.csv` | 2022-12-30 09:19:32 |

The archive's gzip header is stamped 2022-12-31 08:15:25 — it was rebuilt at
least four days after the 27th file was first written.

### Why does another file's content appear at all?

Very little of it does. Of the ~8.7 KB past byte 3,918,197, only ~1.3 KB is
foreign: two tar headers and ~10 opening rows each of the 28th and 29th members.
Everything else is the 27th file's **own** tail — stations 55164‥55206,
55216‥55220 and 55224‥55228 — broken into three fragments and reshuffled out of
order (the file's true sequence is 55164‥55206 → … → 55216‥55220 → 55224‥55228),
wrapped around the foreign records, and truncated mid-row.

So the tail was **re-ordered**, not overwritten with another file: the genuine
data survives almost intact, just relocated, which is why the reconstruction
recovers all but 58 rows verbatim. The 1,012 NUL bytes are the zero-padding of
the injected tar records. They add ~1 KB — enough that the corrupt file
(3,926,901 bytes) edges three bytes past its largest sibling despite having lost
real rows; strip the padding and it is *shorter* than a typical sibling.

## Theories, most to least likely

### 1. Cross-linked disk blocks on the publisher's server

A block (or extent) at the tail of `…-20221227.csv` was also handed to another
file — most likely the growing uncompressed `2022_4_tr.tar` staging archive —
and when the archive builder wrote the 28th/29th members into it, those writes
reached the CSV's blocks too.

This is the only theory that fits *all* the evidence: tar-format bytes, 512-byte
alignment inside the CSV, content newer than the CSV's mtime, exactly 17 blocks
at the end, a hard truncation, and every injected fragment belonging to the same
nightly batch (files whose blocks would be physically adjacent on disk).

Cross-linked blocks come from a free-space bitmap that was not flushed before an
unclean shutdown, a storage controller / RAID cache that lost write ordering,
bad RAM flipping a block pointer, or a bug in a copy-on-write / dedup / overlay
layer. `fsck` reports this class of fault as "block N claimed by inodes X and Y".

### 2. A truncated copy onto recycled, un-zeroed blocks

The publisher clearly regenerates old daily files (the 23rd's mtime is the
28th). If the 27th was regenerated by writing a fresh file whose blocks the
allocator had just reclaimed from a deleted staging tar, and that write stopped
early (process killed, disk full, quota), the bytes past the write head would be
the leftover previous contents of those blocks — a tar. This explains the
truncation and the tar fragments, but is weaker on the mtime: a fresh write
should set a fresh mtime unless the tool deliberately preserved it (`cp -p`,
`rsync -t`).

### 3. A read/write race while the archive was assembled

If the tar build (2022-12-31) read this CSV while it was mid-rewrite, it could
capture a half-updated file. But a content-level race cannot put *tar-format*
bytes, 512-aligned, inside the CSV — so this does not explain what we see.

## Impact

- **Parsing.** `scrub_tar_debris` strips the injected tar headers and 28th/29th
  opening rows first; 92,035 rows then parse, `_drop_unusable_rows` discards 3
  (partial rows torn across a scrubbed block boundary), and **92,032 ingest** —
  exactly the set `reconstruct.py` takes verbatim from the file. No `NaT` dates,
  no phantom rows for stations 3464 / 3468 / 3471.
- **Missing rows.** All genuine losses are in the truncated tail. **58 rows
  across 13 stations** (id 55164–55224) that are present on *both* the 26th and
  28th files are absent from the 27th. Everything below station 55164 is intact.
  Station 27797 (5 rows) is on the 26th but gone by the 28th with a `dtComu` of
  27/08/2022; because it sorts far outside the corrupt tail and is *not* in the
  intact body, its absence is a genuine delisting, not a loss — the
  reconstruction does not restore it.
- **Not corruption.** Day-to-day churn makes the raw diff look worse than it is:
  the 28th file adds new stations (55229, 55231, 55232), a GPL pump at 22430,
  self-service variants at 20836, arctic diesel at 46554 — ~16 rows that simply
  did not exist yet on the 27th. The reconstruction deliberately does **not**
  invent these.
- **Analytical mirror.** Smaller still. The mirror dates a price by the span
  `least(min_extraction_date) … greatest(max_extraction_date)` across the daily
  files it appeared in. A price unchanged across the 27th has a byte-identical
  row on the 26th and 28th, so its span stretches over the 27th automatically.
  **28 of the 58 losses are exactly this** and need no repair; the real gap is
  ~30 rows out of ~2.5 M per quarter.

## Reconstruction

`reconstruct.py` rebuilds the file. A `(station, fuel, self-service)` key is
considered to belong on the 27th only if the intact original still has it **or**
*both* neighbouring days have it. Keys unique to the 28th are that day's own
churn and are left out; keys that appear only on the 26th are treated as
delistings and also left out.

| situation | reconstructed from | rows |
| --- | --- | --- |
| present in the intact part of the original | the original, verbatim | 92,032 |
| missing; the 28th's `dtComu` is **before** 2022-12-27 08:01 | the 28th, verbatim — that exact row was in effect at the snapshot | 36 |
| missing; the 28th's `dtComu` is at/after the snapshot | the 26th, verbatim — the snapshot still held the previous value | 22 |

Result: **92,090 rows**, sorted by station then by the fuel order the station
uses in the 28th file. It parses cleanly (0 rows dropped). Every non-verbatim
row is listed in `reconstruction-provenance.csv`.

### How accurate is it?

Hold-out test: throw away the real 25th-of-December file and rebuild it from the
24th + 26th with the same rule, then compare line by line against the real 25th.
**85.1%** of rows match exactly (77% on the churny high-numbered stations,
~85% on the bulk). The misses are prices that changed twice inside the
48-hour window — a three-file method structurally cannot recover a value that
was already gone by the next snapshot. The full `price_change` history in
Postgres could do better, but for ~30 uncertain rows in a quarter it is not
worth the machinery.

**This file is a best-effort artefact for study, not a source of truth. It is
not loaded by the pipeline.**

## Is there a clean copy anywhere?

The tar is not the culprit — it faithfully archived a file that was already
broken on the publisher's disk. As of 2026 the live
`2022_4_tr.tar.gz` (rebuilt 2023-01-09, a second time after the first
2022-12-31 build) still contains the **byte-identical** corrupt member: same
3,926,901 bytes, same 1,012 NUL bytes, same truncated tail. Both tar rebuilds
re-archived the same damaged CSV.

A clean copy is unlikely to be publicly retrievable:

- `opendatacarburanti.mise.gov.it` publishes **only** the quarterly tars — no
  individual daily files — and every build of the Q4 2022 tar postdates the
  2022-12-29 corruption.
- The oldest Wayback Machine capture of the archive is 2023-01-13, also after
  the corruption.
- The MIMIT "current day" export (`mimit.gov.it/images/exportCSV/…`) is
  overwritten daily and keeps no history.

Where a clean copy *could* still exist: the ministry's own upstream
price-submission database (from which any 08:00 snapshot can be regenerated
exactly, but which is not downloadable), or a third party who fetched the daily
file on the morning of 2022-12-27 before it was rotated and corrupted. This
project has no pre-corruption copy of its own — it began well after 2022 and
backfills history from these same tars.

## What the loader does now

The corruption drove four changes (all on `feature/analytics-infra`):

- **`app/scraper/base.py`** — `to_bool` / `to_datetime` return `None` instead of
  raising; converters run through `safe_convert`; `_drop_unusable_rows` drops any
  row missing `station_id`, `price`, or a parseable `entry_date` and logs the
  count. One bad row can no longer abort a whole file.
- **`app/scraper/base.py`** — `scrub_tar_debris` runs on every file before
  parsing but is a no-op unless the file contains NUL bytes (only this one ever
  has). It walks the 512-byte grid, drops each block whose offset 257 holds the
  `ustar` magic **plus the block after it** (tar member data always follows a
  header), and strips the NUL padding. This removes the two injected tar headers
  and the ~10 opening rows each of the 28th/29th members — so stations 3464,
  3468, 3471 no longer pick up a phantom price change dated 2022-12-27. Rows torn
  across a dropped boundary are left broken and fall out at `_drop_unusable_rows`;
  no attempt is made to stitch them back together.
- **`app/services/ingestion.py`** — the null sanitiser uses `pd.isna`, so pandas
  `NaT` (from an unparseable date) becomes SQL `NULL` rather than the string
  `"NaT"`.
- **`app/services/ingestion.py`** — `ingest_df` now re-raises after rolling back,
  so a failed insert propagates and the file (and its containing tar) is **not**
  marked `loaded`. Previously the error was swallowed, the tar looked complete,
  and nothing would retry it.
