"""Service Purchase Orders — clean titles, PDF, attachments, scrap tracking."""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.db import (
    get_all_projects, get_all_service_vendors, get_service_vendor,
    get_service_vendor_services, create_service_po, get_all_service_pos,
    get_service_po_items, update_service_po_item, update_service_po_status,
    place_service_po_via_sqs, generate_po_pdf, update_po_pdf_key,
    get_po_pdf_download, upload_attachment, list_attachments, get_attachment,
)
from utils.ui_helpers import section_header, format_currency, empty_state
from config import PAYMENT_TERMS, UNITS_OF_MEASURE

FINISHING_STATUSES = ["Pending", "Semi-Finished", "Complete"]

def _status_icon(s):
    return {"Draft": "⚪", "Placed": "🔵", "In Progress": "🟡", "Partially Received": "🟡", "Complete": "🟢", "Cancelled": "🔴"}.get(s, "⚪")

def render():
    st.markdown("# 🛠️ Service Purchase Orders")
    st.markdown("*Track subcontracted work with finishing and scrap tracking*")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📋 All Service POs", "➕ Create Service PO"])

    with tab2:
        section_header("Create Service PO", "🆕")
        projects = get_all_projects()
        svc_vendors = get_all_service_vendors()
        if not projects: st.warning("Create a project first."); return
        if not svc_vendors: st.warning("Register service vendors first."); return

        proj_opts = {f"{p['name']} ({p['project_id']})": p for p in projects}
        vendor_opts = {f"{v['name']} ({v['vendor_id']})": v for v in svc_vendors}
        c1, c2 = st.columns(2)
        with c1: sp = st.selectbox("Project *", list(proj_opts.keys()), key="spo_p")
        with c2: sv = st.selectbox("Service Vendor *", list(vendor_opts.keys()), key="spo_v")
        project = proj_opts[sp]; vendor = vendor_opts[sv]

        c3, c4 = st.columns(2)
        with c3: pt = st.selectbox("Payment Terms", PAYMENT_TERMS, key="spo_pt")
        with c4: ed = st.date_input("Expected Return", value=datetime.now().date() + timedelta(days=14), key="spo_ed")
        notes = st.text_area("Notes", key="spo_n")

        # Attachments during creation
        st.markdown("---")
        st.markdown("**📎 Attach files to this Service PO**")
        new_spo_attachments = st.file_uploader("Choose files", accept_multiple_files=True, key="new_spo_attachments")
        st.markdown("---")

        if "spo_items" not in st.session_state: st.session_state.spo_items = []

        with st.form("spo_manual", clear_on_submit=True):
            mc1, mc2, mc3, mc4, mc5 = st.columns([3, 2, 1, 1, 1])
            with mc1: desc = st.text_input("Service *")
            with mc2: spec = st.text_input("Details")
            with mc3: qty = st.number_input("Qty", min_value=0, step=1)
            with mc4: unit = st.selectbox("Unit", UNITS_OF_MEASURE)
            with mc5: price = st.number_input("Rate ₹", min_value=0.0, step=0.5)
            if st.form_submit_button("➕ Add"):
                if desc and qty > 0:
                    st.session_state.spo_items.append({"description": desc, "specification": spec,
                        "quantity": qty, "unit": unit, "unit_price": price}); st.rerun()

        if st.session_state.spo_items:
            for idx, item in enumerate(st.session_state.spo_items):
                ic1, ic2, ic3, ic4 = st.columns([4, 1, 1, 1])
                with ic1: st.markdown(f"**{item['description']}**")
                with ic2: st.caption(f"{item['quantity']} {item['unit']}")
                with ic3: st.caption(format_currency(item['quantity'] * item['unit_price']))
                with ic4:
                    if st.button("🗑️", key=f"sr_{idx}"): st.session_state.spo_items.pop(idx); st.rerun()

            total = sum(i["quantity"] * i["unit_price"] for i in st.session_state.spo_items)
            st.markdown(f"### Total: {format_currency(total)}")
            cs, cp = st.columns(2)
            with cs:
                if st.button("💾 Save Draft", key="spo_d", use_container_width=True):
                    po = create_service_po(project["project_id"], vendor["vendor_id"], vendor["name"],
                        pt, str(ed), st.session_state.spo_items, notes)
                    for f in (new_spo_attachments or []):
                        upload_attachment(po["po_id"], f.name, f.read(), f.type)
                    st.success(f"SPO **{po['po_id']}** saved"); st.session_state.spo_items = []; st.rerun()
            with cp:
                if st.button("📤 Place Order", key="spo_pl", use_container_width=True, type="primary"):
                    po = create_service_po(project["project_id"], vendor["vendor_id"], vendor["name"],
                        pt, str(ed), st.session_state.spo_items, notes)
                    place_service_po_via_sqs(po["po_id"], vendor.get("email", ""), vendor["name"],
                        st.session_state.spo_items, total, pt, str(ed))
                    pk = generate_po_pdf(po, st.session_state.spo_items, "Service")
                    if pk: update_po_pdf_key(po["po_id"], pk, "service_po")
                    for f in (new_spo_attachments or []):
                        upload_attachment(po["po_id"], f.name, f.read(), f.type)
                    st.success(f"SPO **{po['po_id']}** placed!"); st.session_state.spo_items = []; st.rerun()

    with tab1:
        all_pos = get_all_service_pos()
        if not all_pos: empty_state("🛠️", "No service POs yet"); return

        for po in sorted(all_pos, key=lambda x: x.get("created_at", ""), reverse=True):
            status = po.get("status", "Draft")
            icon = _status_icon(status)
            label = f"{icon} [{status}] {po['po_id']} — {po.get('vendor_name', '')} | {format_currency(po.get('total_amount', 0))}"

            with st.expander(label):
                pc1, pc2, pc3 = st.columns(3)
                with pc1: st.markdown(f"**Vendor:** {po.get('vendor_name', '')}"); st.markdown(f"**Payment:** {po.get('payment_terms', '')}")
                with pc2: st.markdown(f"**Expected:** {po.get('expected_delivery', '')}"); st.markdown(f"**Status:** {status}")
                with pc3: st.markdown(f"**Total:** {format_currency(po.get('total_amount', 0))}")

                # PDF
                pdf_key = po.get("pdf_key", "")
                if pdf_key:
                    pb = get_po_pdf_download(pdf_key)
                    if pb: st.download_button("📄 Download PDF", pb, f"{po['po_id']}.pdf", "application/pdf", key=f"spdf_{po['po_id']}")
                elif status == "Placed":
                    if st.button("📄 Generate PDF", key=f"sgpdf_{po['po_id']}"):
                        pi = get_service_po_items(po["po_id"])
                        pk = generate_po_pdf(po, pi, "Service")
                        if pk: update_po_pdf_key(po["po_id"], pk, "service_po"); st.success("PDF generated!"); st.rerun()

                # Attachments
                st.markdown("**📎 Attachments**")
                for ak in list_attachments(po["po_id"]):
                    ab = get_attachment(ak)
                    if ab: st.download_button(f"⬇️ {ak.split('/')[-1]}", ab, ak.split("/")[-1], key=f"sa_{ak}")
                uploaded = st.file_uploader("Upload attachment", key=f"sup_{po['po_id']}")
                if uploaded and st.button("📤 Upload", key=f"subtn_{po['po_id']}"):
                    upload_attachment(po["po_id"], uploaded.name, uploaded.read(), uploaded.type)
                    st.success(f"Attached {uploaded.name}"); st.rerun()

                st.markdown("---")
                po_items = get_service_po_items(po["po_id"])
                is_complete = status == "Complete"

                if is_complete:
                    # ─── COMPLETE: Read-only view ─────────────────
                    st.success("✅ This Service PO is complete. All items received.")
                    for item in po_items:
                        st.markdown(f"**{item.get('description', '')}** — {item.get('specification', '')}")
                        rc1, rc2, rc3 = st.columns(3)
                        with rc1:
                            st.caption(f"Ordered: {item.get('quantity', 0)} {item.get('unit', '')} | Received: {item.get('quantity_received', 0)} ✅")
                        with rc2:
                            st.caption(f"Finishing: {item.get('finishing_status', '')} | {item.get('finishing_comment', '')}")
                        with rc3:
                            scrap = item.get("scrap_received", 0)
                            if scrap:
                                st.caption(f"Scrap: {scrap} {'(usable)' if item.get('scrap_usable') else ''} {item.get('scrap_notes', '')}")
                        st.markdown("<hr style='margin:4px 0;border-color:#f1f5f9'>", unsafe_allow_html=True)

                    # Override: reopen as incomplete
                    with st.expander("⚠️ Override — Mark as Incomplete"):
                        st.warning("This will reopen the Service PO for editing. Use only if it was marked complete by mistake.")
                        confirm_text = st.text_input("Type **INCOMPLETE** to confirm", key=f"sreopen_{po['po_id']}")
                        if st.button("🔓 Reopen Service PO", key=f"sreopen_btn_{po['po_id']}",
                                     disabled=confirm_text.strip().upper() != "INCOMPLETE"):
                            update_service_po_status(po["po_id"], "Partially Received")
                            st.success("Service PO reopened — you can now edit received quantities.")
                            st.rerun()
                else:
                    # ─── EDITABLE: Receipt tracking ───────────────
                    all_received = True
                    for item in po_items:
                        st.markdown(f"**{item.get('description', '')}** — {item.get('specification', '')}")
                        rc1, rc2, rc3 = st.columns(3)
                        with rc1:
                            st.caption(f"Ordered: {item.get('quantity', 0)} {item.get('unit', '')}")
                            qr = st.number_input("Qty Received", min_value=0.0, max_value=float(item.get("quantity", 0)),
                                value=float(item.get("quantity_received", 0)), step=1.0, key=f"sqr_{po['po_id']}_{item['item_id']}")
                            ir = st.checkbox("Received", value=item.get("received", False), key=f"sc_{po['po_id']}_{item['item_id']}")
                        with rc2:
                            fs = st.selectbox("Finishing", FINISHING_STATUSES,
                                index=FINISHING_STATUSES.index(item.get("finishing_status", "Pending"))
                                if item.get("finishing_status") in FINISHING_STATUSES else 0, key=f"sfs_{po['po_id']}_{item['item_id']}")
                            fc = st.text_area("Comment", value=item.get("finishing_comment", ""), height=60, key=f"sfc_{po['po_id']}_{item['item_id']}")
                        with rc3:
                            st.markdown("**Scrap**")
                            scr = st.number_input("Scrap Qty", min_value=0.0, step=0.5, value=float(item.get("scrap_received", 0)), key=f"scr_{po['po_id']}_{item['item_id']}")
                            su = st.checkbox("Usable?", value=item.get("scrap_usable", False), key=f"ssu_{po['po_id']}_{item['item_id']}")
                            sn = st.text_input("Scrap Notes", value=item.get("scrap_notes", ""), key=f"ssn_{po['po_id']}_{item['item_id']}")
                        if not ir: all_received = False
                        if st.button("💾 Update", key=f"supd_{po['po_id']}_{item['item_id']}"):
                            update_service_po_item(po["po_id"], item["item_id"], qr, ir, fs, fc, scr, su, sn)
                            st.success("Updated!"); st.rerun()
                        st.markdown("<hr style='margin:8px 0;border-color:#f1f5f9'>", unsafe_allow_html=True)

                    if all_received and po_items:
                        if st.button("✅ Mark Complete", key=f"scomp_{po['po_id']}", type="primary"):
                            update_service_po_status(po["po_id"], "Complete"); st.rerun()

                if status == "Draft":
                    if st.button("📤 Place Order", key=f"spl_{po['po_id']}", type="primary"):
                        place_service_po_via_sqs(po["po_id"], "", po.get("vendor_name", ""), [], 0, "", "")
                        pi = get_service_po_items(po["po_id"])
                        pk = generate_po_pdf(po, pi, "Service")
                        if pk: update_po_pdf_key(po["po_id"], pk, "service_po")
                        st.success("Placed!"); st.rerun()
