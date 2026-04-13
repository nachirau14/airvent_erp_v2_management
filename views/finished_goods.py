"""Finished Goods Store Page."""
import streamlit as st
import pandas as pd
from utils.db import (
    get_all_projects, get_production_trackers,
    add_finished_good, get_finished_goods,
)
from utils.ui_helpers import section_header, empty_state, styled_metric
from config import PRODUCTION_STAGES


def render():
    st.markdown("# ✅ Finished Goods Store")
    st.markdown("*Products ready for dispatch*")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📦 Finished Goods", "➕ Add to Store"])

    with tab2:
        section_header("Move Completed Product to Finished Goods", "➕")
        projects = get_all_projects()
        if not projects:
            st.warning("No projects available.")
            return

        proj_opts = {f"{p['name']} ({p['project_id']})": p for p in projects}
        sel_proj = st.selectbox("Project *", list(proj_opts.keys()), key="fg_proj")
        project = proj_opts[sel_proj]

        # Show completed production items
        trackers = get_production_trackers(project["project_id"])
        completed = []
        for t in trackers:
            stages = t.get("stages", {})
            product_type = t.get("product_type", "Custom")
            stage_defs = PRODUCTION_STAGES.get(product_type, PRODUCTION_STAGES["Custom"])
            last_stage = stage_defs[-1][0] if stage_defs else "Complete"
            if stages.get(last_stage) == "Complete":
                completed.append(t)

        if completed:
            st.success(f"{len(completed)} product(s) with production complete")

        with st.form("add_fg", clear_on_submit=True):
            if completed:
                prod_opts = {f"{t['product_name']} ({t['product_id']})": t for t in completed}
                sel_prod = st.selectbox("Select Completed Product", list(prod_opts.keys()))
                product = prod_opts[sel_prod]
                product_id = product["product_id"]
                product_name = product["product_name"]
                quantity = st.number_input("Quantity", min_value=1, value=int(product.get("quantity", 1)))
            else:
                st.info("No completed products found. Enter details manually.")
                product_id = st.text_input("Product ID")
                product_name = st.text_input("Product Name *")
                quantity = st.number_input("Quantity", min_value=1, value=1)

            notes = st.text_area("Notes", placeholder="e.g., Quality checked, ready for dispatch")

            if st.form_submit_button("✅ Add to Finished Goods", use_container_width=True):
                if product_name:
                    fg = add_finished_good(project["project_id"], product_id, product_name, quantity, notes)
                    st.success(f"**{product_name}** added to Finished Goods Store — ID: `{fg['fg_id']}`")
                    st.rerun()
                else:
                    st.error("Product name is required.")

    with tab1:
        fg_items = get_finished_goods()

        if not fg_items:
            empty_state("✅", "No finished goods yet", "Complete production and add items to the store")
            return

        in_store = [f for f in fg_items if f.get("status") == "In Store"]
        dispatched = [f for f in fg_items if f.get("status") == "Dispatched"]

        c1, c2, c3 = st.columns(3)
        with c1:
            styled_metric("In Store", len(in_store), color="#16a34a")
        with c2:
            styled_metric("Dispatched", len(dispatched), color="#0891b2")
        with c3:
            styled_metric("Total", len(fg_items), color="#6b7280")

        st.markdown("")

        # Filter by project
        proj_filter = st.selectbox(
            "Filter by Project",
            ["All"] + list(set(f.get("project_id", "") for f in fg_items)),
            key="fg_filter",
        )

        filtered = fg_items if proj_filter == "All" else [f for f in fg_items if f.get("project_id") == proj_filter]

        if filtered:
            df = pd.DataFrame(filtered)
            cols = ["fg_id", "project_id", "product_name", "quantity", "status", "notes", "added_at"]
            available = [c for c in cols if c in df.columns]
            display_df = df[available].copy()
            display_df.columns = [c.replace("_", " ").title() for c in available]

            def color_status(row):
                status = row.get("Status", "")
                if status == "In Store":
                    return ["background-color: #dcfce7"] * len(row)
                elif status == "Dispatched":
                    return ["background-color: #dbeafe"] * len(row)
                return [""] * len(row)

            st.dataframe(display_df.style.apply(color_status, axis=1), use_container_width=True, hide_index=True)
