from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Iterator

import pandas as pd
import requests
from pandas.errors import EmptyDataError
from collections.abc import Iterable

from .constants import (
    BASE_URL,
    RETRY_DELAY_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    REQUEST_DELAY_SECONDS,
    DEFAULT_HEADERS,
)

# SETTINGS
STATIONS: list[str] = []
START_DATE = datetime.min
END_DATE = datetime.min
HOURS = [0, 12]

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = SCRIPT_DIR / "output.csv"
PROGRESS_FILE = OUTPUT_FILE.with_name(
    f"{OUTPUT_FILE.stem}_progress.csv"
)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)

def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session

def get_completed_launches(output_file: Path) -> set[tuple[str, int, str]]:
    """Get launches that already have saved data rows in the main CSV."""
    if not output_file.exists() or output_file.stat().st_size == 0:
        return set()

    try:
        old = pd.read_csv(
            output_file,
            usecols=["Launch_Date", "UTC", "Station"],
            dtype={"Station": str},
        )

        old["Launch_Date"] = pd.to_datetime(
            old["Launch_Date"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")

        old["UTC"] = pd.to_numeric(old["UTC"], errors="coerce")
        old = old.dropna(subset=["Launch_Date", "UTC", "Station"])

        return set(
            zip(
                old["Launch_Date"],
                old["UTC"].astype(int),
                old["Station"],
            )
        )

    except (EmptyDataError, ValueError) as exc:
        logging.warning("Could not read data CSV for resume: %s", exc)
        return set()

def get_no_data_launches(progress_file: Path) -> set[tuple[str, int, str]]:
    """Get launches where the server previously confirmed no data."""
    if not progress_file.exists() or progress_file.stat().st_size == 0:
        return set()

    try:
        progress = pd.read_csv(progress_file, dtype={"Station": str})

        progress["Launch_Date"] = pd.to_datetime(
            progress["Launch_Date"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")

        progress["UTC"] = pd.to_numeric(progress["UTC"], errors="coerce")
        progress = progress.dropna(
            subset=["Launch_Date", "UTC", "Station", "Status"]
        )

        # Keep only the newest status for each date/hour/station.
        progress = progress.drop_duplicates(
            subset=["Launch_Date", "UTC", "Station"],
            keep="last",
        )

        no_data = progress[progress["Status"] == "no_data"]

        return set(
            zip(
                no_data["Launch_Date"],
                no_data["UTC"].astype(int),
                no_data["Station"],
            )
        )

    except (EmptyDataError, ValueError, KeyError) as exc:
        logging.warning("Could not read progress file: %s", exc)
        return set()

def save_progress(progress_file: Path,dt: datetime,station_id: str,status: str) -> None:
    """Save the latest result of an attempted launch."""
    write_header = (not progress_file.exists() or progress_file.stat().st_size == 0)

    pd.DataFrame(
        [{
            "Launch_Date": dt.strftime("%Y-%m-%d"),
            "UTC": dt.hour,
            "Station": station_id,
            "Status": status,
        }]
    ).to_csv(
        progress_file,
        mode="a",
        header=write_header,
        index=False,
    )

def fetch_sounding_csv(session: requests.Session,dt: datetime,station_id: str,) -> tuple[str, str | None]:
    """
    Returns:
        ("data", text)      -> usable response received
        ("no_data", None)   -> server confirmed no data exists
        ("failed", None)    -> network/server issue; retry next run
    """
    params = {
        "datetime": dt.strftime("%Y-%m-%d %H:00:00"),
        "id": station_id,
        "src": "UNKNOWN",
        "type": "TEXT:CSV",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(BASE_URL,params=params,timeout=REQUEST_TIMEOUT_SECONDS)

            if response.status_code == 200:
                text = response.text.strip()

                if "Can't find" in text:
                    return "no_data", None

                if "Description:" not in text and len(text) > 10:
                    return "data", text

                logging.warning(
                    "Unexpected empty/error response for Station %s at %s, "
                    "attempt %s/%s",
                    station_id,
                    dt,
                    attempt,
                    MAX_RETRIES,
                )

            elif response.status_code in (400,404) :
                return "no_data", None

            else:
                logging.warning(
                    "HTTP %s for Station %s at %s, attempt %s/%s",
                    response.status_code,
                    station_id,
                    dt,
                    attempt,
                    MAX_RETRIES,
                )

        except requests.RequestException as exc:
            logging.warning(
                "Network error for Station %s at %s, attempt %s/%s: %s",
                station_id,
                dt,
                attempt,
                MAX_RETRIES,
                exc,
            )

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SECONDS)

    return "failed", None

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame | None:
    """Remove only rows that contain missing or blank values."""
    if df.empty:
        return None

    df = df.replace(r"^\s*$", pd.NA, regex=True)

    original_count = len(df)
    cleaned_df = df.dropna()
    removed_count = original_count - len(cleaned_df)

    if removed_count:
        logging.info(
            "Removed %d incomplete rows; %d rows remaining.",
            removed_count,
            len(cleaned_df),
        )

    return cleaned_df if not cleaned_df.empty else None

def parse_sounding(text: str, dt: datetime, station_id: str) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(StringIO(text))

        if df.empty:
            return None

        df = df.assign(
            Launch_Date=dt.strftime("%Y-%m-%d"),
            UTC=dt.hour,
            Station=station_id,
        )

        return clean_dataframe(df)

    except Exception as exc:
        logging.warning(
            "Failed parsing data for Station %s at %s: %s",
            station_id,
            dt,
            exc,
        )
        return None

def daterange(start: datetime, end: datetime) -> Iterator[datetime]:
    current = start

    while current <= end:
        yield current
        current += timedelta(days=1)

def _run_download() -> None:
    session = create_session()

    completed_launches = get_completed_launches(OUTPUT_FILE)
    no_data_launches = get_no_data_launches(PROGRESS_FILE)

    logging.info("CSV destination: %s", OUTPUT_FILE.resolve())

    for station_id in STATIONS:
        logging.info("--- Starting Station: %s ---", station_id)
        logging.info(
            "Processing from %s to %s",
            START_DATE.date(),
            END_DATE.date(),
        )

        for day in daterange(START_DATE, END_DATE):
            for hour in HOURS:
                dt = day.replace(hour=hour)
                launch_key = (dt.strftime("%Y-%m-%d"), hour, station_id)

                if launch_key in completed_launches:
                    logging.info("Already saved; skipping %s", dt)
                    continue

                if launch_key in no_data_launches:
                    logging.info("Previously confirmed no data; skipping %s",dt)
                    continue

                logging.info("Station %s -> Requesting dataset for %s",station_id,dt)

                fetch_status, text = fetch_sounding_csv(session,dt,station_id)

                if fetch_status == "no_data":
                    save_progress(PROGRESS_FILE,dt,station_id,"no_data")
                    no_data_launches.add(launch_key)

                    logging.info("No data exists for Station %s at %s",station_id,dt)
                    continue

                if fetch_status == "failed":
                    save_progress(PROGRESS_FILE,dt,station_id,"failed")

                    logging.warning("Request failed for Station %s at %s; it will retry next run.",station_id,dt)
                    continue

                df = parse_sounding(text, dt, station_id)

                if df is None:
                    save_progress(PROGRESS_FILE,dt,station_id,"failed")

                    logging.warning("No usable rows for Station %s at %s; it will retry next run.",station_id,dt)
                    continue

                write_header = (
                    not OUTPUT_FILE.exists()
                    or OUTPUT_FILE.stat().st_size == 0
                )

                df.to_csv(
                    OUTPUT_FILE,
                    mode="a",
                    header=write_header,
                    index=False,
                )

                completed_launches.add(launch_key)

                save_progress(
                    PROGRESS_FILE,
                    dt,
                    station_id,
                    "saved",
                )

                logging.info("Saved %d records", len(df))
                time.sleep(REQUEST_DELAY_SECONDS)

    target_launches = {
        (day.strftime("%Y-%m-%d"), hour, station_id)
        for station_id in STATIONS
        for day in daterange(START_DATE, END_DATE)
        for hour in HOURS
    }

    handled_launches = completed_launches | no_data_launches
    remaining_launches = target_launches - handled_launches

    if not remaining_launches and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        logging.info("All launches handled; progress file deleted.")
    else:
        logging.warning(
            "%d launches remain unfinished and will retry next run.",
            len(remaining_launches),
        )

    logging.info("Finished. CSV stored at: %s", OUTPUT_FILE.resolve())

def download(
    station: str,
    start: datetime,
    end: datetime,
    output: str | Path,
    hours: Iterable[int] = (0, 12),
    overwrite: bool = False,
):
    """
    Download University of Wyoming upper-air sounding data.

    Parameters
    ----------
    station : str
        WMO station number (for example, "42971").

    start : datetime
        First launch date to download.

    end : datetime
        Last launch date to download.

    output : str | Path
        Path to the output CSV file.

    hours : Iterable[int], optional
        UTC launch hours to download.
        Example:
            [0]
            [12]
            [0, 12]
            range(0, 24, 3)

    overwrite : bool, optional
        If True, deletes any existing output and progress files
        before downloading.

    Returns
    -------
    None
    """

    global STATIONS
    global START_DATE
    global END_DATE
    global OUTPUT_FILE
    global PROGRESS_FILE
    global HOURS

    STATIONS = [station]
    START_DATE = start
    END_DATE = end
    HOURS = list(hours)

    OUTPUT_FILE = Path(output)
    PROGRESS_FILE = OUTPUT_FILE.with_name(
        f"{OUTPUT_FILE.stem}_progress.csv"
    )

    if overwrite:
        if OUTPUT_FILE.exists():
            OUTPUT_FILE.unlink()

        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()

    _run_download()
