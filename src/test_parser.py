"""Quick smoke test for the usage parser — no CLI required."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from usage_parser import parse_usage, parse_email

SAMPLE_STATUS = """
Logged in as user@example.com (Free plan)
CLI Version: 0.1.0
"""

SAMPLE_USAGE = """
Current session    ███████████████████████████████████               70%usedReses1:59pm (Europe/Rome)Current week (all models)█████████████████████▌                            43%usedResets Mar 20, 2:59pm (Europe/Rome)Esc to cancel
"""

SAMPLE_USAGE_WITH_EXTRA = """
Current session    ███████████████████████████████████               70%usedResets 1:59pm (Europe/Rome)Current week█████████████████████▌                            43%usedResets Mar 20, 2:59pm (Europe/Rome)Extra usage██████████████████████████████████████████        85%used$1.01 / $20.00 spentResets Apr 1Esc to cancel
"""

# Test parse_email
email = parse_email(SAMPLE_STATUS)
if email != "user@example.com":
    print(f"ERROR: Expected user@example.com, got {email}")
    sys.exit(1)
print(f"Email parsed OK: {email}\n")

# Test parse_usage
data = parse_usage(SAMPLE_USAGE)

if data.error:
    print(f"ERROR: {data.error}")
    sys.exit(1)

print(f"Parsed {len(data.sections)} sections:\n")
for s in data.sections:
    print(f"  [{s.percentage:3d}%] {s.label}")
    print(f"         {s.reset_info}")
    if s.spent_info:
        print(f"         {s.spent_info}")
    print()

print("Parser OK")

# Test parse_usage with Extra usage section
data2 = parse_usage(SAMPLE_USAGE_WITH_EXTRA)

if data2.error:
    print(f"ERROR (extra usage test): {data2.error}")
    sys.exit(1)

if len(data2.sections) != 3:
    print(f"ERROR: Expected 3 sections (including Extra usage), got {len(data2.sections)}")
    for s in data2.sections:
        print(f"  [{s.percentage:3d}%] {s.label}")
    sys.exit(1)

extra = next((s for s in data2.sections if s.label == "Extra usage"), None)
if extra is None:
    print("ERROR: Extra usage section not found")
    sys.exit(1)

print(f"Extra usage section OK: {extra.percentage}% | {extra.spent_info} | {extra.reset_info}")
print("Parser with Extra usage OK")
