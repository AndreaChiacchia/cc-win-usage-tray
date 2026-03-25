"""Account state persistence for Claude Usage Tray — SQLite backend."""

from datetime import datetime

import db
from usage_parser import AccountUsage, UsageData, UsageSection


def load_all_accounts() -> dict[str, AccountUsage]:
    """Load all accounts and their sections from the DB."""
    conn = db.get_connection()
    acc_rows = conn.execute(
        "SELECT email, last_updated, is_active, raw_text, error FROM accounts"
    ).fetchall()
    if not acc_rows:
        return {}

    sec_rows = conn.execute(
        "SELECT email, label, percentage, reset_info, spent_info FROM account_sections"
    ).fetchall()

    # Group sections by email
    sections_by_email: dict[str, list[UsageSection]] = {}
    for email, label, pct, reset_info, spent_info in sec_rows:
        sections_by_email.setdefault(email, []).append(
            UsageSection(
                label=label,
                percentage=pct,
                reset_info=reset_info or "",
                spent_info=spent_info,
            )
        )

    result: dict[str, AccountUsage] = {}
    for email, last_updated, is_active, raw_text, error in acc_rows:
        usage = UsageData(
            sections=sections_by_email.get(email, []),
            raw_text=raw_text or "",
            error=error,
        )
        result[email] = AccountUsage(
            email=email,
            usage=usage,
            last_updated=last_updated,
            is_active=bool(is_active),
        )
    return result


def save_all_accounts(accounts: dict[str, AccountUsage]) -> None:
    """Upsert all accounts and their sections in a single transaction."""
    conn = db.get_connection()
    with conn:
        for email, acc in accounts.items():
            _upsert_account(conn, acc)


def save_account(account: AccountUsage) -> None:
    """Upsert a single account."""
    conn = db.get_connection()
    with conn:
        _upsert_account(conn, account)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _upsert_account(conn, acc: AccountUsage) -> None:
    conn.execute(
        """INSERT INTO accounts(email, last_updated, is_active, raw_text, error)
           VALUES (?,?,?,?,?)
           ON CONFLICT(email) DO UPDATE SET
               last_updated=excluded.last_updated,
               is_active=excluded.is_active,
               raw_text=excluded.raw_text,
               error=excluded.error""",
        (
            acc.email,
            acc.last_updated,
            1 if acc.is_active else 0,
            acc.usage.raw_text,
            acc.usage.error,
        ),
    )
    # Replace sections for this account
    conn.execute("DELETE FROM account_sections WHERE email=?", (acc.email,))
    for sec in acc.usage.sections:
        conn.execute(
            """INSERT INTO account_sections(email, label, percentage, reset_info, spent_info)
               VALUES (?,?,?,?,?)""",
            (acc.email, sec.label, sec.percentage, sec.reset_info or "", sec.spent_info),
        )
