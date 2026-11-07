"""Fake data so you can test the dashboard before your real results exist.

EVERYTHING in here is made up: the numbers AND the district shapes (simple
boxes, not real boundaries). Never publish it as results.
"""
import numpy as np
import pandas as pd

DISTRICTS = [
    ("Imphal West", "valley"), ("Imphal East", "valley"),
    ("Bishnupur", "valley"), ("Thoubal", "valley"),
    ("Senapati", "hill"), ("Churachandpur", "hill"),
    ("Chandel", "hill"), ("Ukhrul", "hill"), ("Tamenglong", "hill"),
]
LANDSAT_YEARS = [1990, 1995, 2000, 2005, 2010, 2015]
SENTINEL_YEARS = list(range(2019, 2026))
CLASSES = ["forest", "rice_paddy", "other_cropland_or_jhum",
           "built_up", "water", "phumdi_wetland"]
CLASS_IDS = {"forest": 0, "rice_paddy": 1, "other_cropland_or_jhum": 2,
             "built_up": 3, "water": 4, "phumdi_wetland": 6}

VALLEY_SHARES = {"forest": 0.25, "rice_paddy": 0.38,
                 "other_cropland_or_jhum": 0.12, "built_up": 0.08,
                 "water": 0.12, "phumdi_wetland": 0.05}
HILL_SHARES = {"forest": 0.72, "rice_paddy": 0.04,
               "other_cropland_or_jhum": 0.20, "built_up": 0.01,
               "water": 0.02, "phumdi_wetland": 0.01}


def make_demo(seed=42):
    """Returns (area_by_district DataFrame, districts GeoJSON, forest-loss DataFrame)."""
    rng = np.random.default_rng(seed)

    # 3 x 3 grid of boxes over Manipur's rough extent
    west, east, south, north = 93.0, 94.8, 23.8, 25.7
    features = []
    for i, (name, _) in enumerate(DISTRICTS):
        row, col = divmod(i, 3)
        w = west + (east - west) * col / 3
        e = west + (east - west) * (col + 1) / 3
        s = south + (north - south) * row / 3
        n = south + (north - south) * (row + 1) / 3
        features.append({
            "type": "Feature",
            "properties": {"district": name},
            "geometry": {"type": "Polygon",
                         "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]},
        })
    geo = {"type": "FeatureCollection", "features": features}

    rows = []
    for name, kind in DISTRICTS:
        total = rng.uniform(150_000, 320_000)
        base = VALLEY_SHARES if kind == "valley" else HILL_SHARES
        for sensor, years in (("Landsat", LANDSAT_YEARS),
                              ("Sentinel2", SENTINEL_YEARS)):
            for year in years:
                t = (year - 1990) / 35
                share = dict(base)
                share["rice_paddy"] *= 1 - 0.15 * t
                share["other_cropland_or_jhum"] *= 1 + 0.30 * t
                share["built_up"] *= 1 + 1.5 * t
                share["forest"] *= 1 - 0.10 * t
                vals = np.array([share[c] for c in CLASSES])
                vals = vals * rng.normal(1, 0.03, len(CLASSES))
                vals = vals / vals.sum() * total
                for c, v in zip(CLASSES, vals):
                    rows.append({"year": year, "sensor": sensor,
                                 "district": name, "class_id": CLASS_IDS[c],
                                 "class_name": c, "hectares": round(float(v), 1)})
    area = pd.DataFrame(rows)

    forest_rows = []
    for name, kind in DISTRICTS:
        scale = 150 if kind == "hill" else 15
        for y in range(2001, 2025):
            forest_rows.append({"district": name, "year": y,
                                "loss_ha": round(float(rng.gamma(2.0, scale)), 1)})
    forest = pd.DataFrame(forest_rows)
    return area, geo, forest
