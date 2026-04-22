"""Quick smoke test for the usage parser - no CLI required."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from usage_parser import parse_usage, parse_email


SAMPLE_STATUS = """
Login method: ClaudePro account
OrganizationEmail: org@example.com
Email: user@example.com
CLI Version: 0.1.0
"""

SAMPLE_USAGE = """
Current session 70%usedReses1:59pm (Europe/Rome)Current week (all models)43%usedResets Mar 20, 2:59pm (Europe/Rome)Esc to cancel
"""

SAMPLE_USAGE_WITH_EXTRA = """
Current session 70%usedResets 1:59pm (Europe/Rome)Current week43%usedResets Mar 20, 2:59pm (Europe/Rome)Extra usage85%used$1.01 / $20.00 spentResets Apr 1Esc to cancel
"""

SAMPLE_USAGE_DUPLICATE_RENDER = """
Status Config Usage Stats
Current session 1%usedResets 1pm (Europe/Rome)
Current week (all models)55%usedResets Apr 24, 9am (Europe/Rome)
What's contributing to your limits usage? Approximate, based on local sessions on this machine - does not include other devices or claude.ai
Scanning local sessions...
Refreshing...
Status Config Usage Stats
Current session 1%usedResets 1pm (Europe/Rome)
Current week (all models)55%usedResets Apr 24, 9am (Europe/Rome)
Last 24h - 38% of your usage came from subagent-heavy sessions.
"""


def _assert_section(section, label, percentage, reset_info, spent_info=None):
    assert section.label == label, f"Expected label {label}, got {section.label}"
    assert section.percentage == percentage, f"Expected {percentage}%, got {section.percentage}%"
    assert section.reset_info == reset_info, f"Expected reset_info {reset_info!r}, got {section.reset_info!r}"
    assert section.spent_info == spent_info, f"Expected spent_info {spent_info!r}, got {section.spent_info!r}"


def main():
    email = parse_email(SAMPLE_STATUS)
    assert email == "user@example.com", f"Expected user@example.com, got {email}"
    print(f"Email parsed OK: {email}")

    data = parse_usage(SAMPLE_USAGE)
    assert not data.error, data.error
    assert len(data.sections) == 2, f"Expected 2 sections, got {len(data.sections)}"
    _assert_section(data.sections[0], "Current session", 70, "Resets 1:59pm (Europe/Rome)")
    _assert_section(data.sections[1], "Current week", 43, "Resets Mar 20, 2:59pm (Europe/Rome)")
    print("Compact usage sample parsed OK")

    data2 = parse_usage(SAMPLE_USAGE_WITH_EXTRA)
    assert not data2.error, data2.error
    assert len(data2.sections) == 3, f"Expected 3 sections, got {len(data2.sections)}"
    extra = next((s for s in data2.sections if s.label == "Extra usage"), None)
    assert extra is not None, "Extra usage section not found"
    _assert_section(extra, "Extra usage", 85, "Resets Apr 1", "$1.01 / $20.00 spent")
    print("Extra usage sample parsed OK")

    data3 = parse_usage(SAMPLE_USAGE_DUPLICATE_RENDER)
    assert not data3.error, data3.error
    assert len(data3.sections) == 2, f"Expected 2 sections, got {len(data3.sections)}"
    _assert_section(data3.sections[0], "Current session", 1, "Resets 1pm (Europe/Rome)")
    _assert_section(data3.sections[1], "Current week", 55, "Resets Apr 24, 9am (Europe/Rome)")
    assert "What's contributing" not in data3.sections[1].reset_info
    assert "subagent-heavy" not in data3.sections[1].reset_info
    print("Duplicate render sample parsed OK")

    print("Parser smoke test passed")


if __name__ == "__main__":
    main()
