
import sys
import json
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st


# ============================================================
# 1. PROJECT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import WAREHOUSE_PATH


st.set_page_config(
    page_title="Karnataka Data Intelligence Platform",
    page_icon="📊",
    layout="wide"
)


# ============================================================
# 2. HEADER
# ============================================================

st.title("Karnataka Data Intelligence Platform")

st.caption(
    "Public Karnataka administrative-boundary "
    "snapshot analytics"
)


# ============================================================
# 3. LOAD DATA FROM DUCKDB
# ============================================================

@st.cache_data(ttl=60)
def load_dashboard_data(warehouse_path):

    con = duckdb.connect(
        warehouse_path,
        read_only=True
    )

    try:
        records = con.execute(
            "SELECT attributes FROM current_features"
        ).fetchall()

        parsed_records = []

        for row in records:

            attributes = row[0]

            if attributes is None:
                continue

            if isinstance(attributes, bytes):
                attributes = attributes.decode("utf-8")

            if isinstance(attributes, str):
                attributes = json.loads(attributes)

            if isinstance(attributes, dict):
                parsed_records.append(attributes)

        df = pd.DataFrame(parsed_records)

        tables = con.execute(
            "SHOW TABLES"
        ).df()["name"].tolist()

        history = {}

        for table_name in ["snapshots", "pipeline_runs"]:

            if table_name in tables:

                history[table_name] = con.execute(
                    f'SELECT * FROM "{table_name}" LIMIT 100'
                ).df()

        return df, history

    finally:
        con.close()


# ============================================================
# 4. MAIN DASHBOARD
# ============================================================

