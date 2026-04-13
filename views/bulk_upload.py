"""Bulk Upload — master items and inventory via CSV/Excel."""
import streamlit as st
import pandas as pd
from utils.db import bulk_upload_master_items, add_inventory_item, get_all_master_items
from utils.ui_helpers import section_header, empty_state


def render():
    st.markdown("# 📤 Bulk Upload")
    st.markdown("*Upload master items or inventory via CSV / Excel*")
    st.markdown("---")

    tab_master, tab_inv, tab_template = st.tabs(["📦 Master Items", "🏗️ Inventory", "📋 Templates"])

    with tab_template:
        section_header("Download Templates", "📋")

        master_template = pd.DataFrame({
            "item_name": ["MS Sheet 2mm", "SS304 Angle 25x25x3", "Proximity Sensor NPN"],
            "vendor": ["Tata Steel", "Jindal Stainless", "Electro Components"],
            "category": ["Mild Steel", "Stainless Steel 304", "Components"],
            "sub_category": ["Sheet", "Angle", "Sensor"],
            "specification": ["2mm x 1250mm x 2500mm", "25x25x3mm x 6m", "NPN, NO, 10mm"],
            "unit": ["Kg", "Kg", "Nos"],
            "location": ["Main Store", "Main Store", "Electrical Store"],
            "price": [72.0, 250.0, 850.0],
            "revised_price": [74.0, 255.0, 850.0],
            "remarks": ["", "", "Omron brand"],
        })
        st.download_button("⬇️ Master Items Template (CSV)", master_template.to_csv(index=False),
                           "master_items_template.csv", "text/csv")

        st.markdown("")

        inv_template = pd.DataFrame({
            "master_item_id": ["MI-abc123", "MI-def456"],
            "quantity": [50, 20],
            "location": ["Main Store", "Tool Store"],
            "remarks": ["Opening stock", ""],
        })
        st.download_button("⬇️ Inventory Template (CSV)", inv_template.to_csv(index=False),
                           "inventory_template.csv", "text/csv")

    with tab_master:
        section_header("Upload Master Items", "📦")
        st.info("Required columns: item_name, vendor, category, sub_category, specification, unit, location, price. Optional: revised_price, remarks")

        uploaded = st.file_uploader("Choose CSV or Excel", type=["csv", "xlsx", "xls"], key="mi_upload")
        if uploaded:
            try:
                df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
                st.markdown("#### Preview")
                st.dataframe(df.head(20), use_container_width=True, hide_index=True)
                st.caption(f"Total rows: {len(df)}")

                required = ["item_name", "vendor", "category", "sub_category", "specification", "unit", "price"]
                missing = [c for c in required if c not in df.columns]
                if missing:
                    st.error(f"Missing columns: {', '.join(missing)}")
                    return

                if st.button(f"✅ Upload {len(df)} Master Items", type="primary", use_container_width=True):
                    items = df.fillna("").to_dict("records")
                    with st.spinner(f"Uploading {len(items)} items to DynamoDB..."):
                        results = bulk_upload_master_items(items)
                    st.success(f"Uploaded **{len(results)}** master items!")
                    st.balloons()
            except Exception as e:
                st.error(f"Error: {e}")

    with tab_inv:
        section_header("Upload Inventory from Master Items", "🏗️")
        st.info("Required columns: master_item_id, quantity. Optional: location, remarks")

        master_items = get_all_master_items()
        mi_lookup = {m["item_id"]: m for m in master_items}

        uploaded = st.file_uploader("Choose CSV or Excel", type=["csv", "xlsx", "xls"], key="inv_upload")
        if uploaded:
            try:
                df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
                st.dataframe(df.head(20), use_container_width=True, hide_index=True)

                if "master_item_id" not in df.columns or "quantity" not in df.columns:
                    st.error("Need columns: master_item_id, quantity")
                    return

                if st.button(f"✅ Upload {len(df)} Inventory Items", type="primary", use_container_width=True):
                    count = 0
                    for _, row in df.iterrows():
                        mid = row["master_item_id"]
                        mi = mi_lookup.get(mid)
                        if mi:
                            add_inventory_item(mid, mi["item_name"], mi.get("vendor", ""),
                                mi.get("category", ""), mi.get("sub_category", ""),
                                mi.get("specification", ""), float(row["quantity"]),
                                mi.get("unit", "Nos"), row.get("location", mi.get("location", "Main Store")),
                                mi.get("price", 0), row.get("remarks", ""))
                            count += 1
                    st.success(f"Added **{count}** items to inventory!")
                    st.balloons()
            except Exception as e:
                st.error(f"Error: {e}")
