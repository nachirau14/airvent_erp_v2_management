"""Service POs — linked to inventory, delivery challans, scrap tracking."""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.db import (
    get_all_projects, get_all_service_vendors, get_service_vendor,
    get_service_vendor_services, create_service_po, get_all_service_pos,
    get_service_po_items, update_service_po_item, update_service_po_status,
    place_service_po_via_sqs, generate_po_pdf, update_po_pdf_key,
    get_po_pdf_download, upload_attachment, list_attachments, get_attachment,
    get_all_inventory, issue_material_to_service_vendor,
    generate_delivery_challan, add_scrap_item, get_raw_material_po,
)
from utils.ui_helpers import section_header, format_currency, empty_state
from config import PAYMENT_TERMS, UNITS_OF_MEASURE

FINISHING_STATUSES = ["Pending", "Semi-Finished", "Complete"]

def _status_icon(s):
    return {"Draft": "⚪", "Placed": "🔵", "In Progress": "🟡", "Partially Received": "🟡", "Complete": "🟢", "Cancelled": "🔴"}.get(s, "⚪")


def render():
    st.markdown("# 🛠️ Service Purchase Orders")
    st.markdown("*Select material from inventory → send to service vendor → track finishing → receive scrap*")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📋 All Service POs", "➕ Create Service PO"])

    # ═══════════════════════════════════════════════════════════
    #  CREATE SERVICE PO
    # ═══════════════════════════════════════════════════════════
    with tab2:
        section_header("Create Service PO", "🆕")
        projects = get_all_projects()
        svc_vendors = get_all_service_vendors()
        if not projects:
            st.warning("Create a project first.")
            return
        if not svc_vendors:
            st.warning("Register service vendors first.")
            return

        proj_opts = {f"{p['name']} ({p['project_id']})": p for p in projects}
        vendor_opts = {f"{v['name']} ({v['vendor_id']})": v for v in svc_vendors}
        c1, c2 = st.columns(2)
        with c1:
            sp = st.selectbox("Project *", list(proj_opts.keys()), key="spo_p")
        with c2:
            sv = st.selectbox("Service Vendor *", list(vendor_opts.keys()), key="spo_v")
        project = proj_opts[sp]
        vendor = vendor_opts[sv]

        c3, c4 = st.columns(2)
        with c3:
            pt = st.selectbox("Payment Terms", PAYMENT_TERMS, key="spo_pt")
        with c4:
            ed = st.date_input("Expected Return", value=datetime.now().date() + timedelta(days=14), key="spo_ed")
        notes = st.text_area("Notes", key="spo_n")

        st.markdown("---")
        st.markdown("**📎 Attach files**")
        new_spo_attachments = st.file_uploader("Choose files", accept_multiple_files=True, key="new_spo_att")

        # ─── Step 1: Select material from inventory to send ───
        st.markdown("---")
        section_header("Step 1: Select Material from Inventory", "📦")
        st.markdown("*Choose raw materials from your stock to send to the service vendor*")

        inventory = get_all_inventory()
        in_stock = [i for i in inventory if i.get("quantity", 0) > 0]

        if "spo_material" not in st.session_state:
            st.session_state.spo_material = []

        if in_stock:
            search = st.text_input("🔍 Search inventory", key="spo_inv_search")
            filtered = in_stock
            if search:
                s = search.lower()
                filtered = [i for i in filtered if s in i.get("item_name", "").lower() or
                            s in i.get("specification", "").lower() or s in i.get("category", "").lower()]

            for inv_item in filtered[:15]:
                avail = inv_item.get("quantity", 0)
                ic1, ic2, ic3, ic4 = st.columns([3, 1, 1, 1])
                with ic1:
                    st.markdown(f"**{inv_item['item_name']}**")
                    st.caption(f"{inv_item.get('category', '')} | {inv_item.get('specification', '')}")
                with ic2:
                    st.caption(f"Stock: {avail} {inv_item.get('unit', '')}")
                with ic3:
                    qty = st.number_input("Qty", min_value=0, max_value=int(avail), step=1,
                                           key=f"spo_iq_{inv_item['item_id']}", label_visibility="collapsed")
                with ic4:
                    if st.button("Add", key=f"spo_ia_{inv_item['item_id']}"):
                        if qty > 0:
                            st.session_state.spo_material.append({
                                "item_id": inv_item["item_id"],
                                "item_name": inv_item["item_name"],
                                "specification": inv_item.get("specification", ""),
                                "category": inv_item.get("category", ""),
                                "quantity": qty,
                                "unit": inv_item.get("unit", ""),
                            })
                            st.rerun()

            if st.session_state.spo_material:
                st.markdown("#### Material to Send")
                for idx, m in enumerate(st.session_state.spo_material):
                    mc1, mc2, mc3 = st.columns([4, 1, 1])
                    with mc1:
                        st.markdown(f"**{m['item_name']}** — {m.get('specification', '')}")
                    with mc2:
                        st.caption(f"{m['quantity']} {m['unit']}")
                    with mc3:
                        if st.button("🗑️", key=f"spo_mr_{idx}"):
                            st.session_state.spo_material.pop(idx)
                            st.rerun()
        else:
            st.info("No items in inventory. Add stock first.")

        # ─── Step 2: Add service charges ──────────────────────
        st.markdown("---")
        section_header("Step 2: Service Charges", "💰")

        if "spo_items" not in st.session_state:
            st.session_state.spo_items = []

        with st.form("spo_manual", clear_on_submit=True):
            mc1, mc2, mc3, mc4, mc5 = st.columns([3, 2, 1, 1, 1])
            with mc1:
                desc = st.text_input("Service *", placeholder="e.g., Laser Cutting, Bending")
            with mc2:
                spec = st.text_input("Details", placeholder="e.g., 2mm MS sheets")
            with mc3:
                qty = st.number_input("Qty", min_value=0, step=1)
            with mc4:
                unit = st.selectbox("Unit", UNITS_OF_MEASURE)
            with mc5:
                price = st.number_input("Rate ₹", min_value=0.0, step=0.5)
            if st.form_submit_button("➕ Add Service"):
                if desc and qty > 0:
                    st.session_state.spo_items.append({"description": desc, "specification": spec,
                        "quantity": qty, "unit": unit, "unit_price": price})
                    st.rerun()

        if st.session_state.spo_items:
            st.markdown("#### Service Line Items")
            for idx, item in enumerate(st.session_state.spo_items):
                ic1, ic2, ic3, ic4 = st.columns([4, 1, 1, 1])
                with ic1:
                    st.markdown(f"**{item['description']}** — {item.get('specification', '')}")
                with ic2:
                    st.caption(f"{item['quantity']} {item['unit']}")
                with ic3:
                    st.caption(format_currency(item['quantity'] * item['unit_price']))
                with ic4:
                    if st.button("🗑️", key=f"spo_sr_{idx}"):
                        st.session_state.spo_items.pop(idx)
                        st.rerun()

            total = sum(i["quantity"] * i["unit_price"] for i in st.session_state.spo_items)
            st.markdown(f"### Service Total: {format_currency(total)}")

        # ─── Step 3: Save / Place ─────────────────────────────
        st.markdown("---")
        can_save = st.session_state.spo_items or st.session_state.spo_material

        if can_save:
            cs, cp = st.columns(2)
            with cs:
                if st.button("💾 Save Draft", key="spo_d", use_container_width=True):
                    svc_items = st.session_state.spo_items if st.session_state.spo_items else [
                        {"description": m["item_name"], "specification": m.get("specification", ""),
                         "quantity": m["quantity"], "unit": m["unit"], "unit_price": 0}
                        for m in st.session_state.spo_material]
                    po = create_service_po(project["project_id"], vendor["vendor_id"], vendor["name"],
                        pt, str(ed), svc_items, notes)
                    if st.session_state.spo_material:
                        issue_material_to_service_vendor(po["po_id"], st.session_state.spo_material)
                    for f in (new_spo_attachments or []):
                        upload_attachment(po["po_id"], f.name, f.read(), f.type)
                    st.success(f"SPO **{po['po_id']}** saved. Material deducted from inventory.")
                    st.session_state.spo_items = []
                    st.session_state.spo_material = []
                    st.rerun()
            with cp:
                if st.button("📤 Place Order", key="spo_pl", use_container_width=True, type="primary"):
                    svc_items = st.session_state.spo_items if st.session_state.spo_items else [
                        {"description": m["item_name"], "specification": m.get("specification", ""),
                         "quantity": m["quantity"], "unit": m["unit"], "unit_price": 0}
                        for m in st.session_state.spo_material]
                    total = sum(i.get("quantity", 0) * i.get("unit_price", 0) for i in svc_items)
                    po = create_service_po(project["project_id"], vendor["vendor_id"], vendor["name"],
                        pt, str(ed), svc_items, notes)
                    if st.session_state.spo_material:
                        issue_material_to_service_vendor(po["po_id"], st.session_state.spo_material)
                    place_service_po_via_sqs(po["po_id"], vendor.get("email", ""), vendor["name"],
                        svc_items, total, pt, str(ed))
                    pk = generate_po_pdf(po, svc_items, "Service")
                    if pk:
                        update_po_pdf_key(po["po_id"], pk, "service_po")
                    for f in (new_spo_attachments or []):
                        upload_attachment(po["po_id"], f.name, f.read(), f.type)
                    st.success(f"SPO **{po['po_id']}** placed! Material deducted from inventory.")
                    st.session_state.spo_items = []
                    st.session_state.spo_material = []
                    st.rerun()
        else:
            st.info("Add material from inventory and/or service charges above.")

    # ═══════════════════════════════════════════════════════════
    #  ALL SERVICE POs
    # ═══════════════════════════════════════════════════════════
    with tab1:
        all_pos = get_all_service_pos()
        if not all_pos:
            empty_state("🛠️", "No service POs yet")
            return

        for po in sorted(all_pos, key=lambda x: x.get("created_at", ""), reverse=True):
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
                    st.markdown(f"**Status:** {status}")
                with pc3:
                    st.markdown(f"**Total:** {format_currency(po.get('total_amount', 0))}")

                # ─── Issued Material ──────────────────────────
                issued = po.get("issued_material", [])
                if issued:
                    st.markdown("**📦 Material Sent to Vendor:**")
                    for m in issued:
                        st.caption(f"• {m.get('item_name', '')} — {m.get('quantity', 0)} {m.get('unit', '')} | {m.get('specification', '')}")

                # ─── PDFs ─────────────────────────────────────
                pdf_key = po.get("pdf_key", "")
                if pdf_key:
                    pb = get_po_pdf_download(pdf_key)
                    if pb:
                        st.download_button("📄 Download Service PO PDF", pb, f"{po['po_id']}.pdf",
                            "application/pdf", key=f"spdf_{po['po_id']}")

                # Delivery Challan
                if issued and status in ("Placed", "In Progress", "Draft"):
                    if st.button("🚚 Generate Delivery Challan", key=f"dc_{po['po_id']}"):
                        challan_items = [{"description": m.get("item_name", ""), "item_name": m.get("item_name", ""),
                                          "specification": m.get("specification", ""),
                                          "quantity": m.get("quantity", 0), "unit": m.get("unit", ""),
                                          "hsn_code": ""} for m in issued]
                        po_with_addr = dict(po)
                        # Get vendor address
                        v = get_service_vendor(po.get("vendor_id", ""))
                        if v:
                            po_with_addr["vendor_address"] = v.get("address", "")
                        dc_key = generate_delivery_challan(po_with_addr, challan_items)
                        if dc_key:
                            dc_bytes = get_po_pdf_download(dc_key)
                            if dc_bytes:
                                st.download_button("📄 Download Delivery Challan", dc_bytes,
                                    f"DC-{po['po_id']}.pdf", "application/pdf", key=f"dcpdf_{po['po_id']}")
                            st.success("Delivery Challan generated!")
                        else:
                            st.error("Failed to generate challan")

                # Attachments
                st.markdown("**📎 Attachments**")
                for ak in list_attachments(po["po_id"]):
                    ab = get_attachment(ak)
                    if ab:
                        st.download_button(f"⬇️ {ak.split('/')[-1]}", ab, ak.split("/")[-1], key=f"sa_{ak}")
                uploaded = st.file_uploader("Upload attachment", key=f"sup_{po['po_id']}")
                if uploaded and st.button("📤 Upload", key=f"subtn_{po['po_id']}"):
                    upload_attachment(po["po_id"], uploaded.name, uploaded.read(), uploaded.type)
                    st.success(f"Attached {uploaded.name}")
                    st.rerun()

                st.markdown("---")
                po_items = get_service_po_items(po["po_id"])

                if is_complete:
                    # ─── COMPLETE: Read-only ──────────────────
                    st.success("✅ This Service PO is complete.")
                    for item in po_items:
                        st.markdown(f"**{item.get('description', '')}** — {item.get('specification', '')}")
                        rc1, rc2, rc3 = st.columns(3)
                        with rc1:
                            st.caption(f"Ordered: {item.get('quantity', 0)} | Received: {item.get('quantity_received', 0)} ✅")
                        with rc2:
                            st.caption(f"Finishing: {item.get('finishing_status', '')} | {item.get('finishing_comment', '')}")
                        with rc3:
                            scrap = item.get("scrap_received", 0)
                            if scrap:
                                st.caption(f"Scrap: {scrap} {'(usable)' if item.get('scrap_usable') else ''}")

                    with st.expander("⚠️ Override — Mark as Incomplete"):
                        st.warning("Reopen for editing if marked complete by mistake.")
                        ct = st.text_input("Type INCOMPLETE to confirm", key=f"sro_{po['po_id']}")
                        if st.button("🔓 Reopen", key=f"srob_{po['po_id']}",
                                     disabled=ct.strip().upper() != "INCOMPLETE"):
                            update_service_po_status(po["po_id"], "Partially Received")
                            st.success("Reopened!")
                            st.rerun()
                else:
                    # ─── EDITABLE: Receipt + Scrap ────────────
                    all_received = True
                    for item in po_items:
                        ordered = float(item.get("quantity", 0))
                        already = float(item.get("quantity_received", 0))
                        remaining = ordered - already
                        is_item_done = item.get("received", False)

                        st.markdown(f"**{item.get('description', '')}** — {item.get('specification', '')}")

                        if is_item_done:
                            st.success(f"✅ Fully received ({already})")
                        else:
                            all_received = False
                            rc1, rc2 = st.columns(2)
                            with rc1:
                                st.caption(f"Ordered: {ordered} | Received: {already} | Remaining: {remaining}")
                                fs = st.selectbox("Finishing", FINISHING_STATUSES,
                                    index=FINISHING_STATUSES.index(item.get("finishing_status", "Pending"))
                                    if item.get("finishing_status") in FINISHING_STATUSES else 0,
                                    key=f"sfs_{po['po_id']}_{item['item_id']}")
                                fc = st.text_area("Comment", value=item.get("finishing_comment", ""),
                                    height=60, key=f"sfc_{po['po_id']}_{item['item_id']}")
                            with rc2:
                                with st.form(key=f"srecv_{po['po_id']}_{item['item_id']}"):
                                    recv_now = st.number_input("Receiving now", min_value=0.0,
                                        max_value=remaining, value=0.0, step=1.0,
                                        key=f"srn_{po['po_id']}_{item['item_id']}")
                                    mark_done = st.checkbox("All received — close this item",
                                        key=f"smd_{po['po_id']}_{item['item_id']}")

                                    st.markdown("**Scrap received:**")
                                    scr = st.number_input("Scrap Qty", min_value=0.0, step=0.5,
                                        key=f"scr_{po['po_id']}_{item['item_id']}")
                                    su = st.checkbox("Usable scrap?", key=f"ssu_{po['po_id']}_{item['item_id']}")
                                    sn = st.text_input("Scrap notes", key=f"ssn_{po['po_id']}_{item['item_id']}")

                                    if st.form_submit_button("💾 Update"):
                                        new_total = already + recv_now
                                        is_done = mark_done
                                        update_service_po_item(po["po_id"], item["item_id"],
                                            new_total, is_done, fs, fc, scr, su, sn)
                                        # Add scrap to scrap inventory
                                        if scr > 0:
                                            add_scrap_item(
                                                item.get("description", ""), item.get("category", "Scrap"),
                                                item.get("specification", ""), scr,
                                                item.get("unit", "Kg"), po["po_id"],
                                                f"{'Usable' if su else 'Not usable'}: {sn}",
                                            )
                                        if recv_now > 0:
                                            st.success(f"Received {recv_now}. Total: {new_total}/{ordered}")
                                        elif is_done:
                                            st.success("Marked as complete")
                                        else:
                                            st.success("Updated!")
                                        st.rerun()

                        st.markdown("<hr style='margin:4px 0;border-color:#f1f5f9'>", unsafe_allow_html=True)

                    if all_received and po_items:
                        if st.button("✅ Mark Complete", key=f"scomp_{po['po_id']}", type="primary"):
                            update_service_po_status(po["po_id"], "Complete")
                            st.rerun()

                if status == "Draft":
                    if st.button("📤 Place Order", key=f"spl_{po['po_id']}", type="primary"):
                        place_service_po_via_sqs(po["po_id"], "", po.get("vendor_name", ""), [], 0, "", "")
                        pi = get_service_po_items(po["po_id"])
                        pk = generate_po_pdf(po, pi, "Service")
                        if pk:
                            update_po_pdf_key(po["po_id"], pk, "service_po")
                        st.success("Placed!")
                        st.rerun()
