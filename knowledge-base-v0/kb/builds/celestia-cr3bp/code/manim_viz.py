"""Stub replacing the Manim cinematic pipeline.

manimpango (a manim dependency) requires system cairo/pango headers that are
not available in this environment, so it cannot be built. The core
simulation and Plotly visualisations do not depend on this module; only the
optional "Export Cinematic Video" dialog in app.py calls render_trajectory,
and it already catches exceptions and shows an error message to the user.
"""


def render_trajectory(mu, trajectory, output_file, body1_name, body2_name, m1_mass, m2_mass):
    raise RuntimeError(
        "Cinematic MP4 export is unavailable in this environment "
        "(Manim/cairo are not installed)."
    )


def cleanup_render(video_path):
    return None
