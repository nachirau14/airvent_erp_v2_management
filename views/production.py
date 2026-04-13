"""Production Tracking Page - track manufacturing stages."""
import streamlit as st
import pandas as pd
from utils.db import (
    get_all_projects, create_production_tracker, get_production_trackers,
    update_production_stage,
)
from utils.ui_helpers import (
    section_header, empty_state, production_stage_color, render_production_progress,
)
from config import PRODUCTION_STAGES


def render():
    st.markdown("# 🏗️ Production Tracking")
    st.markdown("*Track manufacturing progress for each product across production stages*")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📊 Track Production", "➕ Add Product to Track"])

    # ─── Add Tracker ──────────────────────────────────────────────
    with tab2:
        section_header("Add Product to Production Tracking", "🆕")

        projects = get_all_projects()
        if not projects:
            st.warning("Create a project first.")
            return

        with st.form("add_production", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                proj_opts = {f"{p['name']} ({p['project_id']})": p for p in projects}
                sel_proj = st.selectbox("Project *", list(proj_opts.keys()))
            with c2:
                product_name = st.text_input("Product Name *", placeholder="e.g., Bagfilter Unit #1")
            with c3:
                product_type = st.selectbox("Product Type", list(PRODUCTION_STAGES.keys()))

            quantity = st.number_input("Quantity", min_value=1, value=1)

            st.markdown("**Production Stages:**")
            stages = PRODUCTION_STAGES[product_type]
            for stage_name, statuses in stages:
                st.caption(f"• {stage_name}: {' → '.join(statuses)}")

            if st.form_submit_button("✅ Start Tracking", use_container_width=True):
                if product_name:
                    project = proj_opts[sel_proj]
                    tracker = create_production_tracker(
                        project["project_id"], product_name, product_type, quantity, stages,
                    )
                    st.success(f"Tracking started for **{product_name}** — ID: `{tracker['product_id']}`")
                    st.rerun()
                else:
                    st.error("Product name is required.")

    # ─── Track Production ─────────────────────────────────────────
    with tab1:
        projects = get_all_projects()
        if not projects:
            empty_state("🏗️", "No projects yet")
            return

        proj_opts = {f"{p['name']} ({p['project_id']})": p for p in projects}
        sel_proj = st.selectbox("Select Project", list(proj_opts.keys()), key="track_proj")
        project = proj_opts[sel_proj]

        trackers = get_production_trackers(project["project_id"])

        if not trackers:
            empty_state("🏗️", "No products being tracked", "Add products in the 'Add Product to Track' tab")
            return

        for tracker in trackers:
            product_type = tracker.get("product_type", "Custom")
            stages = PRODUCTION_STAGES.get(product_type, PRODUCTION_STAGES["Custom"])
            stage_dict = tracker.get("stages", {})

            with st.expander(
                f"🔩 **{tracker['product_name']}** — {product_type} | Qty: {tracker.get('quantity', 1)} ({tracker.get('product_id', '')})",
                expanded=True,
            ):
                # Progress bar
                render_production_progress(stage_dict, stages)

                st.markdown("")

                # Stage grid
                cols_per_row = 4
                stage_list = list(stages)

                for row_start in range(0, len(stage_list), cols_per_row):
                    cols = st.columns(cols_per_row)
                    for col_idx, (stage_name, statuses) in enumerate(stage_list[row_start:row_start + cols_per_row]):
                        with cols[col_idx]:
                            current_status = stage_dict.get(stage_name, statuses[0])
                            color = production_stage_color(current_status)

                            st.markdown(f"""
                            <div style="border:2px solid {color};border-radius:10px;padding:10px;margin:4px 0;
                                 background:#ffffff;min-height:100px;box-shadow:0 1px 2px rgba(0,0,0,0.05)">
                                <div style="font-size:0.75rem;font-weight:700;color:#334155;text-transform:uppercase;
                                     letter-spacing:0.5px">{stage_name}</div>
                                <div style="font-size:0.85rem;font-weight:700;color:{color};margin-top:4px">
                                    ● {current_status}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

                            new_status = st.selectbox(
                                f"Update",
                                statuses,
                                index=statuses.index(current_status) if current_status in statuses else 0,
                                key=f"stg_{tracker['product_id']}_{stage_name}",
                                label_visibility="collapsed",
                            )

                            if new_status != current_status:
                                if st.button("Save", key=f"save_stg_{tracker['product_id']}_{stage_name}"):
                                    update_production_stage(
                                        project["project_id"], tracker["product_id"],
                                        stage_name, new_status,
                                    )
                                    st.success(f"{stage_name} → {new_status}")
                                    st.rerun()
