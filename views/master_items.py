"""Master Items — Central catalog. Auto-creates vendors when new names are entered."""
import streamlit as st
import pandas as pd
from utils.db import (get_all_master_items, add_master_item, update_master_item,
                       delete_master_item, ensure_vendor_exists, get_all_vendors)
from utils.ui_helpers import section_header, empty_state, styled_metric
from config import MATERIAL_CATEGORIES, UNITS_OF_MEASURE


def render():
    st.markdown("# 📦 Master Items Catalog")
    st.markdown("*Central table of all materials, components, and services. Vendor is auto-created if new.*")
    st.markdown("---")

    tab_all, tab_add = st.tabs(["📋 All Master Items", "➕ Add Item"])

    with tab_add:
        section_header("Add New Master Item", "➕")
        existing_vendors = sorted(set(v.get("name", "") for v in get_all_vendors()))
        all_items = get_all_master_items()
        existing_categories = sorted(set(i.get("category", "") for i in all_items if i.get("category")))
        existing_sub_categories = sorted(set(i.get("sub_category", "") for i in all_items if i.get("sub_category")))

        with st.form("add_master_item", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                item_name = st.text_input("Item Name *", placeholder="e.g., MS Sheet 2mm")
                vendor = st.text_input("Vendor Name *", placeholder="Type vendor name — auto-created if new")
                if existing_vendors:
                    st.caption(f"Existing vendors: {', '.join(existing_vendors[:10])}{'...' if len(existing_vendors) > 10 else ''}")
                category = st.text_input("Category *", placeholder="e.g., Mild Steel, Components, Consumables")
                if existing_categories:
                    st.caption(f"Existing: {', '.join(existing_categories[:10])}")
                sub_category = st.text_input("Sub-Category *", placeholder="e.g., Sheet, Sensor, Welding Spool")
                if existing_sub_categories:
                    st.caption(f"Existing: {', '.join(existing_sub_categories[:15])}")
            with c2:
                specification = st.text_input("Specification", placeholder="e.g., 2mm x 1250mm x 2500mm")
                unit = st.selectbox("Unit", UNITS_OF_MEASURE)
                location = st.text_input("Default Location", value="Main Store")
                price = st.number_input("Price (₹)", min_value=0.0, step=0.5)
                revised_price = st.number_input("Revised Price (₹)", min_value=0.0, step=0.5)
            remarks = st.text_input("Remarks")

            if st.form_submit_button("✅ Add Master Item", use_container_width=True):
                if item_name and vendor and category and sub_category:
                    ensure_vendor_exists(vendor.strip())
                    r = add_master_item(item_name, vendor.strip(), category.strip(), sub_category.strip(),
                                        specification, unit, location, price, revised_price, remarks)
                    st.success(f"Added **{item_name}** (Vendor: {vendor}) — ID: `{r['item_id']}`")
                    st.rerun()
                else:
                    st.error("Item Name, Vendor, Category, and Sub-Category are required.")

    with tab_all:
        items = get_all_master_items()
        if not items:
            empty_state("📦", "No master items yet", "Add items or use Bulk Upload")
            return

        c1, c2, c3 = st.columns(3)
        with c1: styled_metric("Total Items", len(items), color="#1e40af")
        with c2: styled_metric("Vendors", len(set(i.get("vendor", "") for i in items)), color="#7c3aed")
        with c3: styled_metric("Categories", len(set(i.get("category", "") for i in items)), color="#0e7490")

        st.markdown("")
        fc1, fc2, fc3 = st.columns(3)
        with fc1: search = st.text_input("🔍 Search", placeholder="Name, spec, vendor...", key="mi_search")
        with fc2: cat_filter = st.selectbox("Category", ["All"] + sorted(set(i.get("category", "") for i in items)), key="mi_cat")
        with fc3: ven_filter = st.selectbox("Vendor", ["All"] + sorted(set(i.get("vendor", "") for i in items)), key="mi_ven")

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
            st.dataframe(df[available], use_container_width=True, hide_index=True, height=400)
            st.caption(f"Showing {len(filtered)} of {len(items)} items")

        st.markdown("---")
        st.markdown("#### ✏️ Edit or 🗑️ Delete Item")
        item_opts = {f"{i['item_name']} | {i.get('vendor','')} | {i.get('specification','')} ({i['item_id']})": i for i in items}
        sel = st.selectbox("Select Item", list(item_opts.keys()), key="mi_edit_sel")
        if sel:
            item = item_opts[sel]
            with st.expander("Edit Item Details"):
                with st.form("edit_mi"):
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        np = st.number_input("Price", value=float(item.get("price", 0)), step=0.5)
                        nrp = st.number_input("Revised Price", value=float(item.get("revised_price", 0)), step=0.5)
                    with ec2:
                        nl = st.text_input("Location", value=item.get("location", ""))
                        nr = st.text_input("Remarks", value=item.get("remarks", ""))
                    if st.form_submit_button("💾 Update"):
                        update_master_item(item["item_id"], {"price": np, "revised_price": nrp, "location": nl, "remarks": nr})
                        st.success("Updated!"); st.rerun()

            col1, col2 = st.columns([3, 1])
            with col1: confirm = st.checkbox("Confirm deletion", key="mi_dc")
            with col2:
                if st.button("🗑️ Delete", disabled=not confirm, key="mi_db"):
                    delete_master_item(item["item_id"]); st.success("Deleted!"); st.rerun()