try:

    df, history = load_dashboard_data(
        str(WAREHOUSE_PATH)
    )

    if df.empty:
        st.warning("No records found in the warehouse.")
        st.stop()

    # --------------------------------------------------------
    # 5. STANDARDISE DATA COLUMNS
    # --------------------------------------------------------

    expected_columns = [
        "KGISTalukC",
        "LGD_TalukC",
        "KGISTalukN",
        "KGISDistri"
    ]

    for column in expected_columns:

        if column not in df.columns:
            df[column] = pd.NA

    # Preserve leading zeros in administrative codes
    for column in [
        "KGISTalukC",
        "LGD_TalukC",
        "KGISDistri"
    ]:

        df[column] = (
            df[column]
            .astype("string")
            .str.strip()
            .replace("", pd.NA)
        )

    df["KGISTalukN"] = (
        df["KGISTalukN"]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
    )

    # --------------------------------------------------------
    # 6. CALCULATE DASHBOARD METRICS
    # --------------------------------------------------------

    total_taluks = len(df)

    total_districts = (
        df["KGISDistri"].dropna().nunique()
    )

    unique_lgd_codes = (
        df["LGD_TalukC"].dropna().nunique()
    )

    duplicate_kgis_codes = int(
        df.loc[
            df["KGISTalukC"].notna(),
            "KGISTalukC"
        ].duplicated().sum()
    )

    duplicate_lgd_codes = int(
        df.loc[
            df["LGD_TalukC"].notna(),
            "LGD_TalukC"
        ].duplicated().sum()
    )

    missing_taluk_names = int(
        df["KGISTalukN"].isna().sum()
    )

    missing_kgis_codes = int(
        df["KGISTalukC"].isna().sum()
    )

    missing_lgd_codes = int(
        df["LGD_TalukC"].isna().sum()
    )

    # --------------------------------------------------------
    # 7. PLATFORM OVERVIEW
    # --------------------------------------------------------

    st.subheader("Platform Overview")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total Taluks",
        f"{total_taluks:,}"
    )

    col2.metric(
        "District Codes",
        f"{total_districts:,}"
    )

    col3.metric(
        "Unique LGD Codes",
        f"{unique_lgd_codes:,}"
    )

    col4.metric(
        "Duplicate Taluk Codes",
        f"{duplicate_kgis_codes:,}"
    )

    st.divider()

    # --------------------------------------------------------
    # 8. DISTRICT FILTER
    # --------------------------------------------------------

    st.subheader("District-wise Analytics")

    districts = sorted(
        df["KGISDistri"]
        .dropna()
        .unique()
        .tolist()
    )

    selected_district = st.selectbox(
        "Select a district code",
        ["All Districts"] + districts
    )

    if selected_district == "All Districts":

        filtered_df = df.copy()

    else:

        filtered_df = df[
            df["KGISDistri"] == selected_district
        ].copy()

    # --------------------------------------------------------
    # 9. DISTRICT-WISE TALUK DISTRIBUTION
    # --------------------------------------------------------

    district_counts = (
        df.dropna(subset=["KGISDistri"])
        .groupby("KGISDistri")
        .size()
        .reset_index(name="Taluk Count")
        .sort_values(
            "Taluk Count",
            ascending=False
        )
    )

    chart_col, summary_col = st.columns([2, 1])

    with chart_col:

        st.markdown("#### Taluks by District Code")

        if not district_counts.empty:

            st.bar_chart(
                district_counts.set_index("KGISDistri"),
                use_container_width=True
            )

        else:

            st.info("No district information available.")

    with summary_col:

        st.markdown("#### District Summary")

        st.dataframe(
            district_counts,
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    # --------------------------------------------------------
    # 10. DATA QUALITY OVERVIEW
    # --------------------------------------------------------

    st.subheader("Data Quality Overview")

    quality_col1, quality_col2, quality_col3 = st.columns(3)

    quality_col1.metric(
        "Missing Taluk Names",
        missing_taluk_names
    )

    quality_col2.metric(
        "Missing KGIS Codes",
        missing_kgis_codes
    )

    quality_col3.metric(
        "Missing LGD Codes",
        missing_lgd_codes
    )

    quality_checks = pd.DataFrame({

        "Quality Check": [
            "Missing Taluk Names",
            "Missing KGIS Taluk Codes",
            "Missing LGD Taluk Codes",
            "Duplicate KGIS Taluk Codes",
            "Duplicate LGD Taluk Codes"
        ],

        "Issue Count": [
            missing_taluk_names,
            missing_kgis_codes,
            missing_lgd_codes,
            duplicate_kgis_codes,
            duplicate_lgd_codes
        ]

    })

    st.dataframe(
        quality_checks,
        use_container_width=True,
        hide_index=True
    )

    st.caption(
        "Basic null and duplicate checks on administrative "
        "attributes. Geometry validation is not included."
    )

    # --------------------------------------------------------
    # 11. DUPLICATE LGD CODE INVESTIGATION
    # --------------------------------------------------------

    st.markdown("### Duplicate LGD Code Details")

    duplicate_lgd = df[
        df["LGD_TalukC"].notna()
        & df["LGD_TalukC"].duplicated(keep=False)
    ].sort_values("LGD_TalukC")

    if not duplicate_lgd.empty:

        st.warning(
            f"Found {len(duplicate_lgd)} records "
            "with repeated LGD codes."
        )

        st.dataframe(
            duplicate_lgd[
                [
                    "LGD_TalukC",
                    "KGISTalukC",
                    "KGISTalukN",
                    "KGISDistri"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            "All records sharing a repeated LGD code are shown. "
            "These records have not been automatically deleted."
        )

    else:

        st.success(
            "No duplicate LGD codes found."
        )

    st.divider()

    # --------------------------------------------------------
    # 12. TALUK RECORDS
    # --------------------------------------------------------

    st.subheader("Taluk Records")

    display_columns = [
        "KGISTalukC",
        "LGD_TalukC",
        "KGISTalukN",
        "KGISDistri"
    ]

    display_df = filtered_df[
        display_columns
    ].copy()

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=400
    )

    st.caption(
        f"Showing {len(display_df):,} records."
    )

    # CSV DOWNLOAD

    csv_data = display_df.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        label="Download filtered records as CSV",
        data=csv_data,
        file_name="karnataka_taluk_records.csv",
        mime="text/csv"
    )

    st.divider()

    # --------------------------------------------------------
    # 13. SNAPSHOT HISTORY
    # --------------------------------------------------------

    st.subheader("Snapshot & Pipeline History")

    if "snapshots" in history:

        st.markdown("#### Dataset Snapshots")

        snapshot_df = history["snapshots"]

        safe_columns = [
            column
            for column in snapshot_df.columns
            if not any(
                word in column.lower()
                for word in [
                    "attributes",
                    "geometry",
                    "raw_path"
                ]
            )
        ]

        if safe_columns:

            st.dataframe(
                snapshot_df[safe_columns],
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "No displayable snapshot metadata found."
            )

    else:

        st.info(
            "Snapshot history is not available."
        )

    # --------------------------------------------------------
    # 14. PIPELINE RUN HISTORY
    # --------------------------------------------------------

    if "pipeline_runs" in history:

        st.markdown("#### Recent Pipeline Runs")

        runs_df = history["pipeline_runs"]

        safe_columns = [
            column
            for column in runs_df.columns
            if not any(
                word in column.lower()
                for word in [
                    "attributes",
                    "geometry",
                    "raw_path"
                ]
            )
        ]

        if safe_columns:

            st.dataframe(
                runs_df[safe_columns],
                use_container_width=True,
                hide_index=True
            )

    else:

        st.info(
            "Pipeline run history is not available."
        )

    st.divider()

    # --------------------------------------------------------
    # 15. SOURCE INFORMATION
    # --------------------------------------------------------

    st.subheader("Data Source")

    st.markdown(
        """
        - **Dataset:** Karnataka Taluk Boundaries
        - **Publisher:** K-GIS / KSRSAC
        - **Source mirror:** Source Cooperative
        - **Storage:** Local Parquet snapshots
        - **Warehouse:** DuckDB
        """
    )

    st.markdown(
        "[K-GIS Official Portal]"
        "(https://kgis.ksrsac.in/kgis/downloads.aspx)"
    )

    st.markdown(
        "[Source Cooperative Dataset]"
        "(https://source.coop/krishnaglodha/ksrsac-gis)"
    )

    st.success(
        "Dashboard loaded successfully."
    )


# ============================================================
# 16. ERROR HANDLING
# ============================================================

except Exception as e:

    st.error(
        f"Dashboard error: {e}"
    )

    st.exception(e)
