"""Headless launcher for the Bokeh dashboard, bypassing the PyQt5 setup wizard.

Serves the bundled example dataset directly so a browser agent can reach the
dashboard without a display server for PyQt5.
"""
from bokeh.server.server import Server

from active_units.dashboard import make_app

PORT = 8501


def bkapp(doc):
    layout = make_app(
        activity_csv="example/activity/activity_summary.csv",
        trials_csv="example/trials.csv",
        sorted_spikes_dir="example/sorted_spikes",
        config="example/config.json",
    )
    doc.add_root(layout)
    doc.title = "Unit Activity Filter"


if __name__ == "__main__":
    server = Server(
        {"/": bkapp},
        port=PORT,
        address="127.0.0.1",
        allow_websocket_origin=[f"127.0.0.1:{PORT}", f"localhost:{PORT}"],
    )
    server.start()
    server.io_loop.start()
