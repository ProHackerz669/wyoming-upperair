from datetime import datetime
import pandas as pd
from wyoming import download


def test_download_writes_csv(monkeypatch, tmp_path):
    csv_text = """PRES,HGHT,TEMP
1000,100,20.5
900,1000,15.0
"""

    class FakeResponse:
        status_code = 200
        text = csv_text

    def fake_get(self, url, params, timeout):
        assert params["id"] == "72672"
        assert params["datetime"] == "2023-01-01 12:00:00"
        return FakeResponse()

    monkeypatch.setattr(
        "wyoming.downloader.requests.Session.get",
        fake_get,
    )
    monkeypatch.setattr(
        "wyoming.downloader.time.sleep",
        lambda seconds: None,
    )

    output_file = tmp_path / "sounding.csv"

    download(
        station="72672",
        start=datetime(2023, 1, 1),
        end=datetime(2023, 1, 1),
        output=output_file,
        hours=[12],
    )

    result = pd.read_csv(output_file)

    assert len(result) == 2
    assert result["Station"].astype(str).tolist() == ["72672", "72672"]
    assert result["UTC"].tolist() == [12, 12]