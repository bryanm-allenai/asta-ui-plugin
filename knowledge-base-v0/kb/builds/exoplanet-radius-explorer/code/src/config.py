"""Shared constants for the Exoplanet Radius Explorer."""

AGE_GROUP_ORDER = ["< 100 Myr", "100 Myr - 500 Myr", "500 Myr - 2 Gyr", "> 2 Gyr"]

AGE_GROUP_EDGES_GYR = (0.1, 0.5, 2.0)

DEFAULT_RADIUS_CAP = 20.0

COLUMN_LABELS = {
    "pl_name": "Planet",
    "hostname": "Host star",
    "discoverymethod": "Discovery method",
    "disc_year": "Discovery year",
    "age_group": "Age group",
    "st_age": "Stellar age (Gyr)",
    "st_age_err": "Stellar age uncertainty (Gyr)",
    "pl_rade": "Planet radius (R⊕)",
    "pl_orbper": "Orbital period (d)",
    "pl_bmasse": "Planet mass (M⊕)",
    "pl_insol": "Insolation (S⊕)",
    "pl_eqt": "Equilibrium temperature (K)",
    "sy_dist": "Distance (pc)",
    "radius_provenance": "Radius provenance",
}

CITATION = (
    "Razeghi, A. (2026). Exoplanet Radius Explorer (v0.0.0) [Software]. "
    "Data: NASA Exoplanet Archive, Planetary Systems Composite Parameters table."
)
