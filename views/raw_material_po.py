"""Purchase Orders — organized by month. Current month visible, older months collapsed."""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from utils.db import (
    get_all_projects, get_all_vendors, get_all_master_items,
    create_raw_material_po, get_all_raw_material_pos,
    get_raw_material_po_items, update_po_item_receipt,
    update_raw_material_po_status, place_po_via_sqs,
    delete_raw_material_po,
    receive_to_inventory,
    generate_po_pdf, update_po_pdf_key, get_po_pdf_download,
    upload_attachment, list_attachments, get_attachment,
)
from utils.ui_helpers import section_header, format_currency, empty_state
from config import PAYMENT_TERMS


def _status_icon(status):
    return {"Draft": "⚪", "Placed": "🔵", "Partially Received": "🟡", "Complete": "🟢", "Cancelled": "🔴"}.get(status, "⚪")


def _get_month_key(po):
    """Extract 'YYYY-MM' from created_at for grouping."""
    created = po.get("created_at", "")
    if created and len(created) >= 7:
        return created[:7]  # "2026-05"
    return "Unknown"


def _month_label(month_key):
    """Convert '2026-05' to 'May 2026'."""
    try:
        dt = datetime.strptime(month_key, "%Y-%m")
        return dt.strftime("%B %Y")
    except Exception:
        return month_key


