"""Manipur land-use dashboard (Streamlit).

Run locally:   streamlit run app.py
Real data:     put the files from dashboard_data.zip into the folder  data/
No data found: the app starts in DEMO mode with made-up numbers.
"""
import copy
import json
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from branca.colormap import LinearColormap
from streamlit_folium import st_folium

import demo_data

DATA_DIR = Path(__file__).parent / "data"

CLASS_LABELS = {
    "ag_total": "Agricultural land (rice + other cropland)",
    "forest": "Forest",
    "rice_paddy": "Rice paddy",
    "other_cropland_or_jhum": "Other cropland / jhum",
    "built_up": "Built-up",
    "water": "Open water",
    "other": "Other",
    "phumdi_wetland": "Phumdi (floating vegetation)",
}
CLASS_COLORS = {
    "ag_total": "#6d4c41",
    "forest": "#1b5e20",
    "rice_paddy": "#ffd54f",
    "other_cropland_or_jhum": "#ff8f00",
    "built_up": "#d32f2f",
    "water": "#1565c0",
    "other": "#9e9e9e",
    "phumdi_wetland": "#00897b",
}
AG_CLASSES = ["rice_paddy", "other_cropland_or_jhum"]
ALL_NAME = "All Manipur"
DEFAULT_BOUNDS = [[23.8, 93.0], [25.7, 94.8]]   # [[south, west], [north, east]]
RESOLUTION = {"Landsat": "30 m", "Sentinel2": "10 m"}

st.set_page_config(page_title="Manipur Land Use & Forest Dashboard",
                   page_icon="🛰️", layout="wide")

# ------------------------------------------------ formatting helpers ----
def format_area(ha: float) -> str:
    """Format hectares into a string with both ha and km²."""
    km2 = ha * 0.01
    return f"{ha:,.0f} ha ({km2:,.2f} km²)"

def format_delta_area(delta_ha: float) -> str:
    """Format delta hectares into a string with both ha and km²."""
    delta_km2 = delta_ha * 0.01
    return f"{delta_ha:+,.0f} ha ({delta_km2:+,.2f} km²)"

# ---------------------------------------------------------------- data ----
@st.cache_data
def load_data():
    area_path = DATA_DIR / "area_by_district.csv"
    geo_path = DATA_DIR / "districts.geojson"
    forest_path = DATA_DIR / "forest_loss_by_district.csv"
    bounds_path = DATA_DIR / "bounds.json"

    if area_path.exists() and geo_path.exists():
        area = pd.read_csv(area_path)
        geo = json.loads(geo_path.read_text(encoding="utf-8"))
        forest = pd.read_csv(forest_path) if forest_path.exists() else None
        bounds = (json.loads(bounds_path.read_text())
                  if bounds_path.exists() else DEFAULT_BOUNDS)
        return area, geo, forest, bounds, False

    area, geo, forest = demo_data.make_demo()
    return area, geo, forest, DEFAULT_BOUNDS, True


def iter_coords(coords):
    """Yield every [lon, lat] pair inside a GeoJSON coordinates structure."""
    if coords and isinstance(coords[0], (int, float)):
        yield coords
    else:
        for c in coords:
            yield from iter_coords(c)


def district_bounds(geo, name):
    pts = []
    for f in geo["features"]:
        if f["properties"]["district"] == name:
            pts.extend(iter_coords(f["geometry"]["coordinates"]))
    if not pts:
        return None
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def district_slice(df, district):
    """Rows for one district, or the sum over all districts."""
    if district == ALL_NAME:
        return df.groupby(["year", "sensor", "class_name"],
                          as_index=False)["hectares"].sum()
    return df[df["district"] == district][["year", "sensor", "class_name", "hectares"]]


area, geo, forest, bounds, demo = load_data()

# ------------------------------------------------------------- sidebar ----
years = sorted(int(y) for y in area["year"].unique())
sensor_by_year = {int(r.year): r.sensor for r in area.drop_duplicates("year").itertuples()}
districts = [ALL_NAME] + sorted(area["district"].unique())
classes_present = [c for c in CLASS_LABELS
                   if c != "ag_total" and c in set(area["class_name"])]

