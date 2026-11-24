import time
import requests
import pandas as pd
import plotly.express as px
import streamlit as st

# ---------------- CONFIGURATION ----------------
CHANNEL_ID = "3392651"
# Leave empty "" if your ThingSpeak channel is Public; add Read API Key if Private
READ_API_KEY = "QVF11YPPDXTJYPMD"
SENSOR_HEIGHT_CM = 300.0
ALARM_DISTANCE_THRESHOLD_CM = 105.0
REFRESH_INTERVAL_SEC = 20

st.set_page_config(page_title="Water Level Monitor", page_icon="💧", layout="wide")
st.title("💧 Real-Time ESP32 Water Level Monitor")


@st.cache_data(ttl=15)
def fetch_thingspeak_data(channel_id: str, read_key: str, results: int = 100) -> pd.DataFrame:
    url = f"https://api.thingspeak.com/channels/{channel_id}/feeds.json"
    params = {"results": results}
    if read_key:
        params["api_key"] = read_key

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    feeds = response.json().get("feeds", [])

    if not feeds:
        return pd.DataFrame()

    df = pd.DataFrame(feeds)
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["distance_cm"] = pd.to_numeric(df["field1"], errors="coerce")
    df["water_level_cm"] = pd.to_numeric(df["field2"], errors="coerce")
    return df.dropna(subset=["distance_cm", "water_level_cm"])


# Sidebar controls
with st.sidebar:
    st.header("Settings")
    num_points = st.slider("Data points to display", min_value=20, max_value=500, value=100, step=20)
    auto_refresh = st.checkbox("Auto-refresh every 20s", value=True)
    if st.button("Refresh Now"):
        st.cache_data.clear()
        st.rerun()

try:
    df = fetch_thingspeak_data(CHANNEL_ID, READ_API_KEY, results=num_points)

    if df.empty:
        st.warning("No data available yet on ThingSpeak Channel 3392651.")
    else:
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        current_distance = latest["distance_cm"]
        current_level = latest["water_level_cm"]
        fill_pct = min(max((current_level / SENSOR_HEIGHT_CM) * 100, 0.0), 100.0)

        # Alarm banner matching ESP32 logic (distance_cm <= 270)
        if current_distance <= ALARM_DISTANCE_THRESHOLD_CM:
            st.error(
                f"🚨 **HIGH WATER ALARM!** Sensor distance is **{current_distance:.1f} cm** "
                f"(threshold: ≤ {ALARM_DISTANCE_THRESHOLD_CM:.0f} cm)."
            )
        else:
            st.success(f"✅ Normal Level — Last updated: {latest['created_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}")

        # Top KPI Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric(
            label="Water Level (Field 2)",
            value=f"{current_level:.1f} cm",
            delta=f"{current_level - prev['water_level_cm']:.1f} cm",
        )
        col2.metric(
            label="Distance from Sensor (Field 1)",
            value=f"{current_distance:.1f} cm",
            delta=f"{current_distance - prev['distance_cm']:.1f} cm",
            delta_color="inverse",
        )
        col3.metric(
            label="Tank Capacity Used",
            value=f"{fill_pct:.1f}%",
        )

        st.progress(fill_pct / 100.0)

        # Time-series charts
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            fig_level = px.line(
                df,
                x="created_at",
                y="water_level_cm",
                title="Water Level Over Time (cm)",
                labels={"created_at": "Timestamp", "water_level_cm": "Water Level (cm)"},
                markers=True,
            )
            st.plotly_chart(fig_level, use_container_width=True)

        with chart_col2:
            fig_dist = px.line(
                df,
                x="created_at",
                y="distance_cm",
                title="Sensor Distance Over Time (cm)",
                labels={"created_at": "Timestamp", "distance_cm": "Distance (cm)"},
                markers=True,
            )
            fig_dist.add_hline(
                y=ALARM_DISTANCE_THRESHOLD_CM,
                line_dash="dash",
                line_color="red",
                annotation_text="Alarm Threshold (270 cm)",
            )
            st.plotly_chart(fig_dist, use_container_width=True)

        with st.expander("View Raw ThingSpeak Feed Data"):
            st.dataframe(
                df[["entry_id", "created_at", "distance_cm", "water_level_cm"]].sort_values(
                    by="entry_id", ascending=False
                ),
                use_container_width=True,
            )

except requests.exceptions.RequestException as e:
    st.error(f"Failed to fetch data from ThingSpeak: {e}")

if auto_refresh:
    time.sleep(REFRESH_INTERVAL_SEC)
    st.rerun()
