"""Build a Gregorian-backed grid for a Persian Jalali month."""

from datetime import timedelta

import jdatetime

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
WEEKDAYS = tuple(jdatetime.date.j_weekdays_fa)


def to_persian_digits(value):
    return str(value).translate(PERSIAN_DIGITS)


def month_parameter(year, month):
    return f"{year:04d}-{month:02d}"


def build_month(year, month, holidays_by_jalali_date=None):
    """Return month labels and week rows; each week begins on Saturday."""
    holidays_by_jalali_date = holidays_by_jalali_date or {}
    first_day = jdatetime.date(year, month, 1, locale=jdatetime.FA_LOCALE)
    if month <= 6:
        days_in_month = 31
    elif month <= 11:
        days_in_month = 30
    else:
        days_in_month = 30 if first_day.isleap() else 29

    leading_days = first_day.weekday()
    week_count = (leading_days + days_in_month + 6) // 7
    gregorian_first = first_day.togregorian()
    weeks = []

    for week_index in range(week_count):
        week = []
        for weekday_index in range(7):
            offset = week_index * 7 + weekday_index - leading_days
            gregorian_day = gregorian_first + timedelta(days=offset)
            jalali_day = jdatetime.date.fromgregorian(
                date=gregorian_day, locale=jdatetime.FA_LOCALE
            )
            in_month = jalali_day.year == year and jalali_day.month == month
            label = (
                f"{jalali_day.jweekday()} {to_persian_digits(jalali_day.day)} "
                f"{jalali_day.jmonth()} {to_persian_digits(jalali_day.year)}"
            )
            holiday_names = tuple(
                holidays_by_jalali_date.get(jalali_day.isoformat(), ())
            )
            week.append(
                {
                    "day": to_persian_digits(jalali_day.day),
                    "date": gregorian_day.isoformat(),
                    "accessible_date": label,
                    "in_month": in_month,
                    "is_friday": jalali_day.weekday() == 6,
                    "holiday_names": holiday_names,
                    "is_official_holiday": bool(holiday_names),
                }
            )
        weeks.append(week)

    previous_month = None
    if (year, month) > (jdatetime.MINYEAR, 1):
        previous_month = month_parameter(
            year - 1 if month == 1 else year,
            12 if month == 1 else month - 1,
        )

    next_month = None
    if (year, month) < (jdatetime.MAXYEAR, 12):
        next_month = month_parameter(
            year + 1 if month == 12 else year,
            1 if month == 12 else month + 1,
        )

    return {
        "month_title": f"{first_day.jmonth()} {to_persian_digits(year)}",
        "weekdays": WEEKDAYS,
        "weeks": weeks,
        "has_official_holidays": any(
            cell["in_month"] and cell["is_official_holiday"]
            for week in weeks
            for cell in week
        ),
        "previous_month": previous_month,
        "next_month": next_month,
    }
