"""Parse /usage output from Claude Code CLI into structured data."""

import re
from dataclasses import dataclass, field


@dataclass
class UsageSection:
    label: str
    percentage: int
    reset_info: str
    spent_info: str | None = None


@dataclass
class UsageData:
    sections: list[UsageSection] = field(default_factory=list)
    raw_text: str = ""
    error: str | None = None


@dataclass
class AccountUsage:
    email: str
    usage: UsageData
    last_updated: str  # ISO 8601 timestamp
    is_active: bool = False


_EMAIL_RE = re.compile(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)')
_LABELED_EMAIL_RE = re.compile(
    r'(?<![A-Za-z])Email:\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)',
    re.IGNORECASE,
)
_ORG_EMAIL_RE = re.compile(
    r'(?<![A-Za-z])OrganizationEmail:\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)',
    re.IGNORECASE,
)
_SECTION_LABELS = (
    ("Current session", re.compile(r'Current session', re.IGNORECASE)),
    ("Current week", re.compile(r'Current week(?:\s*\(all models\))?', re.IGNORECASE)),
    ("Extra usage", re.compile(r'Extra usage', re.IGNORECASE)),
)
_SECTION_BOUNDARY_RE = re.compile(
    r"Current session|Current week(?:\s*\(all models\))?|Extra usage|Esc to cancel|"
    r"What's contributing to your limits usage\?|"
    r"Approximate, based on local sessions on this machine|"
    r"Scanning local sessions|Refreshing|Last 24h|"
    r"Status\s*Config\s*Usage\s*Stats|StatusConfig",
    re.IGNORECASE,
)
_PERCENTAGE_RE = re.compile(r'(\d{1,3})%\s*used', re.IGNORECASE)
_RESET_PREFIX_RE = re.compile(
    r'(?:Resets?|Reses?|Starts?|Ends?|Next reset|Resetting|Refreshes?(?!ing)|Refresh(?!ing))\s*',
    re.IGNORECASE,
)
_SPENT_RE = re.compile(r'(\$[\d.]+\s*/\s*\$[\d.]+\s*spent)', re.IGNORECASE)


def parse_email(text: str) -> str | None:
    """Extract the account email from /status output."""
    for pattern in (_LABELED_EMAIL_RE, _ORG_EMAIL_RE):
        match = pattern.search(text)
        if match:
            return match.group(1)
    match = _EMAIL_RE.search(text)
    return match.group(1) if match else None


def _normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _canonical_label(raw_label: str) -> str:
    lowered = raw_label.lower()
    if lowered.startswith("current session"):
        return "Current session"
    if lowered.startswith("current week"):
        return "Current week"
    if lowered.startswith("extra usage"):
        return "Extra usage"
    return raw_label.strip()


def _find_boundary(text: str, start: int) -> int:
    match = _SECTION_BOUNDARY_RE.search(text, start)
    return match.start() if match else len(text)


def _parse_section(section_text: str, label: str) -> UsageSection | None:
    pct_match = _PERCENTAGE_RE.search(section_text)
    if not pct_match:
        return None

    percentage = max(0, min(100, int(pct_match.group(1))))
    spent_match = _SPENT_RE.search(section_text)
    spent_info = spent_match.group(1).strip() if spent_match else None

    reset_info = ""
    remainder = section_text[pct_match.end():]
    prefix_match = _RESET_PREFIX_RE.search(remainder)
    if prefix_match:
        reset_value_start = prefix_match.end()
        reset_value_end = _find_boundary(remainder, reset_value_start)
        reset_value = remainder[reset_value_start:reset_value_end].strip()
        reset_value = re.sub(r'\s+', ' ', reset_value).strip(" .")
        if reset_value:
            reset_info = f"Resets {reset_value}"
        else:
            reset_info = "Resets"

    if label == "Extra usage" and "not enabled" in section_text.lower() and not pct_match:
        return None

    return UsageSection(
        label=label,
        percentage=percentage,
        reset_info=reset_info,
        spent_info=spent_info,
    )


def parse_usage(text: str) -> UsageData:
    """
    Parse the ANSI-stripped /usage output into a UsageData object.
    Returns UsageData with error set if parsing fails.
    """
    if not text or not text.strip():
        return UsageData(error="Empty output from Claude Code")

    data = UsageData(raw_text=text)
    normalized = _normalize_whitespace(text)
    if not normalized:
        return UsageData(raw_text=text, error="Could not parse usage data â€” unexpected format")

    matches: list[tuple[int, int, str]] = []
    for label, pattern in _SECTION_LABELS:
        for match in pattern.finditer(normalized):
            matches.append((match.start(), match.end(), label))

    if not matches:
        return UsageData(
            raw_text=text,
            error="Could not parse usage data â€” unexpected format"
        )

    matches.sort(key=lambda item: item[0])

    parsed_by_label: dict[str, UsageSection] = {}
    for index, (start, match_end, label) in enumerate(matches):
        next_start = matches[index + 1][0] if index + 1 < len(matches) else len(normalized)
        end = min(next_start, _find_boundary(normalized, match_end))
        section_text = normalized[start:end].strip()
        parsed = _parse_section(section_text, _canonical_label(label))
        if parsed is not None:
            parsed_by_label[parsed.label] = parsed

    sections: list[UsageSection] = []
    for label in ("Current session", "Current week", "Extra usage"):
        section = parsed_by_label.get(label)
        if section is not None:
            sections.append(section)

    data.sections = sections
    if not data.sections:
        data.error = "Could not extract any usage sections"

    return data
