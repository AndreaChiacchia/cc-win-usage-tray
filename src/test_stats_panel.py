import unittest
from datetime import date
from unittest.mock import Mock
from unittest.mock import patch

import settings as settings_mod
from stats_panel import (
    StatsPanel,
    _build_month_week_slots,
    _chart_bar_fill,
    _chart_max_value,
    _is_current_week,
    _normalize_chart_value,
    _peak_day_for_week,
    _week_disabled_indices,
    _week_start_for,
    _week_title,
)


def _token_slot(input_tokens: int, output_tokens: int = 0, cache_read: int = 0, cache_creation: int = 0) -> dict:
    return {
        "input": input_tokens,
        "output": output_tokens,
        "cache_read": cache_read,
        "cache_creation": cache_creation,
    }


class BuildMonthWeekSlotsTests(unittest.TestCase):
    def test_clips_first_and_last_calendar_weeks(self):
        month_start = date(2026, 3, 1)
        days_in_month = 31
        today = date(2026, 3, 31)
        month_data = [10] * days_in_month
        month_tokens = [_token_slot(1)] * days_in_month

        slots = _build_month_week_slots(month_start, days_in_month, today, month_data, month_tokens)

        self.assertEqual(6, len(slots))
        self.assertEqual(date(2026, 3, 1), slots[0]["start"])
        self.assertEqual(date(2026, 3, 1), slots[0]["end"])
        self.assertEqual("1", slots[0]["label"])
        self.assertEqual(date(2026, 3, 30), slots[-1]["start"])
        self.assertEqual(date(2026, 3, 31), slots[-1]["end"])
        self.assertEqual("30-31", slots[-1]["label"])

    def test_partial_current_week_excludes_future_days_from_aggregation(self):
        month_start = date(2026, 3, 1)
        days_in_month = 31
        today = date(2026, 3, 26)
        month_data = [0] * days_in_month
        month_tokens = [_token_slot(0)] * days_in_month
        values = {
            23: (30, _token_slot(10, 1, 2, 3)),
            24: (40, _token_slot(20, 2, 3, 4)),
            25: (50, _token_slot(30, 3, 4, 5)),
            26: (60, _token_slot(40, 4, 5, 6)),
            27: (99, _token_slot(999, 0, 0, 0)),
            28: (99, _token_slot(999, 0, 0, 0)),
            29: (99, _token_slot(999, 0, 0, 0)),
        }
        for day, (pct, tokens) in values.items():
            month_data[day - 1] = pct
            month_tokens[day - 1] = tokens

        slots = _build_month_week_slots(month_start, days_in_month, today, month_data, month_tokens)
        current_week = next(slot for slot in slots if slot["start"] == date(2026, 3, 23))

        self.assertFalse(current_week["disabled"])
        self.assertEqual(45, current_week["pct"])
        self.assertEqual(100, current_week["tokens"]["input"])
        self.assertEqual(10, current_week["tokens"]["output"])
        self.assertEqual(14, current_week["tokens"]["cache_read"])
        self.assertEqual(18, current_week["tokens"]["cache_creation"])
        self.assertEqual(date(2026, 3, 26), current_week["selected_date"])

    def test_fully_future_week_is_disabled(self):
        month_start = date(2026, 3, 1)
        days_in_month = 31
        today = date(2026, 3, 26)
        month_data = [0] * days_in_month
        month_tokens = [_token_slot(0)] * days_in_month

        slots = _build_month_week_slots(month_start, days_in_month, today, month_data, month_tokens)
        future_week = next(slot for slot in slots if slot["start"] == date(2026, 3, 30))

        self.assertTrue(future_week["disabled"])
        self.assertEqual(0, future_week["pct"])
        self.assertEqual(0, future_week["tokens"]["input"])
        self.assertIsNone(future_week["selected_date"])


