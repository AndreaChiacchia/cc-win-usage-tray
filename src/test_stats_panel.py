import unittest
from datetime import date
from unittest.mock import patch

import settings as settings_mod
from stats_panel import (
    _build_month_week_slots,
    _chart_bar_fill,
    _chart_max_value,
    _normalize_chart_value,
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
