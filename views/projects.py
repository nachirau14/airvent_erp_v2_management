"""Projects & BOQ — linked to master items catalog."""
import streamlit as st
import pandas as pd
from utils.db import (create_project, get_all_projects, update_project_status,
                       add_boq_item, get_boq_items, delete_boq_item, update_boq_item,
                       get_all_master_items, create_staged_orders_from_boq)
from utils.ui_helpers import section_header, project_status_badge, format_currency, empty_state, styled_metric
from config import PRODUCTION_STAGES, PROJECT_STATUSES


def render():
    st.markdown("# 📋 Projects & BOQ")
    st.markdown("*Create projects and build BOQs from the master item catalog*")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📁 All Projects", "➕ New Project"])

    with tab2:
        section_header("Create New Project", "🆕")
        with st.form("new_project_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Project Name *")
                client_name = st.text_input("Client Name *")
            with c2:
                product_type = st.selectbox("Product Type", list(PRODUCTION_STAGES.keys()))
                description = st.text_area("Description", height=80)
            if st.form_submit_button("✅ Create Project", use_container_width=True):
                if name and client_name:
                    proj = create_project(name, client_name, description, product_type)
                    st.success(f"Project **{name}** created! ID: `{proj['project_id']}`")
                    st.rerun()
                else:
                    st.error("Name and Client are required.")

    with tab1:
        projects = get_all_projects()
        if not projects:
            empty_state("📋", "No projects yet")
            return

        c1, c2, c3 = st.columns(3)
        with c1: styled_metric("Total", len(projects), color="#1e40af")
        with c2: styled_metric("Active", len([p for p in projects if p.get("status") not in ("Complete", "Dispatched")]), color="#7c3aed")
        with c3: styled_metric("Complete", len([p for p in projects if p.get("status") in ("Complete", "Dispatched")]), color="#16a34a")

        st.markdown("")
        status_filter = st.multiselect("Filter by Status", PROJECT_STATUSES, default=[])
        filtered = projects if not status_filter else [p for p in projects if p.get("status") in status_filter]

        master_items = get_all_master_items()

        for proj in sorted(filtered, key=lambda x: x.get("created_at", ""), reverse=True):
            with st.expander(f"**{proj['name']}** — {proj.get('client_name', '')} ({proj.get('project_id', '')})"):
                hc1, hc2, hc3 = st.columns([2, 1, 1])
                with hc1:
                    st.markdown(f"**Type:** {proj.get('product_type', '')} | **Description:** {proj.get('description', 'N/A')}")
                with hc2:
                    st.markdown(f"**Status:** {project_status_badge(proj.get('status', 'Planning'))}", unsafe_allow_html=True)
                with hc3:
                    new_status = st.selectbox("Update Status", PROJECT_STATUSES,
                        index=PROJECT_STATUSES.index(proj.get("status", "Planning")), key=f"s_{proj['project_id']}")
                    if st.button("Update", key=f"su_{proj['project_id']}"):
                        update_project_status(proj["project_id"], new_status)
                        st.rerun()

                st.markdown("---")
                st.markdown("### 📝 Bill of Quantities")

                boq = get_boq_items(proj["project_id"])
                if boq:
                    total = sum(i.get("total", 0) for i in boq)
                    st.markdown(f"**{len(boq)} items** | **Estimated: {format_currency(total)}**")
                    df = pd.DataFrame(boq)
                    cols = ["item_id", "item_name", "vendor", "category", "specification", "quantity", "unit", "rate", "total"]
                    available = [c for c in cols if c in df.columns]
                    if available:
                        st.dataframe(df[available], use_container_width=True, hide_index=True)

                    # Delete BOQ item
                    del_opts = [f"{i['item_id']} — {i.get('item_name', '')}" for i in boq]
                    del_sel = st.selectbox("Delete item", [""] + del_opts, key=f"dboq_{proj['project_id']}")
                    if del_sel and st.button("🗑️ Delete", key=f"dbtn_{proj['project_id']}"):
                        delete_boq_item(proj["project_id"], del_sel.split(" — ")[0])
                        st.rerun()

                    # Stage orders from BOQ
                    st.markdown("---")
                    if st.button("🚀 Stage Purchase Orders from BOQ", key=f"stage_{proj['project_id']}", type="primary", use_container_width=True):
                        staged = create_staged_orders_from_boq(proj["project_id"])
                        st.success(f"Created **{len(staged)}** staged POs grouped by vendor. Go to 🚀 Order Staging to review.")
                        st.rerun()
                else:
                    st.info("No BOQ items. Add from master catalog below.")

                # Add BOQ from master items
                st.markdown("#### ➕ Add BOQ Item from Master Catalog")
                if master_items:
                    mi_opts = {f"{m['item_name']} | {m.get('vendor','')} | {m.get('specification','')} — ₹{m.get('price',0)} ({m['item_id']})": m for m in master_items}
                    search = st.text_input("🔍 Search master items", key=f"misearch_{proj['project_id']}")
                    if search:
                        s = search.lower()
                        mi_opts = {k: v for k, v in mi_opts.items() if s in k.lower()}

                    with st.form(f"boq_add_{proj['project_id']}", clear_on_submit=True):
                        sel_mi = st.selectbox("Select Master Item", list(mi_opts.keys()), key=f"mi_sel_{proj['project_id']}")
                        bc1, bc2 = st.columns(2)
                        with bc1:
                            qty = st.number_input("Quantity *", min_value=0.0, step=0.5, key=f"bq_{proj['project_id']}")
                        with bc2:
                            if sel_mi and sel_mi in mi_opts:
                                mi = mi_opts[sel_mi]
                                default_rate = mi.get("revised_price", 0) or mi.get("price", 0)
                            else:
                                default_rate = 0.0
                            rate = st.number_input("Rate (₹)", min_value=0.0, value=float(default_rate), step=0.5, key=f"br_{proj['project_id']}")
                        if st.form_submit_button("➕ Add to BOQ"):
                            if sel_mi and qty > 0:
                                mi = mi_opts[sel_mi]
                                add_boq_item(proj["project_id"], mi["item_id"], mi["item_name"],
                                             mi.get("vendor", ""), mi.get("category", ""), mi.get("sub_category", ""),
                                             mi.get("specification", ""), qty, mi.get("unit", "Nos"), rate)
                                st.success(f"Added **{mi['item_name']}** to BOQ")
                                st.rerun()
                else:
                    st.warning("No master items found. Add items in the Master Items page first.")
