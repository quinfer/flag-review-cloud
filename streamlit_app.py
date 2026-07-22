#!/usr/bin/env python3
"""Co-author flag review app for Streamlit Community Cloud.

Binary labelling of paramilitary flags (UDA/UVF/UFF/RHC/YCV = 1).
Labels persist to a shared Google Sheet when secrets are configured;
otherwise they stay in the browser session (local demo mode).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

import sheet_store

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
COMPOSITES = ROOT / "composites"
ASSETS = ROOT / "assets"

ORG_OPTIONS = [
    "", "UDA", "UVF", "UFF", "RHC", "YCV",
    "other_proscribed", "non_paramilitary", "unknown",
]
SCENE_OPTIONS = [
    "", "paramilitary_display", "memorial", "civic",
    "sport", "national", "other", "none",
]
PARAMILITARY_ORGS = {"UDA", "UVF", "UFF", "RHC", "YCV"}

QUEUES = {
    "Register QA (334 sites)": {
        "key": "register_qa",
        "csv": DATA / "register_qa_to_label.csv",
        "composites": COMPOSITES / "qa",
        "score_col": "stage2_raw",
        "blurb": (
            "One crop per mapped flag site. Mark **1** if this is a loyalist "
            "paramilitary flag (UDA / UVF / UFF / RHC / YCV), else **0**."
        ),
    },
    "Validation round 2 (340 crops)": {
        "key": "validation_r2",
        "csv": DATA / "validation_round2_to_label.csv",
        "composites": COMPOSITES / "validation",
        "score_col": "stage2_full",
        "blurb": (
            "Fresh sample never labelled before. Rows with source **backfill** "
            "are especially important — they decide whether ~137 extra candidate "
            "sites are real."
        ),
    },
}


def _user_accounts() -> dict[str, str]:
    """Return {username: password} from secrets.

    Preferred: [users] barry = "..." / coauthor = "..."
    Fallback: single app_password (username ignored / any).
    """
    try:
        if "users" in st.secrets:
            return {str(k): str(v) for k, v in dict(st.secrets["users"]).items()}
        pw = str(st.secrets.get("app_password", "") or "").strip()
        if pw:
            return {"reviewer": pw}
    except Exception:
        pass
    return {}


def _check_password() -> bool:
    accounts = _user_accounts()
    if not accounts:
        # No auth configured (local demo without secrets)
        return True
    if st.session_state.get("_authed"):
        return True

    st.title("Paramilitary flag review")
    st.caption("Sign in with the username and password you were given.")
    user = st.text_input("Username", key="login_user")
    pw = st.text_input("Password", type="password", key="login_pw")
    if st.button("Sign in", type="primary"):
        u = (user or "").strip()
        if u in accounts and pw == accounts[u]:
            st.session_state["_authed"] = True
            st.session_state["reviewer_name"] = u
            st.rerun()
        st.error("Wrong username or password")
    return False


def _norm_label(v) -> str:
    if pd.isna(v):
        return ""
    s = str(v).strip()
    if s in {"1", "1.0"}:
        return "1"
    if s in {"0", "0.0"}:
        return "0"
    return ""


def _first_blank(df: pd.DataFrame) -> int:
    blank = df.index[df["label"].map(_norm_label) == ""]
    return int(blank[0]) if len(blank) else 0


def _next_blank(df: pd.DataFrame, after: int) -> int:
    for i in df.index:
        if i > after and _norm_label(df.at[i, "label"]) == "":
            return int(i)
    return _first_blank(df)


def _set_row_idx(sk: str, jump_key: str, new_idx: int, lo: int, hi: int) -> None:
    """Set current row and keep the 'Go to row' widget in sync.

    Streamlit persists number_input state by key; if we advance ``sk`` without
    updating the jump widget, the next run snaps back to the old row.
    """
    new_idx = max(lo - 1, min(hi - 1, int(new_idx)))
    st.session_state[sk] = new_idx
    st.session_state[jump_key] = new_idx + 1


def _render_guide() -> None:
    with st.expander("Labelling guide (read once)", expanded=False):
        st.markdown(
            """
