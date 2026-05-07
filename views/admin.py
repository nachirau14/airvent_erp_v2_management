"""Admin — Company config, logo upload, bulk delete."""
import streamlit as st
from utils.db import (bulk_delete_table_data, reset_counter, _scan_all,
                       _get_company_config, save_company_config, upload_company_logo, _get_logo_bytes)
from utils.ui_helpers import section_header, styled_metric
from config import TABLES


TABLE_LABELS = {
    "master_items": "📦 Master Items",
    "projects": "📋 Projects",
    "boq_items": "📝 BOQ Items",
    "inventory": "📦 Inventory",
    "vendors": "👥 Vendors",
    "service_vendors": "🔧 Service Vendors",
    "service_vendor_services": "🛠️ Service Vendor Services",
    "raw_material_po": "📦 Material Purchase Orders",
    "raw_material_po_items": "📦 Material PO Line Items",
    "service_po": "🛠️ Service Purchase Orders",
    "service_po_items": "🛠️ Service PO Line Items",
    "production_tracking": "🏗️ Production Tracking",
    "finished_goods": "✅ Finished Goods",
    "dispatched_goods": "🚚 Dispatched Goods",
    "material_issues": "📦 Material Issues",
    "order_staging": "🚀 Order Staging",
    "email_config": "📧 Email Config",
    "scrap_inventory": "♻️ Scrap Inventory",
    "company_config": "🏢 Company Config",
}


def render():
    st.markdown("# 🛡️ Admin")
    st.markdown("*Company setup, logo, and data management*")
    st.markdown("---")

    tab_company, tab_delete, tab_counters = st.tabs(["🏢 Company Config", "🗑️ Bulk Delete", "🔄 Counters"])

    # ─── Company Config ───────────────────────────────────────
    with tab_company:
        section_header("Company Configuration", "🏢")
        st.markdown("*These details appear on all POs, Service POs, and Delivery Challans*")

        config = _get_company_config()

        with st.form("company_config"):
            c1, c2 = st.columns(2)
            with c1:
                company_name = st.text_input("Company Name *", value=config.get("company_name", ""))
                gstin = st.text_input("GSTIN *", value=config.get("gstin", ""))
            with c2:
                address = st.text_area("Registered Address *", value=config.get("address", ""), height=80)
                shipping_address = st.text_area("Shipping Address", value=config.get("shipping_address", ""), height=80)

            if st.form_submit_button("💾 Save Company Details", use_container_width=True):
                save_company_config({
                    "company_name": company_name, "gstin": gstin,
                    "address": address, "shipping_address": shipping_address,
                    "logo_s3_key": config.get("logo_s3_key", ""),
                })
                st.success("Company details saved!")
                st.rerun()

        st.markdown("---")
        section_header("Company Logo", "🖼️")
        st.markdown("*Upload your company logo (PNG/JPG). It will appear on all generated PDFs.*")

        # Show current logo
        logo_bytes = _get_logo_bytes()
        if logo_bytes:
            st.image(logo_bytes, width=200, caption="Current logo")
        else:
            st.info("No logo uploaded yet.")

        logo_file = st.file_uploader("Upload logo (PNG or JPG)", type=["png", "jpg", "jpeg"], key="logo_upload")
        if logo_file:
            if st.button("📤 Upload Logo", type="primary"):
                result = upload_company_logo(logo_file.read(), logo_file.name)
                if result:
                    st.success("Logo uploaded!")
                    st.rerun()
                else:
                    st.error("Upload failed")

    # ─── Bulk Delete ──────────────────────────────────────────
    with tab_delete:

    section_header("Table Status", "📊")

    # Show record counts
    table_counts = {}
    for key, table_name in TABLES.items():
        if key in TABLE_LABELS:
            try:
                items = _scan_all(table_name)
                table_counts[key] = len(items)
            except Exception:
                table_counts[key] = "?"

    cols = st.columns(4)
    for idx, (key, label) in enumerate(TABLE_LABELS.items()):
        count = table_counts.get(key, "?")
        with cols[idx % 4]:
            st.markdown(f"""
            <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;margin:4px 0;text-align:center">
                <div style="font-size:0.75rem;color:#64748b">{label}</div>
                <div style="font-size:1.2rem;font-weight:700;color:#0f172a">{count}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # Individual table delete
    section_header("Delete Individual Table", "🗑️")

    sel_table = st.selectbox("Select Table", list(TABLE_LABELS.keys()),
                              format_func=lambda x: f"{TABLE_LABELS[x]} ({table_counts.get(x, '?')} records)")

    if sel_table:
        count = table_counts.get(sel_table, 0)
        st.markdown(f"""
        <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px;margin:12px 0">
            <div style="color:#991b1b;font-weight:700;font-size:1rem">⚠️ Delete ALL {count} records from {TABLE_LABELS[sel_table]}</div>
            <div style="color:#7f1d1d;font-size:0.85rem;margin-top:4px">This action cannot be undone.</div>
        </div>""", unsafe_allow_html=True)

        confirm = st.checkbox(f"I confirm I want to delete all data from {TABLE_LABELS[sel_table]}", key="del_confirm")
        if st.button("🗑️ Delete All Records", disabled=not confirm, type="primary", key="del_single"):
            with st.spinner(f"Deleting {count} records..."):
                deleted = bulk_delete_table_data(sel_table)
            st.success(f"Deleted **{deleted}** records from {TABLE_LABELS[sel_table]}")
            st.rerun()

    st.markdown("---")

    # Delete ALL tables
    section_header("Delete ALL Data", "💣")
    st.markdown("Delete all records from **every table** at once. For a complete fresh start.")

    total_records = sum(v for v in table_counts.values() if isinstance(v, int))
    st.markdown(f"**Total records across all tables: {total_records}**")

    confirm_all = st.checkbox("I understand this will delete ALL data from ALL tables and cannot be undone", key="del_all_confirm")
    confirm_text = st.text_input("Type DELETE to confirm", key="del_all_text")

    if st.button("💣 DELETE EVERYTHING", disabled=not (confirm_all and confirm_text == "DELETE"),
                  type="primary", key="del_all"):
        with st.spinner("Deleting all data..."):
            total_deleted = 0
            for key in TABLE_LABELS:
                deleted = bulk_delete_table_data(key)
                total_deleted += deleted
                st.caption(f"  Deleted {deleted} from {TABLE_LABELS[key]}")
        st.success(f"Deleted **{total_deleted}** total records across all tables")
        st.rerun()

    st.markdown("---")

    # Reset counters
    # ─── Counters ──────────────────────────────────────────────
    with tab_counters:
        section_header("Reset Sequential Counters", "🔄")
    st.markdown("Reset MI/RMPO/SPO counters back to 0. New items will start from 0001 again.")

    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        if st.button("Reset MI counter", use_container_width=True):
            reset_counter("MI"); st.success("MI counter reset to 0")
    with rc2:
        if st.button("Reset RMPO counters", use_container_width=True):
            # Reset all FY counters we can find
            from utils.db import _financial_year_prefix
            fy = _financial_year_prefix()
            reset_counter(f"RMPO-FY{fy}")
            st.success(f"RMPO FY{fy} counter reset to 0")
    with rc3:
        if st.button("Reset SPO counters", use_container_width=True):
            from utils.db import _financial_year_prefix
            fy = _financial_year_prefix()
            reset_counter(f"SPO-FY{fy}")
            st.success(f"SPO FY{fy} counter reset to 0")
