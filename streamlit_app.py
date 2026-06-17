"""Health Hotspot Tracker — Chicago influenza surveillance dashboard.

UI layer only: all data loading/shaping lives in ``src/data_processing.py``.
"""

import os
import tempfile

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from src import data_processing as dp

st.set_page_config(page_title="Health Hotspot Tracker", page_icon="🦠", layout="wide")

# Small bit of polish on top of the theme in .streamlit/config.toml.
st.markdown(
    """
    <style>
      .metric-box { border-radius: 12px; padding: 16px; color: white; text-align: center;
                    min-height: 104px; display: flex; flex-direction: column;
                    justify-content: center; margin-bottom: 6px; }
      .metric-value { font-size: 34px; font-weight: 700; line-height: 1.1; }
      .metric-label { font-size: 14px; opacity: 0.9; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="Loading surveillance data…")
def get_data():
    return dp.load_dashboard_data()


@st.cache_data(show_spinner="Processing your timeline…")
def process_uploaded_timeline(file_bytes, pop_dict, weekly_cases):
    """Parse an uploaded Google Timeline export into exposure estimates."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        records = dp.process_timeline_file(tmp_path)
    finally:
        os.unlink(tmp_path)
    return dp.build_exposure_estimates(records, pop_dict, weekly_cases)


def metric_box(value, label, color):
    st.markdown(
        f'<div class="metric-box" style="background-color:{color};">'
        f'<div class="metric-value">{value}</div>'
        f'<div class="metric-label">{label}</div></div>',
        unsafe_allow_html=True,
    )


def week_probability(estimates, week):
    """Mean exposure probability across the days of ``week`` (or None)."""
    probs = []
    for date_str in estimates:
        if pd.Timestamp(date_str).isocalendar().week == week:
            p = dp.exposure_probability(estimates, date_str)
            if p is not None:
                probs.append(p)
    return float(np.mean(probs)) if probs else None


data = get_data()
surveillance, risk, age = data["surveillance"], data["risk"], data["age"]
pop, geojson, estimates = data["population"], data["geojson"], data["estimates"]
weekly_cases = surveillance.set_index("week")["LAB_FLU_TESTED"].to_dict()

# Weeks that actually have map data, newest first.
available_weeks = sorted(risk["MMWR_Week"].unique())
week_dates = risk.groupby("MMWR_Week")["Week_Start"].first().dt.strftime("%b %d, %Y").to_dict()

# --- Sidebar controls -------------------------------------------------------
st.sidebar.title("🦠 Hotspot Tracker")
st.sidebar.caption("Chicago influenza-like illness (ILI) surveillance, 2024 season.")

disease = st.sidebar.selectbox(
    "Disease", ["Influenza (ILI)"],
    help="Only Chicago flu surveillance is wired up today; the data layer is "
         "structured to add more diseases.",
)
city = st.sidebar.selectbox("City", ["Chicago"], help="More metros planned.")

selected_week = st.sidebar.select_slider(
    "Week (MMWR)",
    options=available_weeks,
    value=available_weeks[-1],
    format_func=lambda w: f"Wk {w} · {week_dates.get(w, '')}",
)

st.sidebar.divider()
st.sidebar.subheader("Personal exposure")
uploaded = st.sidebar.file_uploader(
    "Upload your Google Timeline JSON", type=["json"],
    help="Computes a contact-weighted exposure probability from your own "
         "location history. Nothing is uploaded anywhere — it's processed locally.",
)
if uploaded is not None:
    try:
        estimates = process_uploaded_timeline(uploaded.getvalue(), pop, weekly_cases)
        st.sidebar.success(f"Processed timeline · {len(estimates)} days")
    except Exception as e:  # noqa: BLE001 - surface any parse error to the user
        st.sidebar.error(f"Couldn't process that file: {e}")
else:
    st.sidebar.caption("Showing a synthetic sample timeline by default.")

# --- Header -----------------------------------------------------------------
st.title("Health Hotspot Tracker")
st.caption(f"{disease} · {city} · MMWR week {selected_week} ({week_dates.get(selected_week, '')})")

week_risk = risk[risk["MMWR_Week"] == selected_week]

# Default selected ZIP = the hardest-hit ZIP this week (was hardcoded to 60616).
if "selected_zip" not in st.session_state and not week_risk.empty:
    st.session_state.selected_zip = int(week_risk.loc[week_risk["ILI"].idxmax(), "ZIP_Code"])

map_col, stats_col = st.columns([3, 2], gap="large")

with map_col:
    fig = px.choropleth_mapbox(
        week_risk, geojson=geojson, locations="ZIP_Code",
        featureidkey="properties.postal-code", color="ILI",
        color_continuous_scale="YlOrRd", range_color=(1, 10),
        mapbox_style="carto-positron", zoom=9.4,
        center={"lat": 41.84, "lon": -87.68}, opacity=0.6,
        labels={"ILI": "ILI level"},
    )
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=560)
    event = st.plotly_chart(
        fig, use_container_width=True, on_select="rerun", selection_mode="points",
    )
    # Map clicks update the selected ZIP.
    pts = (event.get("selection", {}) or {}).get("points", []) if event else []
    if pts:
        loc = pts[0].get("location")
        if loc is not None:
            st.session_state.selected_zip = int(loc)
    st.caption("Darker = higher ILI activity. **Click a ZIP** to inspect it.")

selected_zip = st.session_state.get("selected_zip")