def _render_po(po):
    """Render a single PO expander with all controls."""
    status = po.get("status", "Draft")
    icon = _status_icon(status)
    label = f"{icon} [{status}] {po['po_id']} — {po.get('vendor_name', '')} | {format_currency(po.get('total_amount', 0))}"
    is_complete = status == "Complete"

    with st.expander(label):
        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            st.markdown(f"**Vendor:** {po.get('vendor_name', '')}")
            st.markdown(f"**Payment:** {po.get('payment_terms', '')}")
        with pc2:
            st.markdown(f"**Expected:** {po.get('expected_delivery', '')}")
            st.markdown(f"**Created:** {po.get('created_at', '')[:10]}")
        with pc3:
            st.markdown(f"**Total:** {format_currency(po.get('total_amount', 0))}")
            st.markdown(f"**Status:** {status}")

        # PDF
        pdf_key = po.get("pdf_key", "")
        if pdf_key:
            pdf_bytes = get_po_pdf_download(pdf_key)
            if pdf_bytes:
                st.download_button("📄 Download PO PDF", pdf_bytes, f"{po['po_id']}.pdf",
                    "application/pdf", key=f"pdf_{po['po_id']}")
        elif status == "Placed":
            if st.button("📄 Generate PDF", key=f"genpdf_{po['po_id']}"):
                po_items = get_raw_material_po_items(po["po_id"])
                pk = generate_po_pdf(po, po_items, "Material")
                if pk:
                    update_po_pdf_key(po["po_id"], pk)
                    st.success("PDF generated!")
                    st.rerun()

        # Attachments
        st.markdown("**📎 Attachments**")
        for ak in list_attachments(po["po_id"]):
            ab = get_attachment(ak)
            if ab:
                st.download_button(f"⬇️ {ak.split('/')[-1]}", ab, ak.split("/")[-1], key=f"att_{ak}")
        uploaded = st.file_uploader("Add attachment", key=f"up_{po['po_id']}")
        if uploaded and st.button("📤 Upload", key=f"upbtn_{po['po_id']}"):
            upload_attachment(po["po_id"], uploaded.name, uploaded.read(), uploaded.type)
            st.success(f"Attached {uploaded.name}")
            st.rerun()

        st.markdown("---")
        po_items = get_raw_material_po_items(po["po_id"])
        if po_items:
            if is_complete:
                st.success("✅ This PO is complete. All items received.")
                for item in po_items:
                    rc1, rc2, rc3 = st.columns([4, 1, 1])
                    with rc1:
                        st.markdown(f"**{item.get('description', '')}** — {item.get('specification', '')}")
                    with rc2:
                        st.caption(f"Ordered: {item.get('quantity', 0)} {item.get('unit', '')}")
                    with rc3:
                        st.caption(f"Received: {item.get('quantity_received', 0)} ✅")

                with st.expander("⚠️ Override — Mark as Incomplete"):
                    st.warning("This will reopen the PO for editing.")
                    confirm_text = st.text_input("Type **INCOMPLETE** to confirm", key=f"reopen_{po['po_id']}")
                    if st.button("🔓 Reopen PO", key=f"reopen_btn_{po['po_id']}",
                                 disabled=confirm_text.strip().upper() != "INCOMPLETE"):
                        update_raw_material_po_status(po["po_id"], "Partially Received")
                        st.success("PO reopened.")
                        st.rerun()
            else:
                all_received = True
                for item in po_items:
                    ordered = float(item.get("quantity", 0))
                    already_received = float(item.get("quantity_received", 0))
                    remaining = ordered - already_received
                    is_item_done = item.get("received", False)

                    rc1, rc2, rc3 = st.columns([4, 2, 2])
                    with rc1:
                        st.markdown(f"**{item.get('description', '')}**")
                        st.caption(item.get("specification", ""))
                    with rc2:
                        st.caption(f"Ordered: {ordered} {item.get('unit', '')}")
                        st.caption(f"Already received: {already_received}")
                        st.caption(f"Remaining: {remaining}")
                    with rc3:
                        if is_item_done:
                            st.success(f"✅ Fully received ({already_received})")
                        else:
                            all_received = False

                    if not is_item_done and remaining > 0:
                        with st.form(key=f"recv_form_{po['po_id']}_{item['item_id']}"):
                            fc1, fc2, fc3 = st.columns([2, 1, 1])
                            with fc1:
                                recv_now = st.number_input(
                                    "Receiving now", min_value=0.0, max_value=remaining,
                                    value=0.0, step=1.0,
                                    key=f"rn_{po['po_id']}_{item['item_id']}")
                            with fc2:
                                mark_complete = st.checkbox(
                                    "All received — close this item",
                                    value=False,
                                    key=f"mc_{po['po_id']}_{item['item_id']}")
                            with fc3:
                                submitted = st.form_submit_button("💾 Receive")

                            if submitted and (recv_now > 0 or mark_complete):
                                new_total = already_received + recv_now
                                is_done = mark_complete
                                update_po_item_receipt(po["po_id"], item["item_id"], new_total, is_done)
                                if recv_now > 0:
                                    receive_to_inventory(
                                        item.get("description", ""),
                                        item.get("category", "Received"),
                                        item.get("sub_category", "PO Receipt"),
                                        item.get("specification", ""),
                                        recv_now, item.get("unit", "Kg"),
                                        "Main Store", item.get("unit_price", 0),
                                    )
                                if is_done:
                                    st.success(f"Item closed. Total received: {new_total}/{ordered}")
                                else:
                                    st.success(f"Received {recv_now}. Total now: {new_total}/{ordered}. Remaining: {ordered - new_total}")
                                st.rerun()

                    st.markdown("<hr style='margin:4px 0;border-color:#f1f5f9'>", unsafe_allow_html=True)

                if all_received and po_items:
                    if st.button("✅ Mark Complete", key=f"comp_{po['po_id']}", type="primary"):
                        update_raw_material_po_status(po["po_id"], "Complete")
                        st.rerun()

        if status == "Draft":
            dc1, dc2 = st.columns(2)
            with dc1:
                if st.button("📤 Place Order", key=f"pl_{po['po_id']}", type="primary", use_container_width=True):
                    place_po_via_sqs(po["po_id"], "", po.get("vendor_name", ""), [], 0, "", "")
                    pi = get_raw_material_po_items(po["po_id"])
                    pk = generate_po_pdf(po, pi, "Material")
                    if pk:
                        update_po_pdf_key(po["po_id"], pk)
                    st.success("Placed!")
                    st.rerun()
            with dc2:
                if st.button("🗑️ Delete Draft", key=f"del_{po['po_id']}", use_container_width=True):
                    delete_raw_material_po(po["po_id"])
                    st.success(f"Draft PO {po['po_id']} deleted.")
                    st.rerun()