with st.sidebar:
    st.header("🎨 Theme")
    theme = st.radio("Choose Theme", ["Dark", "Light"], index=0, horizontal=True)

    st.header("🔍 Filters")
    district = st.selectbox("📍 District", districts)
    year = st.select_slider("📅 Year", options=years, value=years[-1])
    sensor = sensor_by_year[year]
    st.caption(f"📡 {year}: {sensor} satellite data, {RESOLUTION.get(sensor, '')} pixels")

    st.subheader("🗺️ Map Layer Settings")
    default_idx = (classes_present.index("rice_paddy")
                   if "rice_paddy" in classes_present else 0)
    map_class = st.selectbox("Colour districts by share of", classes_present,
                             index=default_idx,
                             format_func=lambda c: CLASS_LABELS[c])
    show_overlay = st.checkbox("Show classified map layer", value=True)
    opacity = st.slider("Layer opacity", 0.2, 1.0, 0.75, 0.05)

    st.subheader("📈 Trend Chart Settings")
    trend_options = ["ag_total"] + classes_present
    trend_default = ["ag_total"] + [c for c in AG_CLASSES if c in classes_present]
    trend_classes = st.multiselect("Classes to show", trend_options,
                                   default=trend_default,
                                   format_func=lambda c: CLASS_LABELS[c])

