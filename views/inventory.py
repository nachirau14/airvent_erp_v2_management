"""Inventory — linked to master items catalog."""
import streamlit as st
import pandas as pd
from utils.db import (get_all_inventory, add_inventory_item, update_inventory_qty,
                       delete_inventory_item, get_all_master_items)
from utils.ui_helpers import section_header, empty_state, styled_metric
from config import MATERIAL_CATEGORIES, UNITS_OF_MEASURE


def render():
    st.markdown("# 📦 Inventory Management")
    st.markdown("*Track stock on hand — add from master item catalog*")
    st.markdown("---")

    tab_view, tab_add = st.tabs(["📋 Current Stock", "➕ Add Stock"])

    with tab_view:
        section_header("Inventory On Hand", "📦")
        inventory = get_all_inventory()

        if not inventory:
            empty_state("📦", "No inventory items", "Add stock from the master catalog in the 'Add Stock' tab")
            return

        c1, c2, c3, c4 = st.columns(4)
        with c1: styled_metric("Total Items", len(inventory), color="#1e40af")
        with c2: styled_metric("Categories", len(set(i.get("category", "") for i in inventory)), color="#7c3aed")
        with c3: styled_metric("Vendors", len(set(i.get("vendor", "") for i in inventory)), color="#0e7490")
        with c4: styled_metric("Out of Stock", len([i for i in inventory if i.get("quantity", 0) <= 0]), color="#dc2626")

        st.markdown("")

        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            search = st.text_input("🔍 Search", key="inv_search")
        with fc2:
            cat_filter = st.selectbox("Category", ["All"] + sorted(set(i.get("category", "") for i in inventory)), key="inv_cat")
        with fc3:
            ven_filter = st.selectbox("Vendor", ["All"] + sorted(set(i.get("vendor", "") for i in inventory)), key="inv_ven")

        filtered = inventory
        if search:
            s = search.lower()
            filtered = [i for i in filtered if s in i.get("item_name", "").lower() or s in i.get("specification", "").lower()]
        if cat_filter != "All":
            filtered = [i for i in filtered if i.get("category") == cat_filter]
        if ven_filter != "All":
            filtered = [i for i in filtered if i.get("vendor") == ven_filter]

        if filtered:
            df = pd.DataFrame(filtered)
            cols = ["item_id", "item_name", "vendor", "category", "sub_category", "specification", "quantity", "unit", "location", "price"]
            available = [c for c in cols if c in df.columns]
            display_df = df[available].copy()
            display_df.columns = [c.replace("_", " ").title() for c in available]

            def highlight(row):
                qty = row.get("Quantity", 0)
                if qty <= 0: return ["background-color: #fee2e2"] * len(row)
                elif qty < 10: return ["background-color: #fef3c7"] * len(row)
                return [""] * len(row)

            st.dataframe(display_df.style.apply(highlight, axis=1), use_container_width=True, hide_index=True, height=400)

        # Adjust stock
        st.markdown("#### 🔄 Adjust Stock")
        item_opts = {f"{i['item_name']} | {i.get('vendor','')} ({i['item_id']})": i for i in inventory}
        sel = st.selectbox("Select Item", list(item_opts.keys()), key="inv_adj_sel")
        ac1, ac2 = st.columns(2)
        with ac1:
            adj = st.number_input("Quantity (+/-)", step=1.0, key="inv_adj_qty")
        with ac2:
            if st.button("Apply", key="inv_adj_btn"):
                update_inventory_qty(item_opts[sel]["item_id"], adj)
                st.success("Adjusted!")
                st.rerun()

        # Delete
        st.markdown("---")
        st.markdown("#### 🗑️ Delete Inventory Item")
        del_opts = {f"{i['item_name']} | {i.get('vendor','')} | Qty: {i.get('quantity',0)} ({i['item_id']})": i for i in inventory}
        del_sel = st.selectbox("Select item to delete", list(del_opts.keys()), key="inv_del_sel")
        col1, col2 = st.columns([3, 1])
        with col1:
            confirm = st.checkbox("Confirm deletion", key="inv_del_conf")
        with col2:
            if st.button("🗑️ Delete", disabled=not confirm, key="inv_del_btn"):
                delete_inventory_item(del_opts[del_sel]["item_id"])
                st.success("Deleted!")
                st.rerun()

    with tab_add:
        section_header("Add Stock from Master Catalog", "➕")
        master_items = get_all_master_items()
        if not master_items:
            st.warning("No master items. Add items in the Master Items page first.")
            return

        search_mi = st.text_input("🔍 Search master items", key="inv_mi_search")
        mi_filtered = master_items
        if search_mi:
            s = search_mi.lower()
            mi_filtered = [m for m in mi_filtered if s in m.get("item_name", "").lower() or s in m.get("vendor", "").lower() or s in m.get("specification", "").lower()]

        mi_opts = {f"{m['item_name']} | {m.get('vendor','')} | {m.get('specification','')} ({m['item_id']})": m for m in mi_filtered[:100]}

        with st.form("add_inv_from_master", clear_on_submit=True):
            sel_mi = st.selectbox("Select Master Item *", list(mi_opts.keys()), key="inv_add_mi")
            c1, c2, c3 = st.columns(3)
            with c1:
                qty = st.number_input("Quantity *", min_value=0.0, step=1.0, key="inv_add_qty")
            with c2:
                location = st.text_input("Location", value="Main Store", key="inv_add_loc")
            with c3:
                remarks = st.text_input("Remarks", key="inv_add_rem")

            if st.form_submit_button("✅ Add to Inventory", use_container_width=True):
                if sel_mi and qty > 0:
                    mi = mi_opts[sel_mi]
                    add_inventory_item(mi["item_id"], mi["item_name"], mi.get("vendor", ""),
                                       mi.get("category", ""), mi.get("sub_category", ""),
                                       mi.get("specification", ""), qty, mi.get("unit", "Nos"),
                                       location, mi.get("price", 0), remarks)
                    st.success(f"Added **{mi['item_name']}** × {qty} to inventory")
                    st.rerun()
                else:
                    st.error("Select an item and enter quantity.")