**Positive (1)** — loyalist paramilitary organisation flag:
- **UDA** (often light blue with red border / crest text)
- **UVF**, **UFF**, **RHC**
- **YCV** modern in-situ: **navy** field, thin white horizontal stripes, white
  star/circle with Red Hand

**Negative (0)** — everything else, including:
- Ulster Banner / Union Flag / national flags
- Orange Order, Somme / 36th Division **civic** commemorative displays
- Sport, club, or unreadable crops

A Red Hand alone is **not** enough for a positive. When unsure, mark **0** and
optionally set org to `unknown`.

Org / scene fields are optional — binary label is what matters.
"""
        )
        ref = ASSETS / "reference_flags.png"
        if ref.exists():
            st.image(str(ref), caption="Reference flag types", use_container_width=True)


def _render_queue(name: str, cfg: dict) -> None:
    seed = pd.read_csv(cfg["csv"])
    df = sheet_store.load_worklist(cfg["key"], seed)
    df["label"] = df["label"].map(_norm_label)

    sk = f"idx_{cfg['key']}"
    if sk not in st.session_state:
        st.session_state[sk] = _first_blank(df)

    labeled = (df["label"] != "").sum()
    st.caption(
        f"Progress: **{labeled} / {len(df)}** labelled "
        f"({100 * labeled / max(1, len(df)):.0f}%)"
    )
    st.info(cfg["blurb"])

    # Optional row-range filter for split assignments
    with st.sidebar:
        st.subheader(f"Split — {name.split('(')[0].strip()}")
        lo = st.number_input(
            f"{cfg['key']} from row", min_value=1, max_value=len(df), value=1, key=f"lo_{cfg['key']}"
        )
        hi = st.number_input(
            f"{cfg['key']} to row", min_value=1, max_value=len(df), value=len(df), key=f"hi_{cfg['key']}"
        )
        if lo > hi:
            st.warning("from > to")

    jump_key = f"jump_{cfg['key']}"
    _set_row_idx(sk, jump_key, int(st.session_state[sk]), int(lo), int(hi))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("First unlabeled", key=f"first_{cfg['key']}"):
            for i in df.index:
                if lo - 1 <= i <= hi - 1 and _norm_label(df.at[i, "label"]) == "":
                    _set_row_idx(sk, jump_key, int(i), int(lo), int(hi))
                    break
            st.rerun()
    with c2:
        if st.button("Prev", key=f"prev_{cfg['key']}"):
            _set_row_idx(sk, jump_key, int(st.session_state[sk]) - 1, int(lo), int(hi))
            st.rerun()
    with c3:
        if st.button("Next", key=f"next_{cfg['key']}"):
            _set_row_idx(sk, jump_key, int(st.session_state[sk]) + 1, int(lo), int(hi))
            st.rerun()
    with c4:
        jump = st.number_input(
            "Go to row",
            min_value=int(lo),
            max_value=int(hi),
            step=1,
            key=jump_key,
        )
        if int(jump) - 1 != int(st.session_state[sk]):
            _set_row_idx(sk, jump_key, int(jump) - 1, int(lo), int(hi))
            st.rerun()

    idx = int(st.session_state[sk])
    row = df.iloc[idx]
    crop_id = str(row["crop_id"])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Row", f"{idx + 1}/{len(df)}")
    score = row.get(cfg["score_col"], "")
    try:
        m2.metric("Score", f"{float(score):.3f}")
    except (TypeError, ValueError):
        m2.metric("Score", str(score) or "n/a")
    m3.metric("Town / band", str(row.get("town") or row.get("band") or "")[:28])
    m4.metric("Source", str(row.get("stage2_source") or row.get("in_sensitivity_088") or ""))

    st.code(crop_id)

    img = cfg["composites"] / crop_id
    if img.exists():
        st.image(str(img), use_container_width=True,
                 caption="Left: scene · Right: zoom")
    else:
        st.warning(f"Composite missing: {crop_id}")

    reviewer = st.session_state.get("reviewer_name", "")
    current = _norm_label(row.get("label", ""))
    choice = st.radio(
        "Label",
        options=["", "1", "0"],
        index=["", "1", "0"].index(current) if current in {"", "1", "0"} else 0,
        format_func=lambda x: {
            "": "— skip —",
            "1": "1 = Paramilitary",
            "0": "0 = Not paramilitary",
        }[x],
        horizontal=True,
        key=f"lab_{cfg['key']}_{idx}",
    )

    cur_org = str(row.get("org", "") or "")
    cur_scene = str(row.get("scene_context", "") or "")
    if cur_org not in ORG_OPTIONS:
        cur_org = ""
    if cur_scene not in SCENE_OPTIONS:
        cur_scene = ""
    o1, o2 = st.columns(2)
    with o1:
        org = st.selectbox(
            "Org (optional)",
            ORG_OPTIONS,
            index=ORG_OPTIONS.index(cur_org),
            format_func=lambda x: "— not set —" if x == "" else x,
            key=f"org_{cfg['key']}_{idx}",
        )
    with o2:
        scene = st.selectbox(
            "Scene (optional)",
            SCENE_OPTIONS,
            index=SCENE_OPTIONS.index(cur_scene),
            format_func=lambda x: "— not set —" if x == "" else x,
            key=f"sc_{cfg['key']}_{idx}",
        )

    if org in PARAMILITARY_ORGS and choice == "0":
        st.warning(f"Org {org} usually implies label 1")
    if org in PARAMILITARY_ORGS and not choice:
        st.caption(f"Tip: {org} → set label to 1")

    def _save_and_maybe_advance(advance: bool) -> None:
        if not reviewer:
            st.error("Not signed in — refresh and sign in again.")
            return
        if choice not in {"0", "1"}:
            st.error("Pick a binary label (1 or 0) before saving.")
            return
        try:
            sheet_store.save_label(
                cfg["key"], seed, crop_id, choice, org, scene, reviewer
            )
        except Exception as exc:
            st.error(f"Save failed: {exc}")
            return
        # Mark current row labelled in this render's frame so next-blank skips it
        df.at[idx, "label"] = choice
        st.success("Saved")
        if advance:
            nxt = _next_blank(df, idx)
            if not (lo - 1 <= nxt <= hi - 1):
                nxt = idx
                for i in df.index:
                    if lo - 1 <= i <= hi - 1 and _norm_label(df.at[i, "label"]) == "":
                        nxt = int(i)
                        break
            _set_row_idx(sk, jump_key, nxt, int(lo), int(hi))
            st.rerun()

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Save", key=f"save_{cfg['key']}"):
            _save_and_maybe_advance(False)
    with b2:
        if st.button("Save + next unlabeled", key=f"saven_{cfg['key']}", type="primary"):
            _save_and_maybe_advance(True)

    st.download_button(
        "Download current labels CSV",
        data=sheet_store.export_csv(df),
        file_name=f"{cfg['key']}_labels.csv",
        mime="text/csv",
        key=f"dl_{cfg['key']}",
    )


def main() -> None:
    st.set_page_config(page_title="Flag review", layout="wide")
    if not _check_password():
        st.stop()

    st.title("Paramilitary flag review")
    mode = "Google Sheet (shared)" if sheet_store._secrets_ready() else "local demo (session only)"
    st.caption(f"Storage: **{mode}**")

    with st.sidebar:
        st.header("Signed in")
        st.write(f"**{st.session_state.get('reviewer_name', '')}**")
        if st.button("Sign out"):
            st.session_state.pop("_authed", None)
            st.rerun()
        st.caption("Labels are attributed to this username in the Sheet.")
        if not sheet_store._secrets_ready():
            st.warning(
                "No Google Sheet secrets configured — labels stay in this "
                "browser session only. Add secrets for co-author sharing."
            )

    _render_guide()
    tabs = st.tabs(list(QUEUES.keys()))
    for tab, (name, cfg) in zip(tabs, QUEUES.items()):
        with tab:
            _render_queue(name, cfg)


if __name__ == "__main__":
    main()
