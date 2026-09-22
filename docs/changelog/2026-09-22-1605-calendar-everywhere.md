# 2.0.2: one calendar for every date filter

- Vehicle and trip pages drop their `<select>` of service dates for the calendar, as a `date` control on `ScopeBar` over `?date=`. No date picker outside `DateRange` remains.
- `DateRange` takes a plain `string[]` (one entity's service days) as well as `DayInfo[]`. In single-day mode it disables days with no data and drops the range fill.
- The popup opens leftwards when its trigger sits in the right half of the window; it ran off-screen on the vehicle and trip pages.
- Selected days are circles, not rounded squares: the fill moved to a centred 26 px `::before`, and a range's end cells carry only their inner half of the band, so the bar runs centre to centre.
- Today is a ring instead of an underline, hidden when that day is selected.
- Dropped the green per-day coverage dot: a day with data already reads in `--ink` against `--faint`, and gaps belong on Data health.
