"""Validation layer: schema contracts + business rules -> one exceptions table.

Flow
1. stg_<table>: typed copy of raw_<table> built with TRY_CAST from the contract.
   Nothing is removed. A value that fails the cast becomes NULL in staging and is
   logged as a type_mismatch exception.
2. Run every check. Each check is a SQL query returning the same six columns:
   table_name, record_id, record_key, check_name, reason, severity.
3. UNION ALL of the checks -> dq_exceptions.
4. dq_row_status: one row per input record with status clean / warning / quarantined.
   clean_<table> keeps clean + warning rows. Quarantined rows stay in stg_ and in
   dq_exceptions, so input = usable + quarantined, always.

Bad rows are never deleted. They are routed and labelled.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from string import Template

import duckdb
import yaml

from .config import CONTRACTS_FILE, SQL_DIR

log = logging.getLogger(__name__)

GENERIC_DIR = SQL_DIR / "checks" / "generic"
EXCEPTION_COLUMNS = "table_name, record_id, record_key, check_name, reason, severity"


@dataclass
class Check:
    name: str      # e.g. "orders.duplicate_key" or "orders_date_sequence.sql"
    sql: str


def load_contracts(path: Path = CONTRACTS_FILE) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _key_expr(cols: list[str], alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return " || '|' || ".join(f"coalesce({prefix}{c}, '<null>')" for c in cols)


def _sql_literal(value) -> str:
    return str(value) if isinstance(value, (int, float)) else "'" + str(value).replace("'", "''") + "'"


def build_staging(con: duckdb.DuckDBPyConnection, contracts: dict) -> None:
    for table, spec in contracts["tables"].items():
        cols = ",\n    ".join(f"try_cast({c} as {s['type']}) as {c}" for c, s in spec["columns"].items())
        con.execute(f"create or replace table stg_{table} as select _row_id,\n    {cols}\nfrom raw_{table}")


def generic_checks(contracts: dict) -> list[Check]:
    tpl = {p.stem: Template(p.read_text()) for p in GENERIC_DIR.glob("*.sql")}
    sev = contracts["defaults"]["severity"]
    checks: list[Check] = []
    for table, spec in contracts["tables"].items():
        pk = spec["primary_key"]
        base = {"table": table, "key_expr": _key_expr(pk)}
        checks.append(Check(f"{table}.duplicate_key", tpl["duplicate_key"].substitute(
            base, key_cols=", ".join(pk), key_not_null=" and ".join(f"{c} is not null" for c in pk),
            severity=spec.get("primary_key_severity", sev["duplicate_key"]))))
        for col, cs in spec["columns"].items():
            args = dict(base, column=col, type=cs["type"])
            if not cs.get("nullable", True):
                checks.append(Check(f"{table}.{col}.required_null",
                                    tpl["required_null"].substitute(args, severity=sev["required_null"])))
            if cs["type"] != "VARCHAR":
                checks.append(Check(f"{table}.{col}.type_mismatch",
                                    tpl["type_mismatch"].substitute(args, severity=sev["type_mismatch"])))
            if "allowed" in cs:
                checks.append(Check(f"{table}.{col}.allowed_values", tpl["allowed_values"].substitute(
                    args, allowed_list=", ".join(_sql_literal(v) for v in cs["allowed"]),
                    severity=cs.get("severity", sev["allowed_values"]))))
        for fk in spec.get("foreign_keys", []):
            ref_table, ref_col = fk["references"].split(".")
            checks.append(Check(f"{table}.{fk['column']}.orphan_foreign_key", tpl["orphan_foreign_key"].substitute(
                base, key_expr_c=_key_expr(pk, "c"), column=fk["column"], ref_table=ref_table,
                ref_column=ref_col, severity=fk.get("severity", sev["orphan_foreign_key"]))))
    return checks


def business_checks() -> list[Check]:
    return [Check(p.name, p.read_text()) for p in sorted((SQL_DIR / "checks").glob("*.sql"))]


def all_checks(contracts: dict) -> list[Check]:
    return generic_checks(contracts) + business_checks()


def run_validation(con: duckdb.DuckDBPyConnection, contracts: dict | None = None) -> dict:
    contracts = contracts or load_contracts()
    build_staging(con, contracts)

    checks = all_checks(contracts)
    union = "\nunion all\n".join(f"select {EXCEPTION_COLUMNS} from (\n{c.sql}\n)" for c in checks)
    con.execute(f"""
        create or replace table dq_exceptions as
        select
            row_number() over (order by table_name, record_id, check_name) as exception_id,
            table_name, record_id, cast(record_key as varchar) as record_key,
            check_name, reason, severity
        from ({union})
    """)

    tables = list(contracts["tables"])
    status_sql = "\nunion all\n".join(f"""
        select '{t}' as table_name, s._row_id as record_id,
               case
                   when bool_or(e.severity in ('high', 'medium')) then 'quarantined'
                   when count(e.record_id) > 0 then 'warning'
                   else 'clean'
               end as row_status
        from stg_{t} as s
        left join dq_exceptions as e on e.table_name = '{t}' and e.record_id = s._row_id
        group by s._row_id""" for t in tables)
    con.execute(f"create or replace table dq_row_status as {status_sql}")
    for t in tables:
        con.execute(f"""
            create or replace view clean_{t} as
            select s.* from stg_{t} as s
            join dq_row_status as r on r.table_name = '{t}' and r.record_id = s._row_id
            where r.row_status <> 'quarantined'
        """)

    summary = con.execute("""
        select table_name, check_name, severity, count(*) as n
        from dq_exceptions group by all order by n desc
    """).fetchall()
    for table_name, check_name, severity, n in summary:
        log.info("  %-15s %-35s %-6s %8s", table_name, check_name, severity, f"{n:,}")
    log.info("%d checks run, %s exceptions", len(checks), f"{sum(r[3] for r in summary):,}")
    return {"checks_run": len(checks)}
