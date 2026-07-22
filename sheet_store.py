"""Google Sheet backed label store for Streamlit Community Cloud.

Each worklist has its own worksheet. Rows are keyed by crop_id.

Important: the free Sheets API has a tight per-minute read quota. We therefore
cache each worklist in ``st.session_state`` and only hit the API on first load
(or explicit refresh). Saves update a single row (write) and the local cache —
they do not re-download the sheet.
"""
from __future__ import annotations

from datetime import datetime, timezone

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
        _ = st.secrets
        return (
            "gcp_service_account" in st.secrets
            and "sheet_id" in st.secrets
            and bool(st.secrets["sheet_id"])
        )
    except Exception:
        return False


def _df_key(key: str) -> str:
    return f"_sheet_df_{key}"


def _rowmap_key(key: str) -> str:
    return f"_sheet_rowmap_{key}"


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


@st.cache_resource
def _spreadsheet():
    return _client().open_by_key(st.secrets["sheet_id"])


def _get_or_create_worksheet(name: str, seed: pd.DataFrame):
    """Return worksheet; seed only if it does not exist yet (one-time write)."""
    sh = _spreadsheet()
    try:
        return sh.worksheet(name)
    except Exception:
        ws = sh.add_worksheet(
            title=name, rows=max(len(seed) + 50, 100), cols=len(COLUMNS)
        )
        out = _seed_frame(seed)
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


def _fetch_from_sheet(key: str, seed: pd.DataFrame) -> pd.DataFrame:
    ws = _get_or_create_worksheet(WORKSHEETS[key], seed)
    values = ws.get_all_values()
    if len(values) <= 1:
        # Empty / header-only — seed once
        out = _seed_frame(seed)
        ws.clear()
        ws.update([COLUMNS] + out.fillna("").astype(str).values.tolist())
        df = out.copy()
    else:
        header, *rows = values
        # Align to expected columns (Sheet may have extras/missing)
        records = []
        for row in rows:
            rec = {h: (row[i] if i < len(row) else "") for i, h in enumerate(header)}
            records.append(rec)
        df = pd.DataFrame(records)
        for c in COLUMNS:
            if c not in df.columns:
                df[c] = ""
        df = df[COLUMNS].copy()

    # 1-based Sheet row numbers (row 1 = header)
    rowmap = {str(cid): i + 2 for i, cid in enumerate(df["crop_id"].astype(str))}
    st.session_state[_df_key(key)] = df
    st.session_state[_rowmap_key(key)] = rowmap
    return df


def load_worklist(key: str, seed: pd.DataFrame, force_reload: bool = False) -> pd.DataFrame:
    """Return the worklist, using a session cache to avoid Sheets read quota."""
    if not _secrets_ready():
        sk = f"_local_{key}"
        if sk not in st.session_state:
            st.session_state[sk] = _seed_frame(seed)
        return st.session_state[sk].copy()

    ck = _df_key(key)
    if force_reload or ck not in st.session_state:
        _fetch_from_sheet(key, seed)
    return st.session_state[ck].copy()


def invalidate_cache(key: str | None = None) -> None:
    """Drop cached worklist(s) so the next load hits the Sheet."""
    keys = [key] if key else list(WORKSHEETS)
    for k in keys:
        st.session_state.pop(_df_key(k), None)
        st.session_state.pop(_rowmap_key(k), None)


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
    crop_id = str(crop_id)

    if not _secrets_ready():
        sk = f"_local_{key}"
        df = st.session_state[sk]
        idx = df.index[df["crop_id"].astype(str) == crop_id]
        if len(idx):
            i = int(idx[0])
            df.at[i, "label"] = label
            df.at[i, "org"] = org
            df.at[i, "scene_context"] = scene
            df.at[i, "reviewer"] = reviewer
            df.at[i, "updated_at"] = now
        return

    # Ensure cache + row map exist (one read if this is the first action)
    if _df_key(key) not in st.session_state:
        _fetch_from_sheet(key, seed)

    rowmap = st.session_state[_rowmap_key(key)]
    if crop_id not in rowmap:
        # Rare: cache stale — one reload
        _fetch_from_sheet(key, seed)
        rowmap = st.session_state[_rowmap_key(key)]
    if crop_id not in rowmap:
        raise ValueError(f"crop_id not found in sheet: {crop_id}")

    row_num = rowmap[crop_id]
    ws = _get_or_create_worksheet(WORKSHEETS[key], seed)
    # Columns: A crop_id, B image_id, C label, D org, E scene, F reviewer, G updated_at
    ws.update(f"C{row_num}:G{row_num}", [[label, org, scene, reviewer, now]])

    # Update local cache — no re-read
    df = st.session_state[_df_key(key)]
    idx = df.index[df["crop_id"].astype(str) == crop_id]
    if len(idx):
        i = int(idx[0])
        df.at[i, "label"] = label
        df.at[i, "org"] = org
        df.at[i, "scene_context"] = scene
        df.at[i, "reviewer"] = reviewer
        df.at[i, "updated_at"] = now


def export_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")