def render():
    st.markdown("# 📦 Purchase Orders")
    st.markdown("*Current month shown. Older POs grouped by month.*")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📋 All POs", "➕ Create PO"])

    # ─── Create PO ────────────────────────────────────────────
    with tab2:
        section_header("Create Purchase Order", "🆕")
        projects = get_all_projects()
        vendors = get_all_vendors()
        if not projects:
            st.warning("Create a project first.")
            return
        if not vendors:
            st.warning("Register vendors first.")
            return

        proj_opts = {f"{p['name']} ({p['project_id']})": p for p in projects}
        vendor_opts = {f"{v['name']} ({v['vendor_id']})": v for v in vendors}

        c1, c2 = st.columns(2)
        with c1:
            selected_project = st.selectbox("Project *", list(proj_opts.keys()))
        with c2:
            selected_vendor = st.selectbox("Vendor *", list(vendor_opts.keys()))
        project = proj_opts[selected_project]
        vendor = vendor_opts[selected_vendor]

        c3, c4 = st.columns(2)
        with c3:
            payment_terms = st.selectbox("Payment Terms", PAYMENT_TERMS,
                index=PAYMENT_TERMS.index(vendor.get("payment_terms", PAYMENT_TERMS[0]))
                if vendor.get("payment_terms") in PAYMENT_TERMS else 0)
        with c4:
            expected_delivery = st.date_input("Expected Delivery", value=datetime.now().date() + timedelta(days=7))

        notes = st.text_area("Notes")

        gst_pct = st.number_input("GST %", min_value=0.0, max_value=28.0, value=18.0, step=0.5,
                                    help="Default 18%. CGST and SGST will be split equally.")

        st.markdown("---")
        st.markdown("**📎 Attach files to this PO**")
        new_attachments = st.file_uploader("Choose files", accept_multiple_files=True, key="new_po_attachments")
        st.markdown("---")

        if "po_items" not in st.session_state:
            st.session_state.po_items = []

        master_items = get_all_master_items()
        vendor_master = [m for m in master_items if m.get("vendor", "").lower() == vendor["name"].lower()]

        if vendor_master:
            with st.expander(f"📂 Quick Add from Master Catalog ({len(vendor_master)} items)"):
                for mi in vendor_master[:30]:
                    qc1, qc2, qc3, qc4 = st.columns([3, 1, 1, 1])
                    with qc1:
                        st.markdown(f"**{mi['item_name']}** — {mi.get('specification', '')}")
                    with qc2:
                        price = mi.get("revised_price", 0) or mi.get("price", 0)
                        st.caption(f"₹{price}/{mi.get('unit', '')}")
                    with qc3:
                        qty = st.number_input("Qty", min_value=0, step=1, key=f"viq_{mi['item_id']}", label_visibility="collapsed")
                    with qc4:
                        if st.button("Add", key=f"va_{mi['item_id']}"):
                            if qty > 0:
                                st.session_state.po_items.append({"description": mi["item_name"],
                                    "specification": mi.get("specification", ""),
                                    "category": mi.get("category", ""),
                                    "sub_category": mi.get("sub_category", ""),
                                    "quantity": qty, "unit": mi.get("unit", "Kg"), "unit_price": price})
                                st.rerun()

        with st.form("manual_item", clear_on_submit=True):
            mc1, mc2, mc3, mc4, mc5 = st.columns([3, 2, 1, 1, 1])
            with mc1:
                desc = st.text_input("Description *")
            with mc2:
                spec = st.text_input("Specification")
            with mc3:
                qty = st.number_input("Qty *", min_value=0, step=1)
            with mc4:
                unit = st.selectbox("Unit", ["Kg", "Nos", "Meters", "Sets", "Lots", "Pcs"])
            with mc5:
                price = st.number_input("Rate ₹", min_value=0.0, step=0.5)
            if st.form_submit_button("➕ Add Line Item"):
                if desc and qty > 0:
                    st.session_state.po_items.append({"description": desc, "specification": spec,
                        "category": "", "sub_category": "",
                        "quantity": qty, "unit": unit, "unit_price": price})
                    st.rerun()

        if st.session_state.po_items:
            st.markdown("#### Current PO Items")
            for idx, item in enumerate(st.session_state.po_items):
                ic1, ic2, ic3, ic4 = st.columns([4, 1, 1, 1])
                with ic1:
                    st.markdown(f"**{item['description']}** — {item.get('specification', '')}")
                with ic2:
                    st.caption(f"{item['quantity']} {item['unit']}")
                with ic3:
                    st.caption(format_currency(item['quantity'] * item['unit_price']))
                with ic4:
                    if st.button("🗑️", key=f"rem_{idx}"):
                        st.session_state.po_items.pop(idx)
                        st.rerun()

            total = sum(i["quantity"] * i["unit_price"] for i in st.session_state.po_items)
            st.markdown(f"### Total: {format_currency(total)}")

            cs, cp = st.columns(2)
            with cs:
                if st.button("💾 Save Draft", use_container_width=True):
                    po = create_raw_material_po(project["project_id"], vendor["vendor_id"], vendor["name"],
                        payment_terms, str(expected_delivery), st.session_state.po_items, notes, gst_pct)
                    for f in (new_attachments or []):
                        upload_attachment(po["po_id"], f.name, f.read(), f.type)
                    st.success(f"PO **{po['po_id']}** saved")
                    st.session_state.po_items = []
                    st.rerun()
            with cp:
                if st.button("📤 Place Order", use_container_width=True, type="primary"):
                    po = create_raw_material_po(project["project_id"], vendor["vendor_id"], vendor["name"],
                        payment_terms, str(expected_delivery), st.session_state.po_items, notes, gst_pct)
                    place_po_via_sqs(po["po_id"], vendor.get("email", ""), vendor["name"],
                        st.session_state.po_items, total, payment_terms, str(expected_delivery))
                    pdf_key = generate_po_pdf(po, st.session_state.po_items, "Material")
                    if pdf_key:
                        update_po_pdf_key(po["po_id"], pdf_key)
                    for f in (new_attachments or []):
                        upload_attachment(po["po_id"], f.name, f.read(), f.type)
                    st.success(f"PO **{po['po_id']}** placed!")
                    st.session_state.po_items = []
                    st.rerun()

    # ─── All POs — grouped by month ──────────────────────────
    with tab1:
        all_pos = get_all_raw_material_pos()
        if not all_pos:
            empty_state("📦", "No purchase orders yet")
            return

        # Group by month
        current_month = datetime.utcnow().strftime("%Y-%m")
        by_month = defaultdict(list)
        for po in all_pos:
            mk = _get_month_key(po)
            by_month[mk].append(po)

        # Sort months descending
        sorted_months = sorted(by_month.keys(), reverse=True)

        # Summary
        total_pos = len(all_pos)
        current_count = len(by_month.get(current_month, []))
        st.markdown(f"**{total_pos} total POs** | **{current_count} this month** | **{len(sorted_months)} months**")
        st.markdown("---")

        for month_key in sorted_months:
            month_pos = sorted(by_month[month_key], key=lambda x: x.get("created_at", ""), reverse=True)
            label = _month_label(month_key)
            count = len(month_pos)
            month_total = sum(p.get("total_amount", 0) for p in month_pos)

            if month_key == current_month:
                # Current month — show directly, no folder
                st.markdown(f"### 📅 {label} — {count} PO(s) — {format_currency(month_total)}")
                for po in month_pos:
                    _render_po(po)
                st.markdown("---")
            else:
                # Older months — collapsed folder
                with st.expander(f"📁 {label} — {count} PO(s) — {format_currency(month_total)}"):
                    for po in month_pos:
                        _render_po(po)
