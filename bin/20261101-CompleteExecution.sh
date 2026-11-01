#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if [[ -n "${PYTHON:-}" ]]; then
    PYTHON_CMD="${PYTHON}"
elif [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    PYTHON_CMD="${PROJECT_ROOT}/.venv/bin/python"
else
    PYTHON_CMD="python3"
fi

TODAY_UTC="$(date -u +%Y%m%d)"
TODAY_ISO="$(date -u +%F)"
DATA_DIR="${PROJECT_ROOT}/data/${TODAY_UTC}"
ELIGIBILITY_REPORT="${DATA_DIR}/eligibility-report.txt"
ELIGIBLE_INSTRUMENTS="${DATA_DIR}/eligible-instruments.txt"

cd "${PROJECT_ROOT}"
mkdir -p "${DATA_DIR}"

printf 'Downloading the public Investing.com ETF catalog through %s.\n' "${TODAY_ISO}"
"${PYTHON_CMD}" "${SCRIPT_DIR}/download_investing_etfs.py" \
    --end "${TODAY_ISO}" \
    --output "${DATA_DIR}" \
    --resume

printf '\nApplying transparent eligibility rules for default rolling windows.\n'
"${PYTHON_CMD}" - "${DATA_DIR}" "${ELIGIBILITY_REPORT}" "${ELIGIBLE_INSTRUMENTS}" <<'PY'
import calendar
import csv
import math
import re
import sys
from datetime import date, timedelta
from pathlib import Path

data_dir = Path(sys.argv[1])
report_path = Path(sys.argv[2])
eligible_path = Path(sys.argv[3])
csv_paths = sorted(data_dir.glob("*.csv"))
records = []
excluded = []
minimum_history_years = 5
minimum_common_observations = minimum_history_years * 200

for path in csv_paths:
    first = last = None
    previous = None
    observation_dates = []
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if not {"date", "close"}.issubset(reader.fieldnames or ()):
                raise ValueError("missing date/close columns")
            for row in reader:
                day = date.fromisoformat(row["date"])
                close = float(row["close"])
                if not math.isfinite(close) or close <= 0:
                    raise ValueError(f"non-positive or invalid close on {day}")
                if previous is not None and day <= previous:
                    raise ValueError(f"dates are not strictly increasing at {day}")
                first = day if first is None else first
                last = day
                previous = day
                observation_dates.append(day)
        if first is None or last is None:
            raise ValueError("no price observations")
    except (OSError, KeyError, TypeError, ValueError, UnicodeError) as error:
        excluded.append((path.name, f"invalid price history: {error}"))
        continue
    records.append((path.stem, first, last, path, observation_dates))

if not records:
    raise SystemExit("No CSV has a valid positive price history.")

latest = max(record[2] for record in records)
freshness_cutoff = latest - timedelta(days=7)
fresh = []
for name, first, last, path, days in records:
    if last < freshness_cutoff:
        excluded.append((path.name, f"stale history ends {last}"))
    else:
        fresh.append((name, first, last, path, days))

if not fresh:
    raise SystemExit("No recent ETF histories remain after freshness screening.")

groups = {}
for record in fresh:
    name, first, last, path, days = record
    identity = re.sub(r"_\d{8}_\d{8}$", "", name)
    groups.setdefault(identity, []).append(record)

deduplicated = []
for records_for_etf in groups.values():
    selected = max(
        records_for_etf,
        key=lambda record: (record[2], -record[1].toordinal(), record[0]),
    )
    deduplicated.append(selected)
    for duplicate in records_for_etf:
        if duplicate != selected:
            excluded.append(
                (
                    duplicate[3].name,
                    f"duplicate history; using {selected[3].name}",
                )
            )

common_end = min(record[2] for record in deduplicated)
cutoff_year = common_end.year - minimum_history_years
history_cutoff = date(
    cutoff_year,
    common_end.month,
    min(common_end.day, calendar.monthrange(cutoff_year, common_end.month)[1]),
)
history_eligible = []
for name, first, last, path, days in deduplicated:
    if first > history_cutoff:
        excluded.append(
            (path.name, f"insufficient history: starts {first}; needs <= {history_cutoff}")
        )
    else:
        history_eligible.append((name, first, last, path, days))

if not history_eligible:
    raise SystemExit(f"No ETFs have {minimum_history_years} years of history.")

history_eligible.sort(
    key=lambda record: (
        -sum(history_cutoff <= day <= common_end for day in record[4]),
        record[0],
    )
)
eligible = []
shared_dates = set()
for record in history_eligible:
    name, first, last, path, days = record
    window_dates = {
        day for day in days if history_cutoff <= day <= common_end
    }
    candidate_dates = (
        window_dates if not eligible else shared_dates.intersection(window_dates)
    )
    if len(candidate_dates) < minimum_common_observations:
        excluded.append(
            (
                path.name,
                "insufficient shared trading dates: "
                f"{len(candidate_dates)}; needs >= {minimum_common_observations}",
            )
        )
        continue
    eligible.append(name)
    shared_dates = candidate_dates

if not eligible:
    raise SystemExit(
        "No ETFs share enough dates for the default rolling windows."
    )

eligible_path.write_text(
    "".join(f"{name}.csv\n" for name in eligible), encoding="utf-8"
)
common_start = min(shared_dates)
common_end = max(shared_dates)

lines = [
    "Eligibility policy: exclude malformed/non-positive histories, histories ending",
    "more than 7 calendar days before the latest available CSV date, and histories",
    "starting after the common end date minus 5 calendar years. Five years preserve",
    "the default 3-year training, 1-year validation, and 1-year out-of-sample windows.",
    "Further exclude instruments that leave fewer than 1,000 common price dates",
    "when added in descending order of available observations.",
    f"CSV histories scanned: {len(csv_paths)}",
    f"Latest available history date: {latest}",
    f"Eligible instruments: {len(eligible)}",
    f"Eligible common price range: {common_start} to {common_end}",
    f"Excluded CSV histories/files: {len(excluded)}",
]
lines.extend(f"EXCLUDED {name}: {reason}" for name, reason in excluded)
report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
PY

mapfile -t ELIGIBLE_INSTRUMENT_LIST < "${ELIGIBLE_INSTRUMENTS}"
if [[ "${#ELIGIBLE_INSTRUMENT_LIST[@]}" -eq 0 ]]; then
    printf 'Eligibility screening returned no ETFs.\n' >&2
    exit 1
fi

printf '\nSelecting eligible ETFs with absolute return correlation below 0.4.\n'
if ! SELECTION_OUTPUT="$(
    "${PYTHON_CMD}" "${SCRIPT_DIR}/select_uncorrelated_etfs.py" \
        --data-dir "${DATA_DIR}" \
        --instruments "${ELIGIBLE_INSTRUMENT_LIST[@]}" \
        --max-abs-correlation 0.4
)"; then
    printf '%s\n' "${SELECTION_OUTPUT}" >&2
    exit 1
fi
printf '%s\n' "${SELECTION_OUTPUT}"

SELECTED_LINE="$(
    printf '%s\n' "${SELECTION_OUTPUT}" |
        sed -n 's/^Selected instruments ([0-9][0-9]*): //p'
)"
if [[ -z "${SELECTED_LINE}" || "${SELECTED_LINE}" == "(none)" ]]; then
    printf 'Correlation selection returned no ETFs; skipping optimization.\n' >&2
    exit 1
fi

IFS=',' read -r -a SELECTED_INSTRUMENTS <<< "${SELECTED_LINE}"
for index in "${!SELECTED_INSTRUMENTS[@]}"; do
    SELECTED_INSTRUMENTS[index]="${SELECTED_INSTRUMENTS[index]# }.csv"
done

printf '\nRunning the default three-year rolling max-Sharpe backtest for %s ETFs.\n' \
    "${#SELECTED_INSTRUMENTS[@]}"
"${PYTHON_CMD}" "${SCRIPT_DIR}/rolling_backtest.py" \
    --data-dir "${DATA_DIR}" \
    --instruments "${SELECTED_INSTRUMENTS[@]}" \
    --strategy max_sharpe
