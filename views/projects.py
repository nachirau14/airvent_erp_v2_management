"""Projects & BOQ — search master items by name/category/sub_category, auto-fill rate."""
import streamlit as st
import pandas as pd
from utils.db import (create_project, get_all_projects, update_project_status,
                       add_boq_item, get_boq_items, delete_boq_item,
                       get_all_master_items, create_staged_orders_from_boq)
from utils.ui_helpers import section_header, project_status_badge, format_currency, empty_state, styled_metric
from config import PRODUCTION_STAGES, PROJECT_STATUSES


def render():
    st.markdown("# 📋 Projects & BOQ")
    st.markdown("*Build BOQs from master catalog — search by name, category, or sub-category*")
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
            empty_state("📋", "No projects yet"); return

        c1, c2, c3 = st.columns(3)
        with c1: styled_metric("Total", len(projects), color="#1e40af")
        with c2: styled_metric("Active", len([p for p in projects if p.get("status") not in ("Complete", "Dispatched")]), color="#7c3aed")
        with c3: styled_metric("Complete", len([p for p in projects if p.get("status") in ("Complete", "Dispatched")]), color="#16a34a")

        st.markdown("")
        status_filter = st.multiselect("Filter by Status", PROJECT_STATUSES)
        filtered = projects if not status_filter else [p for p in projects if p.get("status") in status_filter]

        master_items = get_all_master_items()

        for proj in sorted(filtered, key=lambda x: x.get("created_at", ""), reverse=True):
            pid = proj["project_id"]
            with st.expander(f"**{proj['name']}** — {proj.get('client_name', '')} ({pid})"):
                hc1, hc2, hc3 = st.columns([2, 1, 1])
                with hc1:
                    st.markdown(f"**Type:** {proj.get('product_type', '')} | {proj.get('description', '')}")
                with hc2:
                    st.markdown(project_status_badge(proj.get("status", "Planning")), unsafe_allow_html=True)
                with hc3:
                    new_status = st.selectbox("Status", PROJECT_STATUSES,
                        index=PROJECT_STATUSES.index(proj.get("status", "Planning")), key=f"s_{pid}")
                    if st.button("Update", key=f"su_{pid}"):
                        update_project_status(pid, new_status); st.rerun()

                st.markdown("---")
                st.markdown("### 📝 Bill of Quantities")

                boq = get_boq_items(pid)
                if boq:
                    total = sum(i.get("total", 0) for i in boq)
                    st.markdown(f"**{len(boq)} items** | **Estimated: {format_currency(total)}**")
                    df = pd.DataFrame(boq)
                    cols = ["item_id", "item_name", "vendor", "category", "specification", "quantity", "unit", "rate", "total"]
                    available = [c for c in cols if c in df.columns]
                    if available:
                        st.dataframe(df[available], use_container_width=True, hide_index=True)

                    del_opts = [f"{i['item_id']} — {i.get('item_name', '')}" for i in boq]
                    del_sel = st.selectbox("Delete item", [""] + del_opts, key=f"db_{pid}")
                    if del_sel and st.button("🗑️ Delete", key=f"dbb_{pid}"):
                        delete_boq_item(pid, del_sel.split(" — ")[0]); st.rerun()

                    st.markdown("---")
                    if st.button("🚀 Stage Purchase Orders from BOQ", key=f"stg_{pid}", type="primary", use_container_width=True):
                        staged = create_staged_orders_from_boq(pid)
                        st.success(f"Created **{len(staged)}** staged POs. Go to 🚀 Order Staging to review.")
                        st.rerun()
                else:
                    st.info("No BOQ items. Add from master catalog below.")

                # ─── Add BOQ from master items with search ────────
                st.markdown("#### ➕ Add BOQ Item from Master Catalog")
                if not master_items:
                    st.warning("No master items. Add items in Master Items page first."); continue

                # Search by name, category, sub_category
                search = st.text_input("🔍 Search by name, category, or sub-category", key=f"ms_{pid}")

                mi_filtered = master_items
                if search:
                    s = search.lower()
                    mi_filtered = [m for m in master_items if
                        s in m.get("item_name", "").lower() or
                        s in m.get("category", "").lower() or
                        s in m.get("sub_category", "").lower() or
                        s in m.get("specification", "").lower() or
                        s in m.get("vendor", "").lower()]

                mi_opts = {f"{m['item_name']} | {m.get('vendor','')} | {m.get('category','')} > {m.get('sub_category','')} | {m.get('specification','')} — ₹{m.get('revised_price',0) or m.get('price',0)} ({m['item_id']})": m
                           for m in mi_filtered[:200]}

                if not mi_opts:
                    st.caption("No items match your search.")
                    continue

                sel_mi_key = st.selectbox("Select Master Item", list(mi_opts.keys()), key=f"mi_{pid}")
                sel_mi = mi_opts.get(sel_mi_key, {})

                # Auto-fill rate from master item
                default_rate = float(sel_mi.get("revised_price", 0) or sel_mi.get("price", 0))

                with st.form(f"boq_{pid}", clear_on_submit=True):
                    bc1, bc2 = st.columns(2)
                    with bc1:
                        qty = st.number_input("Quantity *", min_value=1, value=1, step=1, key=f"bq_{pid}")
                    with bc2:
                        rate = st.number_input("Rate (₹)", min_value=0.0, value=default_rate, step=0.5, key=f"br_{pid}")

                    if st.form_submit_button("➕ Add to BOQ"):
                        if sel_mi and qty > 0:
                            add_boq_item(pid, sel_mi["item_id"], sel_mi["item_name"],
                                sel_mi.get("vendor", ""), sel_mi.get("category", ""),
                                sel_mi.get("sub_category", ""), sel_mi.get("specification", ""),
                                qty, sel_mi.get("unit", "Nos"), rate)
                            st.success(f"Added **{sel_mi['item_name']}** × {qty} to BOQ")
                            st.rerun()
