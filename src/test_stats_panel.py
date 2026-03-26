import unittest
from datetime import date

from stats_panel import _build_month_week_slots


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


if __name__ == "__main__":
    unittest.main()
