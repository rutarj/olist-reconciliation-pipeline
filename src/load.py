"""Load raw CSVs into DuckDB exactly as they are.

Every column is loaded as text (all_varchar). Typing happens later in the
staging step, so a bad value (say 'abc' in a price column) becomes a logged
exception instead of crashing the load or being silently turned into NULL.

Each table gets a _row_id (1 = first data row in the file). That is the
stable record id used by the exceptions table, because natural keys can be
duplicated in the raw data.
"""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from .config import RAW_FILES

log = logging.getLogger(__name__)


def load_raw(con: duckdb.DuckDBPyConnection, raw_dir: Path) -> dict[str, int]:
    counts = {}
    for table, file_name in RAW_FILES.items():
        path = (Path(raw_dir) / file_name).as_posix()
        con.execute(f"""
            create or replace table raw_{table} as
            select row_number() over () as _row_id, *
            from read_csv('{path}', header = true, all_varchar = true, quote = '"', escape = '"',
                          strict_mode = false, parallel = false)
        """)
        counts[table] = con.execute(f"select count(*) from raw_{table}").fetchone()[0]
        log.info("loaded raw_%-22s %9s rows", table, f"{counts[table]:,}")
    return counts
