"""Master Items — Central catalog of all products/services."""
import streamlit as st
import pandas as pd
from utils.db import get_all_master_items, add_master_item, update_master_item, delete_master_item
from utils.ui_helpers import section_header, empty_state, styled_metric
from config import MATERIAL_CATEGORIES, UNITS_OF_MEASURE


def render():
    st.markdown("# 📦 Master Items Catalog")
    st.markdown("*Central table of all raw materials, components, and services with vendor linkage*")
    st.markdown("---")

    tab_all, tab_add = st.tabs(["📋 All Master Items", "➕ Add Item"])

    with tab_add:
        section_header("Add New Master Item", "➕")
        with st.form("add_master_item", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                item_name = st.text_input("Item Name *", placeholder="e.g., MS Sheet 2mm")
                vendor = st.text_input("Vendor Name *", placeholder="e.g., Tata Steel Distributors")
                category = st.selectbox("Category", list(MATERIAL_CATEGORIES.keys()))
                sub_category = st.selectbox("Sub-Category", MATERIAL_CATEGORIES.get(category, ["Custom"]))
            with c2:
                specification = st.text_input("Specification", placeholder="e.g., 2mm x 1250mm x 2500mm")
                unit = st.selectbox("Unit", UNITS_OF_MEASURE)
                location = st.text_input("Default Location", value="Main Store")
                price = st.number_input("Price (₹)", min_value=0.0, step=0.5)
                revised_price = st.number_input("Revised Price (₹)", min_value=0.0, step=0.5)
            remarks = st.text_input("Remarks", placeholder="Any notes...")

            if st.form_submit_button("✅ Add Master Item", use_container_width=True):
                if item_name and vendor:
                    r = add_master_item(item_name, vendor, category, sub_category, specification, unit, location, price, revised_price, remarks)
                    st.success(f"Added **{item_name}** — ID: `{r['item_id']}`")
                    st.rerun()
                else:
                    st.error("Item Name and Vendor are required.")

    with tab_all:
        items = get_all_master_items()
        if not items:
            empty_state("📦", "No master items yet", "Add items or use Bulk Upload")
            return

        c1, c2, c3 = st.columns(3)
        with c1:
            styled_metric("Total Items", len(items), color="#1e40af")
        with c2:
            vendors = set(i.get("vendor", "") for i in items)
            styled_metric("Vendors", len(vendors), color="#7c3aed")
        with c3:
            cats = set(i.get("category", "") for i in items)
            styled_metric("Categories", len(cats), color="#0e7490")

        st.markdown("")

        # Filters
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            search = st.text_input("🔍 Search", placeholder="Name, spec, vendor...", key="mi_search")
        with fc2:
            cat_filter = st.selectbox("Category", ["All"] + sorted(cats), key="mi_cat")
        with fc3:
            ven_filter = st.selectbox("Vendor", ["All"] + sorted(vendors), key="mi_ven")

        filtered = items
        if search:
            s = search.lower()
            filtered = [i for i in filtered if s in i.get("item_name", "").lower() or s in i.get("specification", "").lower() or s in i.get("vendor", "").lower()]
        if cat_filter != "All":
            filtered = [i for i in filtered if i.get("category") == cat_filter]
        if ven_filter != "All":
            filtered = [i for i in filtered if i.get("vendor") == ven_filter]

        if filtered:
            df = pd.DataFrame(filtered)
            cols = ["item_id", "item_name", "vendor", "category", "sub_category", "specification", "unit", "location", "price", "revised_price", "remarks"]
            available = [c for c in cols if c in df.columns]
            display_df = df[available].copy()
            display_df.columns = [c.replace("_", " ").title() for c in available]
            st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
            st.caption(f"Showing {len(filtered)} of {len(items)} items")

        # Edit / Delete
        st.markdown("---")
        st.markdown("#### ✏️ Edit or 🗑️ Delete Item")
        item_opts = {f"{i['item_name']} | {i.get('vendor','')} | {i.get('specification','')} ({i['item_id']})": i for i in items}
        sel = st.selectbox("Select Item", list(item_opts.keys()), key="mi_edit_sel")

        if sel:
            item = item_opts[sel]
            with st.expander("Edit Item Details", expanded=False):
                with st.form("edit_master_item"):
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        new_price = st.number_input("Price", value=float(item.get("price", 0)), step=0.5, key="mi_ep")
                        new_revised = st.number_input("Revised Price", value=float(item.get("revised_price", 0)), step=0.5, key="mi_erp")
                    with ec2:
                        new_location = st.text_input("Location", value=item.get("location", ""), key="mi_el")
                        new_remarks = st.text_input("Remarks", value=item.get("remarks", ""), key="mi_er")
                    if st.form_submit_button("💾 Update"):
                        update_master_item(item["item_id"], {"price": new_price, "revised_price": new_revised, "location": new_location, "remarks": new_remarks})
                        st.success("Updated!")
                        st.rerun()

            st.markdown("")
            st.markdown(f"""
            <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:12px;margin:8px 0">
                <div style="color:#991b1b;font-weight:600">⚠️ Delete: {item['item_name']} — {item.get('vendor','')}</div>
            </div>""", unsafe_allow_html=True)
            col1, col2 = st.columns([3, 1])
            with col1:
                confirm = st.checkbox("I confirm deletion", key="mi_del_confirm")
            with col2:
                if st.button("🗑️ Delete", disabled=not confirm, key="mi_del_btn"):
                    delete_master_item(item["item_id"])
                    st.success("Deleted!")
                    st.rerun()
