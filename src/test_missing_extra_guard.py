"""Smoke test for the missing-Extra refresh guard."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from main import _has_extra_usage, _raw_says_extra_disabled, _is_missing_expected_extra
from usage_parser import AccountUsage, UsageData, UsageSection


def _account_with_extra() -> AccountUsage:
    return AccountUsage(
        email="user@example.com",
        usage=UsageData(sections=[
            UsageSection(label="Current session", percentage=10, reset_info="Resets 1pm"),
            UsageSection(
                label="Extra usage",
                percentage=75,
                reset_info="Resets Apr 1",
                spent_info="$1.00 / $20.00 spent",
            ),
        ]),
        last_updated="2026-04-22T10:00:00",
        is_active=True,
    )


def main():
    old_account = _account_with_extra()

    assert _has_extra_usage(old_account)
    assert not _has_extra_usage(None)

    missing_extra_usage = UsageData(raw_text="Current session 1%used Current week 2%used")
    assert _is_missing_expected_extra(old_account, missing_extra_usage)

    disabled_usage = UsageData(raw_text="Current session 1%used Current week 2%used Extra usage not enabled")
    assert _raw_says_extra_disabled(disabled_usage.raw_text)
    assert not _is_missing_expected_extra(old_account, disabled_usage)

    unrelated_usage = UsageData(raw_text="Current session 1%used Current week 2%used not enabled")
    assert not _raw_says_extra_disabled(unrelated_usage.raw_text)
    assert _is_missing_expected_extra(old_account, unrelated_usage)

    print("Missing-Extra guard test passed")


if __name__ == "__main__":
    main()