class SelectedWeekHelperTests(unittest.TestCase):
    def test_week_start_for_current_week_day(self):
        self.assertEqual(date(2026, 3, 23), _week_start_for(date(2026, 3, 26)))

    def test_week_start_for_past_week_day(self):
        self.assertEqual(date(2026, 3, 16), _week_start_for(date(2026, 3, 18)))

    def test_week_title_uses_this_week_for_current_week(self):
        today = date(2026, 3, 26)
        self.assertEqual("This Week", _week_title(today, today))

    def test_week_title_uses_explicit_range_for_past_week(self):
        self.assertEqual("16 Mar - 22 Mar", _week_title(date(2026, 3, 18), date(2026, 3, 26)))

    def test_week_disabled_indices_only_apply_to_current_week(self):
        self.assertEqual({4, 5, 6}, _week_disabled_indices(date(2026, 3, 23), date(2026, 3, 26)))
        self.assertEqual(set(), _week_disabled_indices(date(2026, 3, 16), date(2026, 3, 26)))

    def test_is_current_week_detects_matching_calendar_week(self):
        self.assertTrue(_is_current_week(date(2026, 3, 24), date(2026, 3, 26)))
        self.assertFalse(_is_current_week(date(2026, 3, 18), date(2026, 3, 26)))

    def test_peak_day_for_week_uses_unique_max(self):
        self.assertEqual(
            date(2026, 3, 18),
            _peak_day_for_week(date(2026, 3, 16), [10, 20, 80, 15, 5, 0, 0], date(2026, 3, 26)),
        )

    def test_peak_day_for_week_uses_latest_day_on_tie(self):
        self.assertEqual(
            date(2026, 3, 19),
            _peak_day_for_week(date(2026, 3, 16), [10, 50, 20, 50, 5, 0, 0], date(2026, 3, 26)),
        )

    def test_peak_day_for_week_uses_latest_day_when_all_zero(self):
        self.assertEqual(
            date(2026, 3, 22),
            _peak_day_for_week(date(2026, 3, 16), [0, 0, 0, 0, 0, 0, 0], date(2026, 3, 26)),
        )


class StatsPanelSelectionTests(unittest.TestCase):
    def test_week_selected_index_uses_displayed_week_context(self):
        panel = StatsPanel.__new__(StatsPanel)
        panel._selected_date = date(2026, 3, 18)
        panel._week_chart_context = {"week_start": date(2026, 3, 16)}

        self.assertEqual(2, panel._get_week_selected_index())

    def test_set_selected_date_rerenders_selected_day_and_week_sections(self):
        panel = StatsPanel.__new__(StatsPanel)
        panel._current_email = "test@example.com"
        panel._selected_date = date(2026, 3, 26)
        panel._render_selected_day_section = Mock()
        panel._render_week_section = Mock()
        panel._month_chart_redraw = Mock()
        panel._build_week_chart_context = Mock(return_value={"week_start": date(2026, 3, 16)})

        with patch("stats_panel._now", return_value=Mock(date=Mock(return_value=date(2026, 3, 26)))):
            panel._set_selected_date(date(2026, 3, 18))

        self.assertEqual(date(2026, 3, 18), panel._selected_date)
        panel._render_selected_day_section.assert_called_once_with("test@example.com")
        panel._build_week_chart_context.assert_called_once()
        panel._render_week_section.assert_called_once_with()
        panel._month_chart_redraw.assert_called_once_with()

    def test_resolve_month_selection_date_uses_peak_day_for_past_week(self):
        panel = StatsPanel.__new__(StatsPanel)
        panel._current_email = "test@example.com"
        panel._selected_date = date(2026, 3, 26)

        with patch("stats_panel._now", return_value=Mock(date=Mock(return_value=date(2026, 3, 26)))):
            with patch("stats_panel.usage_history.get_daily_delta", return_value=[10, 60, 15, 80, 40, 0, 0]) as daily_delta:
                resolved = panel._resolve_month_selection_date(date(2026, 3, 18))

        self.assertEqual(date(2026, 3, 19), resolved)
        daily_delta.assert_called_once_with("test@example.com", date(2026, 3, 16), 7, "Current week")

    def test_resolve_month_selection_date_uses_latest_peak_day_for_ties(self):
        panel = StatsPanel.__new__(StatsPanel)
        panel._current_email = "test@example.com"
        panel._selected_date = date(2026, 3, 26)

        with patch("stats_panel._now", return_value=Mock(date=Mock(return_value=date(2026, 3, 26)))):
            with patch("stats_panel.usage_history.get_daily_delta", return_value=[10, 80, 15, 80, 40, 0, 0]):
                resolved = panel._resolve_month_selection_date(date(2026, 3, 18))

        self.assertEqual(date(2026, 3, 19), resolved)

    def test_resolve_month_selection_date_keeps_clicked_day_in_current_week(self):
        panel = StatsPanel.__new__(StatsPanel)
        panel._current_email = "test@example.com"
        panel._selected_date = date(2026, 3, 26)

        with patch("stats_panel._now", return_value=Mock(date=Mock(return_value=date(2026, 3, 26)))):
            with patch("stats_panel.usage_history.get_daily_delta") as daily_delta:
                resolved = panel._resolve_month_selection_date(date(2026, 3, 24))

        self.assertEqual(date(2026, 3, 24), resolved)
        daily_delta.assert_not_called()

    def test_resolve_month_selection_date_keeps_clicked_day_within_same_past_week(self):
        panel = StatsPanel.__new__(StatsPanel)
        panel._current_email = "test@example.com"
        panel._selected_date = date(2026, 3, 18)

        with patch("stats_panel._now", return_value=Mock(date=Mock(return_value=date(2026, 3, 26)))):
            with patch("stats_panel.usage_history.get_daily_delta") as daily_delta:
                resolved = panel._resolve_month_selection_date(date(2026, 3, 17))

        self.assertEqual(date(2026, 3, 17), resolved)
        daily_delta.assert_not_called()


