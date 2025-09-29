import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import folium
from folium.plugins import Draw
import geopandas as gpd
from shapely.geometry import shape
import requests
import datetime
import shutil

# -------------------------
# Elastic connection setup
# -------------------------
ELASTIC_URL = "https://eda6f533d8524075abddae2a7527be04.us-central1.gcp.cloud.es.io:443"
ELASTIC_INDEX = "fire_districts"
ELASTIC_API_KEY = st.secrets["ELASTIC_API_KEY"]  # stored in Streamlit Cloud secrets

HEADERS = {
    "Authorization": f"ApiKey {ELASTIC_API_KEY}",
    "Content-Type": "application/json"
}

st.set_page_config(page_title="Fire Districts Tool", layout="wide")

# -------------------------
# Header
# -------------------------
st.markdown(
    "<h1 style='text-align:center; color:firebrick;'>Fire District Mapping Tool</h1>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center;'>Draw, save, manage, and export fire districts with ease.</p>",
    unsafe_allow_html=True
)

# -------------------------
# Layout: Map on left, Info on right
# -------------------------
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Map")

    # Create Folium Map
    m = folium.Map(location=[40.7, -73.9], zoom_start=8)

    draw = Draw(
        draw_options={
            "polyline": False,
            "circle": False,
            "marker": False,
            "circlemarker": False
        },
        export=False
    )
    draw.add_to(m)

    # Render Streamlit Folium Map
    st_data = st_folium(m, width=800, height=500)

with col2:
    st.subheader("District Information")

    # Handle New Polygon
    if st_data and st_data.get("last_active_drawing"):
        feature = st_data["last_active_drawing"]
        geometry = feature["geometry"]

        district_name = st.text_input("Enter district name:", "")

        # Save to Elasticsearch
        if st.button("Save to Elasticsearch", use_container_width=True):
            doc = {
                "district_name": district_name if district_name else "Unnamed District",
                "geometry": {
                    "type": geometry["type"],
                    "coordinates": geometry["coordinates"]
                },
                "created_at": datetime.datetime.utcnow().isoformat()
            }

            r = requests.post(
                f"{ELASTIC_URL}/{ELASTIC_INDEX}/_doc",
                headers=HEADERS,
                json=doc
            )
            if r.status_code in [200, 201]:
                st.success("Polygon saved to Elasticsearch!")
            else:
                st.error(f"Error saving to Elasticsearch: {r.text}")

        # -------------------------
        # Export Options
        # -------------------------
        st.subheader("Export Options")

        gdf = gpd.GeoDataFrame(
            [{"district_name": district_name, "geometry": shape(geometry)}],
            crs="EPSG:4326"
        )

        gdf.to_file("fire_district.geojson", driver="GeoJSON")
        gdf.to_file("fire_district.shp", driver="ESRI Shapefile")
        gdf.to_file("fire_district.kml", driver="KML")

        with open("fire_district.geojson", "rb") as f:
            st.download_button("Download GeoJSON", f, "fire_district.geojson")

        shutil.make_archive("fire_district", "zip", ".", "fire_district.shp")
        with open("fire_district.zip", "rb") as f:
            st.download_button("Download Shapefile (.zip)", f, "fire_district.zip")

        with open("fire_district.kml", "rb") as f:
            st.download_button("Download KML", f, "fire_district.kml")

# -------------------------
# Saved Districts Section
# -------------------------
st.markdown("---")
st.subheader("Saved Districts")

r = requests.get(
    f"{ELASTIC_URL}/{ELASTIC_INDEX}/_search",
    headers=HEADERS,
    json={"size": 1000, "_source": ["district_name", "created_at"]}
)

if r.status_code == 200:
    hits = r.json()["hits"]["hits"]
    if hits:
        data = [
            {
                "id": h["_id"],
                "district_name": h["_source"].get("district_name", "Unnamed"),
                "created_at": h["_source"].get("created_at", "")
            }
            for h in hits
        ]

        df = pd.DataFrame(data)

        # Show districts table
        st.dataframe(df, use_container_width=True)

        # Download as CSV
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download Districts CSV", csv, "districts.csv", "text/csv")

        # Delete option
        district_to_delete = st.selectbox(
            "Select a district to delete", df["district_name"].tolist()
        )

        if st.button("Delete District", type="primary"):
            doc_id = df.loc[df["district_name"] == district_to_delete, "id"].values[0]
            delete_res = requests.delete(
                f"{ELASTIC_URL}/{ELASTIC_INDEX}/_doc/{doc_id}",
                headers=HEADERS
            )
            if delete_res.status_code == 200:
                st.success(f"{district_to_delete} deleted from Elasticsearch")
                st.rerun()
            else:
                st.error(f"Error deleting: {delete_res.text}")
    else:
        st.info("No districts saved yet.")
else:
    st.error(f"Error fetching districts: {r.text}")
