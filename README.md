# Wyoming Upper-Air

A Python package for downloading upper-air sounding (weather balloon) data from the University of Wyoming archive.

## Features

- Download data using a WMO station number.
- Download any date range.
- Select one or more UTC launch hours.
- Automatically resumes interrupted downloads.
- Skips launches that have already been downloaded.
- Saves data directly to CSV.

## Installation

### From source

```bash
git clone https://github.com/ProHackerz669/wyoming-upperair.git
cd wyoming-upperair
pip install -e .
```

### From PyPI

```bash
pip install wyoming-upperair
```

## Example

```python
from datetime import datetime
from wyoming import dowload

download(
    station="72672",
    start=datetime(2023, 1, 1),
    end=datetime(2023, 1, 31),
    output="data.csv",
    hours=[0]
)
```

Download any UTC:

```python
wyoming.download(
    station="42971",
    start=datetime(2023, 1, 1),
    end=datetime(2023, 1, 31),
    output="data.csv",
    hours=[0,3,6,...,21],
)
```

Start a fresh download:

```python
wyoming.download(
    station="42971",
    start=datetime(2023, 1, 1),
    end=datetime(2023, 1, 31),
    output="data.csv",
    overwrite=True,
)
```

## Requirements

- Python 3.10+
- pandas
- requests

## License

MIT License.