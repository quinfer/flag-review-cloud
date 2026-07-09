"""Google Sheet backed label store for Streamlit Community Cloud.

Each worklist has its own worksheet. Rows are keyed by crop_id.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

WORKSHEETS = {
    "register_qa": "register_qa",
    "validation_r2": "validation_r2",
}

COLUMNS = [
    "crop_id",
    "image_id",
    "label",
    "org",
    "scene_context",
    "reviewer",
    "updated_at",
    # context columns (copied from seed CSV; not edited by reviewers)
    "town",
    "stage2_raw",
    "stage2_full",
    "stage2_source",
    "band",
    "in_sensitivity_088",
    "n_crops_at_site",
    "site_id",
]


def _secrets_ready() -> bool:
    try:
        # st.secrets raises if file missing; treat as local demo mode
        _ = st.secrets
        return (
            "gcp_service_account" in st.secrets
            and "sheet_id" in st.secrets
            and bool(st.secrets["sheet_id"])
        )
    except Exception:
        return False


@st.cache_resource
def _client():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=scopes
    )
    return gspread.authorize(creds)


def _open_sheet():
    return _client().open_by_key(st.secrets["sheet_id"])


def _ensure_worksheet(name: str, seed: pd.DataFrame):
    sh = _open_sheet()
    try:
        ws = sh.worksheet(name)
    except Exception:
        ws = sh.add_worksheet(title=name, rows=max(len(seed) + 50, 100), cols=len(COLUMNS))
        # seed empty labels
        out = _seed_frame(seed)
        ws.update([COLUMNS] + out.fillna("").astype(str).values.tolist())
        return ws

    # If worksheet exists but is empty / header-only, seed it
    values = ws.get_all_values()
    if len(values) <= 1:
        out = _seed_frame(seed)
        ws.clear()
        ws.update([COLUMNS] + out.fillna("").astype(str).values.tolist())
    return ws


def _seed_frame(seed: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(columns=COLUMNS)
    out["crop_id"] = seed["crop_id"].astype(str)
    out["image_id"] = seed["image_id"].astype(str)
    for col in COLUMNS:
        if col in ("crop_id", "image_id", "label", "org", "scene_context", "reviewer", "updated_at"):
            continue
        if col in seed.columns:
            out[col] = seed[col].astype(str)
        else:
            out[col] = ""
    out["label"] = ""
    out["org"] = ""
    out["scene_context"] = ""
    out["reviewer"] = ""
    out["updated_at"] = ""
    return out[COLUMNS]


def load_worklist(key: str, seed: pd.DataFrame) -> pd.DataFrame:
    """Return the live worklist (Sheet if configured, else local seed + session)."""
    if not _secrets_ready():
        # Local / demo mode: keep labels in session state
        sk = f"_local_{key}"
        if sk not in st.session_state:
            st.session_state[sk] = _seed_frame(seed)
        return st.session_state[sk].copy()

    ws = _ensure_worksheet(WORKSHEETS[key], seed)
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[COLUMNS].copy()


def save_label(
    key: str,
    seed: pd.DataFrame,
    crop_id: str,
    label: str,
    org: str,
    scene: str,
    reviewer: str,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if not _secrets_ready():
        sk = f"_local_{key}"
        df = st.session_state[sk]
        idx = df.index[df["crop_id"].astype(str) == str(crop_id)]
        if len(idx):
            i = int(idx[0])
            df.at[i, "label"] = label
            df.at[i, "org"] = org
            df.at[i, "scene_context"] = scene
            df.at[i, "reviewer"] = reviewer
            df.at[i, "updated_at"] = now
        return

    ws = _ensure_worksheet(WORKSHEETS[key], seed)
    # Find row (1-indexed; row 1 is header)
    cells = ws.col_values(1)  # crop_id column
    try:
        row_num = cells.index(str(crop_id)) + 1
    except ValueError:
        raise ValueError(f"crop_id not found in sheet: {crop_id}")

    # Columns: A crop_id, B image_id, C label, D org, E scene, F reviewer, G updated_at
    ws.update(
        f"C{row_num}:G{row_num}",
        [[label, org, scene, reviewer, now]],
    )


def export_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")
