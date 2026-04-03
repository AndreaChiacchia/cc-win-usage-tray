"""Configuration constants for Claude Usage Tray."""

# Claude CLI command (must be on PATH)
CLAUDE_CMD = "claude"

# Auto-refresh interval in milliseconds (5 minutes)
REFRESH_INTERVAL_MS = 300_000

# PTY timeout in seconds
PTY_TIMEOUT_S = 45

# PTY terminal dimensions (match cc-usage-bar)
PTY_COLS = 68
PTY_ROWS = 24

MAX_CONSECUTIVE_FAILURES = 3   # force-respawn PTY after this many timeouts

# Color thresholds (percentage)
COLOR_GREEN_MAX = 50    # 0-49%  -> green
COLOR_YELLOW_MAX = 80   # 50-79% -> yellow
                        # 80%+   -> red

# UI Colors (Claude-like dark theme)
BG_COLOR = "#1e1e1e"
FG_COLOR = "#e5e5e5"
FG_DIM_COLOR = "#8b8b8b"
BORDER_COLOR = "#333333"
BAR_BG_COLOR = "#2d2d2d"
BAR_GREEN = "#10b981"   # Emerald green
BAR_YELLOW = "#f59e0b"  # Amber
BAR_RED = "#ef4444"     # Vibrant red
BUTTON_BG = "#2d2d2d"
BUTTON_FG = "#e5e5e5"
BUTTON_ACTIVE_BG = "#3d3d3d"

# Popup dimensions
POPUP_WIDTH = 520
POPUP_PADDING = 24
TASKBAR_OFFSET = 48  # pixels above taskbar

# Tray icon size
ICON_SIZE = 64

# Notification settings
NOTIFICATION_THRESHOLD_STEP = 10  # Notify every N% (used by notifier.py)

# Progress bar
BAR_HEIGHT = 18

# Animation
ANIM_FRAME_MS = 33            # ~30 FPS
ANIM_BAR_DURATION_MS = 600    # fill transition duration (ms)
ANIM_SHIMMER_WIDTH = 65       # shimmer band width (px)
ANIM_SHIMMER_SPEED = 10       # shimmer pixels per frame
ANIM_PACE_DURATION_MS = 400   # fade+count animation for pace label (ms)

# Pace delta (burn rate indicator)
PACE_DEAD_ZONE = 5            # hide delta when abs(delta) < 5%
PACE_SESSION_WINDOW_H = 5     # session rate-limit window (hours)
PACE_WEEK_WINDOW_H = 168      # weekly rate-limit window (7 days in hours)

# Stats Panel
STATS_PANEL_WIDTH = 700
STATS_BAR_MAX_HEIGHT = 120
STATS_BAR_MIN_HEIGHT = 2
STATS_CHART_HEIGHT = 150
STATS_TOP_LABEL_HEIGHT = 16  # zone above bars for token count labels (px, 4px grid)
STATS_PIN_DURATION_MS = 1200  # ms hovering before panel becomes pinned
STATS_OPEN_DURATION_MS = 220   # slide+fade open animation (ms)
STATS_OPEN_SLIDE_PX = 24       # horizontal slide distance (px)
STATS_CLOSE_DURATION_MS = 160  # fade-out close animation (ms, ~75% of open)

# Scrollable popup content area
POPUP_MAX_CONTENT_HEIGHT = 680  # fits 2 accounts × 3 sections (~669 px); scrollbar only for 3+ accounts

# Token detail panel
CLAUDE_DATA_DIR = "~/.claude"   # base dir for Claude Code session data
TOKEN_PANEL_WIDTH = 280         # width of the token detail panel (px)