with stats_col:
    zip_row = week_risk[week_risk["ZIP_Code"] == selected_zip]
    ili = f"{zip_row['ILI'].iloc[0]:.1f}" if not zip_row.empty else "—"

    wk = surveillance[surveillance["week"] == selected_week]
    prev = surveillance[surveillance["week"] == selected_week - 1]
    cases = int(wk["LAB_FLU_TESTED"].iloc[0]) if not wk.empty else None
    prev_cases = int(prev["LAB_FLU_TESTED"].iloc[0]) if not prev.empty else None
    if cases is not None and prev_cases:
        pct = (cases - prev_cases) / prev_cases * 100
        pct_display = f"{pct:+.1f}%"
    else:
        pct_display = "—"
    cases_display = f"{cases:,}" if cases is not None else "—"

    pct_pos = wk["LAB_FLU_PCT_POSITIVE"].iloc[0] if not wk.empty else None
    pos_display = f"{pct_pos:.1f}%" if pct_pos is not None and not pd.isna(pct_pos) else "—"

    age_week = age[age["mmwr-week"] == selected_week]
    age_display = (
        age_week.loc[age_week["weekly rate"].idxmax(), "age category"]
        if not age_week.empty else "—"
    )

    prob = week_probability(estimates, selected_week)
    prob_display = f"{prob:.1f}%" if prob is not None else "No data"

    st.markdown(f"#### ZIP {selected_zip}" if selected_zip else "#### Citywide")
    r1c1, r1c2 = st.columns(2)
    r2c1, r2c2 = st.columns(2)
    r3c1, r3c2 = st.columns(2)
    with r1c1: metric_box(ili, "ILI level (selected ZIP)", "#2E8B57")
    with r1c2: metric_box(pct_display, "Cases vs last week", "#5F9EA0")
    with r2c1: metric_box(cases_display, "Lab-tested cases", "#4682B4")
    with r2c2: metric_box(age_display, "Most-affected age", "#8A2BE2")
    with r3c1: metric_box(prob_display, "Exposure probability", "#20B2AA")
    with r3c2: metric_box(pos_display, "Tests positive", "#6495ED")

st.divider()

# --- Trends & breakdowns ----------------------------------------------------
left, right = st.columns(2, gap="large")

with left:
    st.subheader("ILI trend — selected ZIP")
    zip_series = risk[risk["ZIP_Code"] == selected_zip].sort_values("Week_Start")
    if not zip_series.empty:
        line = px.line(zip_series, x="Week_Start", y="ILI", markers=True)
        sel = zip_series[zip_series["MMWR_Week"] == selected_week]
        if not sel.empty:
            line.add_vline(x=sel["Week_Start"].iloc[0], line_dash="dash", line_color="gray")
        line.update_layout(height=300, margin={"t": 10, "b": 0}, yaxis_title="ILI level")
        st.plotly_chart(line, use_container_width=True)
    else:
        st.info("No ILI series for this ZIP.")

    st.subheader("Citywide lab-tested cases")
    cases_fig = px.area(surveillance.sort_values("week"), x="WEEK_START", y="LAB_FLU_TESTED")
    cases_fig.update_layout(height=240, margin={"t": 10, "b": 0}, yaxis_title="cases")
    st.plotly_chart(cases_fig, use_container_width=True)

with right:
    st.subheader(f"Infection rate by age — week {selected_week}")
    if not age_week.empty:
        bar = px.bar(
            age_week.sort_values("weekly rate", ascending=True),
            x="weekly rate", y="age category", orientation="h",
            color="weekly rate", color_continuous_scale="OrRd",
        )
        bar.update_layout(height=300, margin={"t": 10, "b": 0}, coloraxis_showscale=False)
        st.plotly_chart(bar, use_container_width=True)
    else:
        st.info("No age breakdown for this week.")

    st.subheader(f"Influenza subtypes — week {selected_week}")
    if not wk.empty:
        subtypes = {
            "H1N1": wk["LAB_TOT_H1N1_POSITIVE"].iloc[0],
            "H3N2": wk["LAB_TOT_H3N2_POSITIVE"].iloc[0],
            "Influenza B": wk["LAB_TOT_B_POSITIVE"].iloc[0],
            "A (unsubtyped)": wk["LAB_TOT_NOTSUBTYPED_POSITIVE"].iloc[0],
        }
        sub_df = pd.DataFrame({"subtype": list(subtypes), "positive": list(subtypes.values())})
        sub_fig = px.bar(sub_df, x="subtype", y="positive", color="subtype")
        sub_fig.update_layout(height=240, margin={"t": 10, "b": 0}, showlegend=False)
        st.plotly_chart(sub_fig, use_container_width=True)
    else:
        st.info("No subtype data for this week.")

# --- Export -----------------------------------------------------------------
st.divider()
st.download_button(
    "⬇️ Download this week's ZIP data (CSV)",
    data=week_risk.to_csv(index=False).encode(),
    file_name=f"ili_week_{selected_week}.csv",
    mime="text/csv",
)
with st.expander("About the exposure-probability metric"):
    st.markdown(
        f"""
        For each consecutive pair of events in a timeline we accumulate
        `time × activity_weight × local_case_rate`, where `local_case_rate` is the
        week's lab-tested cases divided by the ZIP population. The summed risk is
        mapped to a probability with `1 − exp(−risk / {dp.EXPOSURE_SCALE:.0f})`.
        Activity weights (transit > stationary > cycling) and the scale constant
        are heuristics, not clinically validated. Gaps longer than
        {dp.MAX_GAP_MINUTES} minutes are ignored. The default view uses a
        **synthetic** sample timeline; upload your own in the sidebar.
        """
    )
