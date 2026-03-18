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
