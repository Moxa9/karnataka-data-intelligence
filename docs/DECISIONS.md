# Architecture decisions

- No Docker: Python, DuckDB and Streamlit run directly on the host.
- DuckDB is the default warehouse so no database server is required.
- The selected source is a public Parquet snapshot, not a live edit-tracked feature API.
- Incrementality is based on content-addressed snapshots and stable row hashes, not a fabricated edit-date watermark.
- Spark is not used because this dataset does not justify distributed processing.
- Airflow is optional and must be installed in a separate compatible environment.
- A true parcel-level star schema and SCD Type 2 are not claimed for a taluk-boundary dataset.