# ------------------------------------------------ styling & theme ----
is_dark = theme == "Dark"
bg_color = "#0e1117" if is_dark else "#ffffff"
text_color = "#fafafa" if is_dark else "#1a1a1a"
card_bg = "#161b22" if is_dark else "#f4f6f8"
border_color = "#30363d" if is_dark else "#e0e0e0"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"], .stApp {{
        font-family: 'Inter', sans-serif;
        background-color: {bg_color};
        color: {text_color};
    }}

    /* Sticky Header Styling */
    .sticky-header-container {{
        position: sticky;
        top: 2.8rem;
        z-index: 999;
        background-color: {bg_color};
        backdrop-filter: blur(8px);
        padding: 12px 0 16px 0;
        border-bottom: 1px solid {border_color};
        margin-bottom: 20px;
    }}
    .sticky-header-title {{
        font-size: 1.85rem;
        font-weight: 700;
        margin: 0;
        color: {text_color};
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .sticky-header-subtitle {{
        font-size: 0.95rem;
        margin: 4px 0 0 0;
        opacity: 0.8;
        color: {text_color};
    }}
</style>
""", unsafe_allow_html=True)

# Static/Sticky Title Header Container
st.markdown(f"""
<div class="sticky-header-container">
    <div class="sticky-header-title">🛰️ Manipur Land-use and Forest Dashboard</div>
    <div class="sticky-header-subtitle">See how Manipur's farmland and forests are changing, district by district.</div>
</div>
""", unsafe_allow_html=True)

with st.expander("❓ New here? How to use this dashboard"):
    st.markdown("""
**What is this?** A free, open dashboard that uses satellite images (Landsat and Sentinel) to estimate how land is used in Manipur: rice paddy, other cropland and jhum, forest, built-up areas, water and phumdi.

**How to use it:**
- Pick a district in the left sidebar, or leave it on **“All Manipur”**.
- Move the year slider to see the map and charts change.
- Choose a land type to color the districts by, and switch the map layer on or off.
- Open the **“Forest loss”** tab for yearly tree-cover loss.

*Please note: these are computer estimates from satellite images, not official statistics. Accuracy is lower for jhum versus forest and for phumdi versus water, and older years are less certain than recent ones.*
""")

if demo:
    st.warning("⚠️ **DEMO DATA:** The numbers and district shapes below are made up "
               "for testing. Put your real files in the `data/` folder.")

tab_land, tab_forest = st.tabs(["🌱 Land use", "🌲 Forest loss"])

# ------------------------------------------------------- land-use tab -----
with tab_land:
    base = district_slice(area, district)
    ag = (base[base["class_name"].isin(AG_CLASSES)]
          .groupby(["year", "sensor"], as_index=False)["hectares"].sum())
    ag["class_name"] = "ag_total"
    trend_all = pd.concat([base, ag], ignore_index=True)

    # headline numbers (compared only within the same satellite sensor)
    def ag_ha(y):
        return float(ag.loc[ag["year"] == y, "hectares"].sum())

    same_sensor_years = [y for y in years if sensor_by_year[y] == sensor]
    base_year = min(same_sensor_years)
    cur_forest = float(base[(base["year"] == year) &
                            (base["class_name"] == "forest")]["hectares"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric(f"🌾 Agricultural land, {year}", format_area(ag_ha(year)))
    if year != base_year and ag_ha(base_year) > 0:
        delta = ag_ha(year) - ag_ha(base_year)
        pct_change = delta / ag_ha(base_year) * 100
        c2.metric(f"📉 Change since {base_year} ({sensor})", 
                  format_delta_area(delta),
                  f"{pct_change:+.1f}%")
    else:
        c2.metric("📉 Change", "n/a", "earliest year for this sensor",
                  delta_color="off")
    c3.metric(f"🌲 Forest, {year}", format_area(cur_forest))

    # ------------------------------------------------------------- map ----
    yr = area[area["year"] == year]
    totals = yr.groupby("district")["hectares"].sum()
    cls_ha = (yr[yr["class_name"] == map_class]
              .groupby("district")["hectares"].sum())
    pct = (cls_ha.reindex(totals.index).fillna(0) / totals * 100)

    vmin, vmax = float(pct.min()), float(pct.max())
    if vmax - vmin < 0.01:
        vmax = vmin + 1
    cmap = LinearColormap(
        ["#f7f7f7", CLASS_COLORS[map_class]], vmin=vmin, vmax=vmax,
        caption=f"{CLASS_LABELS[map_class]}, % of district area ({year})")

    overlay_path = DATA_DIR / "overlays" / f"classes_{year}.png"
    has_overlay = show_overlay and overlay_path.exists()

    geo_year = copy.deepcopy(geo)
    for f in geo_year["features"]:
        n = f["properties"]["district"]
        f["properties"]["share"] = f"{pct[n]:.1f}%" if n in pct.index else "n/a"

    def style(feature):
        name = feature["properties"]["district"]
        selected = district != ALL_NAME and name == district
        value = pct.get(name)
        return {
            "fillColor": cmap(value) if value is not None else "#cccccc",
            "color": "#000000" if selected else "#555555",
            "weight": 3 if selected else 1,
            "fillOpacity": 0.15 if has_overlay else 0.65,
        }

    m = folium.Map(location=[24.8, 93.9], zoom_start=8, tiles=None,
                   control_scale=True)
    
    tile_theme = "cartodbdarkmatter" if is_dark else "cartodbpositron"
    folium.TileLayer(tile_theme, name="Base map").add_to(m)
    folium.TileLayer(
        tiles=("https://server.arcgisonline.com/ArcGIS/rest/services/"
               "World_Imagery/MapServer/tile/{z}/{y}/{x}"),
        attr="Esri, Maxar, Earthstar Geographics", name="Satellite",
    ).add_to(m)

    if has_overlay:
        folium.raster_layers.ImageOverlay(
            image=str(overlay_path), bounds=bounds, opacity=opacity,
            name=f"Classified map {year}", interactive=False, zindex=2,
        ).add_to(m)

    folium.GeoJson(
        geo_year, name="Districts", style_function=style,
        tooltip=folium.GeoJsonTooltip(
            fields=["district", "share"],
            aliases=["District", f"{CLASS_LABELS[map_class]} share"]),
    ).add_to(m)
    cmap.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    fit = (district_bounds(geo, district) if district != ALL_NAME else None) or bounds
    m.fit_bounds(fit)

    if show_overlay and not has_overlay:
        st.info(f"ℹ️ No classified map layer for {year} yet (district shading only).")

    # returned_objects=[] stops the app re-running every time you pan the map
    st_folium(m, height=560, use_container_width=True, returned_objects=[])

    legend = " ".join(
        f"<span style='display:inline-block;width:12px;height:12px;"
        f"background:{CLASS_COLORS[c]};border:1px solid #888;margin-right:4px'>"
        f"</span>{CLASS_LABELS[c]}&nbsp;&nbsp;" for c in classes_present)
    st.markdown(legend, unsafe_allow_html=True)

    # ----------------------------------------------------------- charts ---
    color_map = {CLASS_LABELS[c]: CLASS_COLORS[c] for c in CLASS_LABELS}
    plotly_template = "plotly_dark" if is_dark else "plotly_white"
    left, right = st.columns(2)

    with left:
        if trend_classes:
            t = trend_all[trend_all["class_name"].isin(trend_classes)].copy()
            t["Class"] = t["class_name"].map(CLASS_LABELS)
            t["sq_km"] = t["hectares"] * 0.01
            
            fig = px.line(
                t.sort_values("year"), x="year", y="hectares", color="Class",
                symbol="sensor", markers=True, color_discrete_map=color_map,
                hover_data={"sq_km": ":,.2f", "hectares": ":,.0f"},
                labels={"hectares": "Hectares (ha)", "sq_km": "Square Km (km²)", "year": "Year",
                        "sensor": "Satellite"},
                template=plotly_template,
                title=f"📈 Land-use trend: {district}")
            fig.add_vline(x=year, line_dash="dot", line_color="gray")
            fig.update_layout(legend_title_text="", margin=dict(t=50, b=10))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("ℹ️ Lines break where the satellite changes (Landsat 30 m "
                       "to Sentinel-2 10 m), because the two are not directly "
                       "comparable.")
        else:
            st.info("💡 Pick at least one class in the sidebar.")

    with right:
        mix = yr.copy()
        mix["Class"] = mix["class_name"].map(CLASS_LABELS)
        mix["sq_km"] = mix["hectares"] * 0.01
        
        fig2 = px.bar(
            mix, x="district", y="hectares", color="Class",
            color_discrete_map=color_map,
            hover_data={"sq_km": ":,.2f", "hectares": ":,.0f"},
            labels={"hectares": "Area Share (%)", "district": "", "sq_km": "Square Km (km²)"},
            template=plotly_template,
            title=f"📊 Land-use mix by district, {year}")
        fig2.update_layout(barmode="stack", barnorm="percent", legend_title_text="", margin=dict(t=50, b=10))
        st.plotly_chart(fig2, use_container_width=True)

    with st.expander("🔬 Methods and limitations"):
        st.markdown(
            "- **Data:** Sentinel-2 and Landsat optical imagery (cloud-masked "
            "seasonal composites), Sentinel-1 radar, SRTM elevation, via "
            "Google Earth Engine.\n"
            "- **Method:** Random Forest classifier trained on hand-labelled "
            "points. Overall accuracy on held-out test points for 2023 was "
            "about 77% (update this when you retrain). The weakest classes "
            "are phumdi versus water, and forest versus jhum.\n"
            "- **Decades:** older years come from Landsat (30 m) and are less "
            "certain than recent Sentinel-2 years. Do not read a jump at the "
            "sensor change as real land change.\n"
            "- **District boundaries:** FAO GAUL. Areas are approximate.")

# ------------------------------------------------------- forest tab -------
with tab_forest:
    if forest is None:
        st.info("ℹ️ No forest-loss file found. Add `data/forest_loss_by_district.csv` "
                "(columns: district, year, loss_ha).")
    else:
        f = forest if district == ALL_NAME else forest[forest["district"] == district]
        f = (f.groupby("year", as_index=False)["loss_ha"].sum()
             .sort_values("year"))
        f["cumulative_ha"] = f["loss_ha"].cumsum()
        f["loss_sq_km"] = f["loss_ha"] * 0.01
        f["cumulative_sq_km"] = f["cumulative_ha"] * 0.01

        plotly_template = "plotly_dark" if is_dark else "plotly_white"
        a, b = st.columns(2)
        with a:
            st.plotly_chart(px.bar(
                f, x="year", y="loss_ha",
                hover_data={"loss_sq_km": ":,.2f", "loss_ha": ":,.0f"},
                labels={"loss_ha": "Hectares (ha)", "loss_sq_km": "Square Km (km²)", "year": "Year"},
                template=plotly_template,
                title=f"🪵 Forest loss per year: {district}"), use_container_width=True)
        with b:
            st.plotly_chart(px.line(
                f, x="year", y="cumulative_ha", markers=True,
                hover_data={"cumulative_sq_km": ":,.2f", "cumulative_ha": ":,.0f"},
                labels={"cumulative_ha": "Hectares (ha)", "cumulative_sq_km": "Square Km (km²)", "year": "Year"},
                template=plotly_template,
                title=f"📈 Cumulative forest loss: {district}"), use_container_width=True)
        st.caption("ℹ️ **Source:** Hansen / UMD Global Forest Change. Loss includes "
                   "shifting-cultivation (jhum) clearing and fires where trees "
                   "can regrow, so it is not the same as permanent "
                   "deforestation.")

st.divider()
st.caption("🌍 Data: Copernicus Sentinel-1/2, USGS/NASA Landsat, SRTM, ESA "
           "WorldCover, FAO GAUL, Hansen/UMD, processed with Google Earth Engine.")
