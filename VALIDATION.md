# Validation

Checked in the build environment:

- Python syntax compile: `streamlit_app.py`, `engineering.py`, `github_store.py`, `outputs.py`
- Performance DB extraction: 13 digital models
- Data Sheet Excel generation: valid XLSX generated with openpyxl
- Performance Curve PDF generation: valid PDF generated with ReportLab/matplotlib
- Landscape PDF render inspection: one-page output with graph, design-point table, metric descriptions and source footer
- Local optimistic-concurrency simulation: stale SHA save correctly raises ConflictError

Not tested here:

- Live deployment to the user's GitHub repositories
- Live Streamlit Community Cloud deployment
- Real GitHub API writes using the user's fine-grained PAT

Those require the user's GitHub repository and Streamlit Secrets.
