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


# Regex patterns
_EMAIL_RE = re.compile(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)')
_SECTION_HEADER_RE = re.compile(
    r'(Current session|Current week[^\n]*|Extra usage)',
    re.IGNORECASE
)
_PERCENTAGE_RE = re.compile(r'(\d+)%\s*used')
# More inclusive regex for reset info, catching misspelled 'Reses' and missing spaces
_RESET_RE = re.compile(r'(?:Resets?|Reses?|Starts?|Ends?|Next reset|Refreshes?|Refresh|Resetting)\s*(.*)', re.IGNORECASE)
_SPENT_RE = re.compile(r'(\$[\d.]+\s*/\s*\$[\d.]+\s*spent)')


def parse_email(text: str) -> str | None:
    """Extract email address from /status output."""
    match = _EMAIL_RE.search(text)
    return match.group(1) if match else None


def parse_usage(text: str) -> UsageData:
    """
    Parse the ANSI-stripped /usage output into a UsageData object.
    Returns UsageData with error set if parsing fails.
    """
    if not text or not text.strip():
        return UsageData(error="Empty output from Claude Code")

    data = UsageData(raw_text=text)

    # Find all section headers and their positions
    headers = list(_SECTION_HEADER_RE.finditer(text))
    if not headers:
        return UsageData(
            raw_text=text,
            error="Could not parse usage data — unexpected format"
        )

    # Filter out "Extra usage" headers whose section contains "not enabled" and no percentage
    filtered_headers = []
    for i, match in enumerate(headers):
        if "Extra usage" in match.group(1):
            start = match.start()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
            section_text = text[start:end]
            if "not enabled" in section_text.lower() and not _PERCENTAGE_RE.search(section_text):
                continue
        filtered_headers.append(match)
    headers = filtered_headers

    # Extract all sections bounded by headers
    sections = []
    for i, match in enumerate(headers):
        raw_label = match.group(1)
        if "Current week" in raw_label:
            label = "Current week"
        elif "Current session" in raw_label:
            label = "Current session"
        elif "Extra usage" in raw_label:
            label = "Extra usage"
        else:
            label = raw_label.strip()

        start = match.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        section_text = text[start:end]

        pct_match = _PERCENTAGE_RE.search(section_text)
        if not pct_match:
            continue
        percentage = max(0, min(100, int(pct_match.group(1))))

        spent_match = _SPENT_RE.search(section_text)
        spent_info = spent_match.group(1).strip() if spent_match else None

        # Extract reset info within this specific bounded section
        reset_info = ""
        res_match = _RESET_RE.search(section_text)
        if res_match:
            # We use the full match group and strip any trailing cruft that might have leaked in
            reset_info = res_match.group(0).strip().replace("Esc to cancel", "").strip()
            # If the literal word "Reses" was matched, clean it up for display
            if reset_info.lower().startswith("reses"):
                reset_info = "Resets" + reset_info[5:]
            
            # Ensure there is a space after 'Resets' if followed directly by a number or character
            reset_info = re.sub(r'^(Resets)(?=[^\s])', r'\1 ', reset_info, flags=re.IGNORECASE)

            # Strip any trailing "Extra usage..." text that may have leaked from raw PTY stream
            reset_info = re.sub(r'Extra usage.*$', '', reset_info, flags=re.IGNORECASE).strip()

        sections.append(UsageSection(
            label=label,
            percentage=percentage,
            reset_info=reset_info,
            spent_info=spent_info,
        ))

    data.sections = sections
    if not data.sections:
        data.error = "Could not extract any usage sections"

    return data
