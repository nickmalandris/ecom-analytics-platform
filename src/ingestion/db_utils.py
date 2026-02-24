"""
Shared database utilities for sync orchestrators.

Provides:
  - upsert_rows: Generic INSERT ... ON CONFLICT DO UPDATE with insert/update/unchanged counting
  - fmt_counts: Format upsert counts dict for display
  - fmt_summary: Format a full sync summary block for terminal output
  - get_db_url: Read DATABASE_URL from env
"""

import os

import psycopg2.extras
from psycopg2.extras import Json


def get_db_url() -> str:
    """Get the database URL from environment, with a local default."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql://analytics_user:analytics_pass@localhost:5435/analytics",
    )


def upsert_rows(
    conn,
    schema: str,
    table: str,
    columns: list[str],
    rows: list[dict],
    conflict_col: str = "id",
) -> dict[str, int]:
    """
    Generic upsert: INSERT ... ON CONFLICT DO UPDATE ... WHERE <data changed>.

    The WHERE clause uses ROW() IS DISTINCT FROM to skip updates when data
    is identical, so unchanged rows are not touched at all.

    Uses RETURNING xmax to distinguish inserts (xmax=0) from real updates
    (xmax!=0). Rows that conflict but have no changes are not returned by
    RETURNING and are counted as unchanged.

    Returns {"inserted": N, "updated": M, "unchanged": K}.
    """
    if not rows:
        return {"inserted": 0, "updated": 0, "unchanged": 0}

    col_names = ", ".join(f'"{c}"' if c == "return" else c for c in columns)
    update_cols = [c for c in columns if c != conflict_col]

    def _col_ref(c: str, prefix: str = "") -> str:
        """Quote reserved words, optionally with table/alias prefix."""
        name = f'"{c}"' if c == "return" else c
        return f"{prefix}.{name}" if prefix else name

    update_set = ", ".join(
        f"{_col_ref(c)} = EXCLUDED.{_col_ref(c)}" for c in update_cols
    )

    # WHERE clause: only update if at least one column value actually changed.
    # ROW(existing cols) IS DISTINCT FROM ROW(incoming cols) handles NULLs correctly.
    existing_row = ", ".join(f"{schema}.{table}.{_col_ref(c)}" for c in update_cols)
    excluded_row = ", ".join(f"EXCLUDED.{_col_ref(c)}" for c in update_cols)
    where_clause = f"ROW({existing_row}) IS DISTINCT FROM ROW({excluded_row})"

    sql = (
        f"INSERT INTO {schema}.{table} ({col_names}) VALUES %s "
        f"ON CONFLICT ({conflict_col}) DO UPDATE SET {update_set} "
        f"WHERE {where_clause} "
        f"RETURNING xmax"
    )

    batch = []
    for row in rows:
        values = []
        for col in columns:
            val = row.get(col)
            if isinstance(val, (dict, list)):
                values.append(Json(val))
            else:
                values.append(val)
        batch.append(tuple(values))

    inserted = 0
    updated = 0
    with conn.cursor() as cur:
        result = psycopg2.extras.execute_values(cur, sql, batch, page_size=500, fetch=True)
        for (xmax,) in result:
            if str(xmax) == "0":
                inserted += 1
            else:
                updated += 1
    conn.commit()

    unchanged = len(batch) - inserted - updated
    return {"inserted": inserted, "updated": updated, "unchanged": unchanged}


def fmt_counts(counts: dict[str, int], mode: str = "incremental") -> str:
    """Format an upsert counts dict into a readable string, omitting zero values.

    Full mode:        "N inserted"  (truncate + insert, so just total)
    Incremental mode: "N new, M updated"  (only actionable changes)
    """
    parts = []
    if mode == "full":
        total = counts.get("inserted", 0) + counts.get("updated", 0) + counts.get("unchanged", 0)
        if total:
            parts.append(f"{total} inserted")
    else:
        if counts.get("inserted"):
            parts.append(f"{counts['inserted']} new")
        if counts.get("updated"):
            parts.append(f"{counts['updated']} updated")
    return ", ".join(parts) if parts else "0"


def fmt_summary(
    summary: dict,
    resource_keys: list[tuple[str, str]],
) -> str:
    """Format a sync summary dict into a single readable block.

    Args:
        summary: Dict with "mode", "tenant_id", elapsed_seconds, and
                 per-resource count dicts.
        resource_keys: List of (dict_key, display_label) pairs for each resource.
    """
    mode = summary.get("mode", "sync")
    source = summary.get("source", "")
    title_prefix = f"{source} " if source else ""
    title = f"{title_prefix}Full Sync" if mode == "full" else f"{title_prefix}Incremental Sync"
    lines = [
        f"\n{'=' * 50}",
        f"  {title} Complete (tenant {summary.get('tenant_id', '?')})",
        f"{'=' * 50}",
    ]

    for key, label in resource_keys:
        val = summary.get(key)
        if val is None:
            continue
        if isinstance(val, dict):
            lines.append(f"  {label:<12} {fmt_counts(val, mode)}")
        else:
            lines.append(f"  {label:<12} {val}")

    elapsed = summary.get("elapsed_seconds")
    if elapsed is not None:
        lines.append(f"{'─' * 50}")
        lines.append(f"  Completed in {elapsed}s")

    lines.append(f"{'=' * 50}")
    return "\n".join(lines)
