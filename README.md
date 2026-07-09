# Paramilitary flag review (Streamlit Community Cloud)

Shared labelling app for co-authors. Two queues:

1. **Register QA** — 334 mapped sites (is the published register honest?)
2. **Validation round 2** — 340 fresh crops (are the +137 Stage-1-backfill sites real?)

Labels are stored in a **Google Sheet** so they survive app restarts and can be
done by several people at once.

## One-time setup (you, the project lead)

### 1. Create a Google Sheet
1. Create a blank Google Spreadsheet (any name, e.g. `flag_review_labels`).
2. Copy the spreadsheet ID from the URL:  
   `https://docs.google.com/spreadsheets/d/`**`SPREADSHEET_ID`**`/edit`

### 2. Create a Google Cloud service account
1. In [Google Cloud Console](https://console.cloud.google.com/) create (or pick) a project.
2. Enable the **Google Sheets API** and **Google Drive API**.
3. **IAM & Admin → Service accounts → Create**.
4. Create a JSON key for that account; download it.
5. Open the JSON and note `client_email`.
6. In the Google Sheet: **Share →** paste `client_email` as **Editor**.

### 3. Put this folder on GitHub
Create a **new private repo** (recommended) and push only this folder as the repo root:

```bash
cd flag_review_cloud
git init
git add .
git commit -m "Flag review app for Streamlit Community Cloud"
# create empty private repo on GitHub, then:
git branch -M main
git remote add origin git@github.com:YOUR_USER/flag-review-cloud.git
git push -u origin main
```

Do **not** commit `.streamlit/secrets.toml` (it is gitignored). Composites (~50 MB) are included on purpose.

### 4. Deploy on Streamlit Community Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. **New app** → pick the repo → main file: `streamlit_app.py`.
3. Under **Advanced settings → Secrets**, paste something like:

```toml
app_password = "a-shared-password-for-coauthors"

sheet_id = "SPREADSHEET_ID_FROM_STEP_1"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "flag-review@....iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

Copy every field from the service-account JSON into `[gcp_service_account]`.  
Keep the `\n` characters inside `private_key`.

4. Deploy. On first open of each tab, the app creates worksheets `register_qa` and
   `validation_r2` and seeds them from the CSVs.

### 5. Local smoke test (optional)
```bash
cd flag_review_cloud
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# optional: cp .streamlit/secrets.toml.example .streamlit/secrets.toml  # then edit
streamlit run streamlit_app.py
```
Without secrets, the app runs in **local demo mode** (labels only in the browser session).

## What to send co-authors

> Please open: **\<your Streamlit URL\>**  
> Password: **\<app_password\>**  
> Enter your name in the sidebar before saving.  
>  
> **Your assignment:** Register QA rows **1–167** (set the split in the sidebar).  
> For each image: **1** = loyalist paramilitary (UDA/UVF/UFF/RHC/YCV), **0** = anything else.  
> Org/scene optional. Use **Save + next unlabeled**.  
> Guide is in the expander at the top of the page.

Suggested splits (non-overlapping):

| Person | Register QA | Validation round 2 |
|--------|-------------|--------------------|
| A | 1–167 | 1–170 |
| B | 168–334 | 171–340 |

Or give one person Register QA and another Validation round 2.

## Pulling labels back into the project

From the Google Sheet: **File → Download → CSV** for each worksheet, or use the
in-app **Download current labels CSV** button, then save as:

- `flagdata/out/rollup/register_qa_reviewed.csv`
- `flagdata/out/rollup/validation_round2_reviewed.csv`

(Keep at least `crop_id` and `label` columns.)

## Notes
- Binary label is required to save; org/scene are optional.
- Concurrent labelling of **different rows** is fine; avoid two people on the same row.
- Streamlit Cloud free tier may sleep the app; first load after sleep can take ~30s.