class ChartBarModeTests(unittest.TestCase):
    def test_color_mode_uses_vivid_color_at_max_value(self):
        fill = _chart_bar_fill("#10b981", "#2d2d2d", "#1e1e1e", 100, "color")
        self.assertEqual("#10b981", fill)

    def test_color_mode_dims_mid_value(self):
        fill = _chart_bar_fill("#10b981", "#2d2d2d", "#1e1e1e", 50, "color")
        self.assertEqual("#1c795a", fill)

    def test_color_mode_renders_zero_as_faint_full_bar(self):
        fill = _chart_bar_fill("#10b981", "#2d2d2d", "#1e1e1e", 0, "color")
        self.assertEqual("#273833", fill)

    def test_disabled_slots_keep_existing_disabled_treatment(self):
        fill = _chart_bar_fill("#10b981", "#2d2d2d", "#1e1e1e", 50, "color", disabled=True)
        self.assertEqual("#167354", fill)

    def test_hourly_chart_normalization_stays_local_to_chart_max(self):
        data = [0] * 24
        data[10] = 6
        data[11] = 12

        max_val = _chart_max_value(data)

        self.assertEqual(12, max_val)
        self.assertEqual(50, _normalize_chart_value(data[10], max_val))
        self.assertEqual(100, _normalize_chart_value(data[11], max_val))

    def test_weekly_chart_normalization_ignores_disabled_future_slots(self):
        data = [12, 20, 40, 10, 8, 99, 99]
        disabled = {5, 6}

        max_val = _chart_max_value(data, disabled)

        self.assertEqual(40, max_val)
        self.assertEqual(50, _normalize_chart_value(data[1], max_val))
        self.assertEqual(100, _normalize_chart_value(data[2], max_val))

    def test_monthly_chart_normalization_stays_local_to_visible_data(self):
        data = [0] * 31
        data[4] = 40
        data[9] = 80
        data[30] = 99
        disabled = {30}

        max_val = _chart_max_value(data, disabled)

        self.assertEqual(80, max_val)
        self.assertEqual(50, _normalize_chart_value(data[4], max_val))
        self.assertEqual(100, _normalize_chart_value(data[9], max_val))


class StatsBarModeSettingsTests(unittest.TestCase):
    def test_defaults_to_fill_when_setting_is_missing(self):
        with patch.object(settings_mod, "load_settings", return_value={}):
            self.assertEqual("fill", settings_mod.get_stats_bar_mode())

    def test_persists_and_reloads_chart_mode(self):
        store = {}

        def fake_load_settings():
            return {
                key: value.copy() if isinstance(value, dict) else value
                for key, value in store.items()
            }

        def fake_save_settings(settings: dict):
            store.clear()
            store.update({
                key: value.copy() if isinstance(value, dict) else value
                for key, value in settings.items()
            })

        with patch.object(settings_mod, "load_settings", side_effect=fake_load_settings):
            with patch.object(settings_mod, "save_settings", side_effect=fake_save_settings):
                settings_mod.set_stats_bar_mode("color")
                self.assertEqual("color", settings_mod.get_stats_bar_mode())


if __name__ == "__main__":
    unittest.main()
