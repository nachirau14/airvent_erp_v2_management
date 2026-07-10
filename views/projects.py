"""Projects & BOQ — search master items, vendor dropdown with 'Add New' option."""
import streamlit as st
import pandas as pd
from utils.db import (create_project, get_all_projects, update_project_status,
                       add_boq_item, get_boq_items, delete_boq_item,
                       get_all_master_items, create_staged_orders_from_boq,
                       get_all_vendors, get_all_service_vendors, add_vendor)
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
                    staged_count = sum(1 for i in boq if i.get("staged", False))
                    unstaged_count = len(boq) - staged_count

                    sc1, sc2, sc3 = st.columns(3)
                    with sc1:
                        st.markdown(f"**{len(boq)} total items** | **{format_currency(total)}**")
                    with sc2:
                        if staged_count:
                            st.markdown(f"✅ **{staged_count}** staged/ordered")
                    with sc3:
                        if unstaged_count:
                            st.markdown(f"🆕 **{unstaged_count}** new (not yet staged)")

                    # Add staged column to display
                    df = pd.DataFrame(boq)
                    df["status"] = df.apply(lambda r: "✅ Staged" if r.get("staged", False) else "🆕 New", axis=1)
                    cols = ["item_id", "item_name", "vendor", "category", "specification", "quantity", "unit", "rate", "total", "status"]
                    available = [c for c in cols if c in df.columns]
                    if available:
                        def highlight_staged(row):
                            if row.get("status") == "✅ Staged":
                                return ["background-color: #f0fdf4"] * len(row)
                            return ["background-color: #eff6ff"] * len(row)
                        st.dataframe(df[available].style.apply(highlight_staged, axis=1),
                                     use_container_width=True, hide_index=True)

                    del_opts = [f"{i['item_id']} — {i.get('item_name', '')}" for i in boq]
                    del_sel = st.selectbox("Delete item", [""] + del_opts, key=f"db_{pid}")
                    if del_sel and st.button("🗑️ Delete", key=f"dbb_{pid}"):
                        delete_boq_item(pid, del_sel.split(" — ")[0]); st.rerun()

                    st.markdown("---")
                    if unstaged_count > 0:
                        if st.button(f"🚀 Stage {unstaged_count} New Item(s) for Purchase Orders",
                                     key=f"stg_{pid}", type="primary", use_container_width=True):
                            staged = create_staged_orders_from_boq(pid)
                            if staged:
                                st.success(f"Staged **{len(staged)}** vendor PO(s) from **{unstaged_count}** new items. Go to 🚀 Order Staging to review.")
                            else:
                                st.info("No new items to stage.")
                            st.rerun()
                    else:
                        st.success("All BOQ items have been staged. Add more items below if needed.")
                else:
                    st.info("No BOQ items. Add from master catalog below.")

                # ─── Add BOQ from master items with search + filters ────
                st.markdown("#### ➕ Add BOQ Item from Master Catalog")
                if not master_items:
                    st.warning("No master items. Add items in Master Items page first."); continue

                all_cats = sorted(set(m.get("category", "") for m in master_items if m.get("category")))

                # Vendor dropdown from registered vendors
                all_vendors = get_all_vendors()
                all_svc_vendors = get_all_service_vendors()
                vendor_names = sorted(set(v.get("name", "") for v in all_vendors if v.get("name")))
                svc_vendor_names = sorted(set(v.get("name", "") for v in all_svc_vendors if v.get("name")))
                combined_vendors = sorted(set(vendor_names + svc_vendor_names))
                vendor_options = ["All"] + combined_vendors + ["➕ Add New Vendor..."]

                fc1, fc2, fc3, fc4 = st.columns([2, 1, 1, 1])
                with fc1:
                    search = st.text_input("🔍 Search by name or spec", key=f"ms_{pid}")
                with fc2:
                    ven_filter = st.selectbox("Vendor", vendor_options, key=f"mv_{pid}")
                with fc3:
                    cat_filter = st.selectbox("Category", ["All"] + all_cats, key=f"mc_{pid}")
                with fc4:
                    if cat_filter != "All":
                        filtered_subcats = sorted(set(m.get("sub_category", "") for m in master_items
                                                      if m.get("category") == cat_filter and m.get("sub_category")))
                    else:
                        filtered_subcats = sorted(set(m.get("sub_category", "") for m in master_items if m.get("sub_category")))
                    subcat_filter = st.selectbox("Sub-Category", ["All"] + filtered_subcats, key=f"msc_{pid}")

                # Handle "Add New Vendor"
                if ven_filter == "➕ Add New Vendor...":
                    st.markdown("---")
                    st.markdown("#### 🆕 Register New Vendor First")
                    st.info("Add the vendor details below. Once registered, select them from the dropdown above.")
                    with st.form(f"new_ven_boq_{pid}", clear_on_submit=True):
                        nv1, nv2 = st.columns(2)
                        with nv1:
                            nv_name = st.text_input("Company Name *", key=f"nvn_{pid}")
                            nv_contact = st.text_input("Contact Person *", key=f"nvc_{pid}")
                            nv_phone = st.text_input("Phone *", key=f"nvp_{pid}")
                        with nv2:
                            nv_email = st.text_input("Email", key=f"nve_{pid}")
                            nv_address = st.text_area("Address", height=60, key=f"nva_{pid}")
                            nv_gst = st.text_input("GST Number", key=f"nvg_{pid}")
                        if st.form_submit_button("✅ Register & Continue", use_container_width=True):
                            if nv_name and nv_contact and nv_phone:
                                add_vendor(nv_name, nv_contact, nv_phone, nv_email, nv_address, nv_gst, "Credit - 30 Days")
                                st.success(f"Vendor **{nv_name}** registered! Now select them from the Vendor dropdown.")
                                st.rerun()
                            else:
                                st.error("Company Name, Contact Person, and Phone are required.")
                    continue

                mi_filtered = master_items
                if search:
                    s = search.lower()
                    mi_filtered = [m for m in mi_filtered if
                        s in m.get("item_name", "").lower() or
                        s in m.get("specification", "").lower()]
                if ven_filter != "All":
                    mi_filtered = [m for m in mi_filtered if m.get("vendor", "").lower() == ven_filter.lower()]
                if cat_filter != "All":
                    mi_filtered = [m for m in mi_filtered if m.get("category") == cat_filter]
                if subcat_filter != "All":
                    mi_filtered = [m for m in mi_filtered if m.get("sub_category") == subcat_filter]

                mi_opts = {f"{m['item_name']} | {m.get('vendor','')} | {m.get('category','')} > {m.get('sub_category','')} | {m.get('specification','')} — INR {m.get('revised_price',0) or m.get('price',0)} ({m['item_id']})": m
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
