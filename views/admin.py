"""Admin — Bulk delete for rapid prototyping. Handle with care."""
import streamlit as st
from utils.db import bulk_delete_table_data, reset_counter, _scan_all
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
}


def render():
    st.markdown("# 🛡️ Admin — Bulk Delete")
    st.markdown("*⚠️ Permanently delete all data from selected tables. Use for rapid prototyping only.*")
    st.markdown("---")

    st.error("**WARNING:** Deleting data is irreversible. This will permanently remove ALL records from the selected tables.")

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
