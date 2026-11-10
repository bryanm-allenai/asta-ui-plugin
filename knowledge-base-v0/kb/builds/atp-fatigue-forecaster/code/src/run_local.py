"""
Launcher used only for this sandboxed run: makes the Streamlit app read ATP
match data and Match Charting Project points from local CSV files instead of
raw.githubusercontent.com, since the running server here has no network.
Falls back to the real network fetch for any URL that has no local file, so
behavior is unchanged outside this sandbox.
"""
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import app as appmod  # noqa: E402  (import after sys.path setup)

LOCAL_DIR = pathlib.Path(__file__).parent / "local_data"

_local_url_to_file = {}
for _year in range(2018, 2025):
    _url = appmod.ATP_MATCH_URL_TEMPLATES[0].format(year=_year)
    _local_url_to_file[_url] = LOCAL_DIR / f"atp_matches_{_year}.csv"
_local_url_to_file[appmod.INMATCH_URL] = LOCAL_DIR / "charting-m-points-2020s.csv"

_orig_read_remote_csv = appmod.read_remote_csv


def _patched_read_remote_csv(url, label, timeout=20):
    path = _local_url_to_file.get(url)
    if path is not None and path.exists():
        df = pd.read_csv(path, low_memory=False)
        if df.empty:
            raise RuntimeError(f"{label} local file was empty.")
        return df
    return _orig_read_remote_csv(url, label, timeout=timeout)


appmod.read_remote_csv = _patched_read_remote_csv

if __name__ == "__main__":
    import numpy as np
    np.random.seed(42)
    appmod.main()
