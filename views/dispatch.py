"""Dispatch Goods Page."""
import streamlit as st
import pandas as pd
from utils.db import (
    get_all_projects, get_finished_goods, dispatch_goods,
    get_dispatched_goods, update_project_status,
)
from utils.ui_helpers import section_header, empty_state, styled_metric


def render():
    st.markdown("# 🚚 Dispatch")
    st.markdown("*Dispatch finished goods from the store*")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📋 Dispatch History", "➕ Create Dispatch"])

    with tab2:
        section_header("Dispatch Finished Goods", "🚚")

        projects = get_all_projects()
        if not projects:
            st.warning("No projects available.")
            return

        proj_opts = {f"{p['name']} ({p['project_id']})": p for p in projects}
        sel_proj = st.selectbox("Project *", list(proj_opts.keys()), key="dsp_proj")
        project = proj_opts[sel_proj]

        # Get FG items in store for this project
        fg_items = get_finished_goods(project["project_id"])
        in_store = [f for f in fg_items if f.get("status") == "In Store"]

        if not in_store:
            st.info("No finished goods in store for this project.")
            return

        st.markdown(f"**{len(in_store)} item(s) available for dispatch**")

        # Select items to dispatch
        selected_fgs = []
        for fg in in_store:
            if st.checkbox(
                f"📦 {fg['product_name']} (Qty: {fg.get('quantity', 1)}) — {fg['fg_id']}",
                key=f"dsel_{fg['fg_id']}",
            ):
                selected_fgs.append(fg["fg_id"])

        if selected_fgs:
            with st.form("dispatch_form"):
                c1, c2 = st.columns(2)
                with c1:
                    dispatch_to = st.text_input("Dispatch To *", placeholder="Client site address")
                with c2:
                    vehicle_no = st.text_input("Vehicle Number *", placeholder="e.g., KA-01-AB-1234")
                notes = st.text_area("Dispatch Notes", placeholder="e.g., DC No., Challan details...")

                if st.form_submit_button("🚚 Dispatch Selected Items", use_container_width=True, type="primary"):
                    if dispatch_to and vehicle_no:
                        d = dispatch_goods(project["project_id"], selected_fgs, dispatch_to, vehicle_no, notes)
                        st.success(f"Dispatched {len(selected_fgs)} item(s) — Dispatch ID: `{d['dispatch_id']}`")

                        # Check if all FGs for project are dispatched
                        remaining = [f for f in get_finished_goods(project["project_id"]) if f.get("status") == "In Store"]
                        if not remaining:
                            update_project_status(project["project_id"], "Dispatched")
                            st.success("All goods dispatched! Project marked as Dispatched.")
                        st.rerun()
                    else:
                        st.error("Dispatch To and Vehicle Number are required.")

    with tab1:
        dispatched = get_dispatched_goods()
        if not dispatched:
            empty_state("🚚", "No dispatches yet")
            return

        styled_metric("Total Dispatches", len(dispatched), color="#0891b2")
        st.markdown("")

        df = pd.DataFrame(dispatched)
        cols = ["dispatch_id", "project_id", "dispatch_to", "vehicle_no", "notes", "dispatched_at"]
        available = [c for c in cols if c in df.columns]
        display_df = df[available].copy()
        display_df.columns = [c.replace("_", " ").title() for c in available]
        st.dataframe(display_df, use_container_width=True, hide_index=True)
