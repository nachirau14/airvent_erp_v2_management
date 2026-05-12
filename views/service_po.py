"""Service POs — search inventory/scrap, service = description + rate, always saveable."""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from utils.db import (
    get_all_projects, get_all_service_vendors, get_service_vendor,
    create_service_po, get_all_service_pos,
    get_service_po_items, update_service_po_item, update_service_po_status,
    place_service_po_via_sqs, generate_po_pdf, update_po_pdf_key,
    get_po_pdf_download, upload_attachment, list_attachments, get_attachment,
    get_all_inventory, get_all_scrap, issue_material_to_service_vendor,
    generate_delivery_challan, add_scrap_item,
)
from utils.ui_helpers import section_header, format_currency, empty_state
from config import PAYMENT_TERMS

FINISHING_STATUSES = ["Pending", "Semi-Finished", "Complete"]

def _status_icon(s):
    return {"Draft": "⚪", "Placed": "🔵", "In Progress": "🟡", "Partially Received": "🟡", "Complete": "🟢", "Cancelled": "🔴"}.get(s, "⚪")


def render():
    st.markdown("# 🛠️ Service Purchase Orders")
    st.markdown("*Search inventory/scrap → select material → add service charge → place order*")
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

        gst_pct = st.number_input("GST %", min_value=0.0, max_value=28.0, value=18.0, step=0.5,
                                    key="spo_gst", help="Default 18%. CGST and SGST split equally.")

        st.markdown("---")
        st.markdown("**📎 Attach files**")
        new_spo_attachments = st.file_uploader("Choose files", accept_multiple_files=True, key="new_spo_att")

        # ─── Step 1: Search & select material ─────────────────
        st.markdown("---")
        section_header("Step 1: Select Material to Send", "📦")
        st.markdown("*Search your raw material inventory or scrap store. Only matching items are shown.*")

        if "spo_material" not in st.session_state:
            st.session_state.spo_material = []

        # ── Raw Material Inventory Search ─────────────────────
        st.markdown("**📦 Raw Material Inventory**")
        inv_search = st.text_input("🔍 Search raw material inventory", key="spo_inv_search",
                                    placeholder="Type item name, spec, or category and press Enter...")

        if inv_search and len(inv_search) >= 2:
            s = inv_search.lower()
            all_inv = get_all_inventory()
            matched = [i for i in all_inv if i.get("quantity", 0) > 0 and (
                s in i.get("item_name", "").lower() or
                s in i.get("specification", "").lower() or
                s in i.get("category", "").lower())]

            if matched:
                st.caption(f"Found {len(matched)} item(s) in inventory")
                for inv_item in matched[:10]:
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
                                    "source": "Raw Material",
                                })
                                st.rerun()
            else:
                st.caption("No matching items in inventory.")
        elif inv_search:
            st.caption("Type at least 2 characters.")

        st.markdown("")

        # ── Scrap Store Search ────────────────────────────────
        st.markdown("**♻️ Scrap Store**")
        scrap_search = st.text_input("🔍 Search scrap inventory", key="spo_scrap_search",
                                      placeholder="Type item name or notes and press Enter...")

        if scrap_search and len(scrap_search) >= 2:
            s = scrap_search.lower()
            all_scrap = get_all_scrap()
            matched_scrap = [i for i in all_scrap if i.get("quantity", 0) > 0 and (
                s in i.get("item_name", "").lower() or
                s in i.get("specification", "").lower() or
                s in i.get("category", "").lower() or
                s in i.get("notes", "").lower())]

            if matched_scrap:
                st.caption(f"Found {len(matched_scrap)} item(s) in scrap store")
                for scrap_item in matched_scrap[:10]:
                    avail = scrap_item.get("quantity", 0)
                    sc1, sc2, sc3, sc4 = st.columns([3, 1, 1, 1])
                    with sc1:
                        st.markdown(f"**{scrap_item['item_name']}**")
                        st.caption(f"{scrap_item.get('specification', '')} | {scrap_item.get('notes', '')}")
                    with sc2:
                        st.caption(f"Stock: {avail} {scrap_item.get('unit', '')}")
                    with sc3:
                        qty = st.number_input("Qty", min_value=0, max_value=int(avail), step=1,
                                               key=f"spo_sq_{scrap_item['item_id']}", label_visibility="collapsed")
                    with sc4:
                        if st.button("Add", key=f"spo_sa_{scrap_item['item_id']}"):
                            if qty > 0:
                                st.session_state.spo_material.append({
                                    "item_id": scrap_item["item_id"],
                                    "item_name": scrap_item["item_name"],
                                    "specification": scrap_item.get("specification", ""),
                                    "category": scrap_item.get("category", "Scrap"),
                                    "quantity": qty,
                                    "unit": scrap_item.get("unit", ""),
                                    "source": "Scrap Store",
                                })
                                st.rerun()
            else:
                st.caption("No matching items in scrap store.")
        elif scrap_search:
            st.caption("Type at least 2 characters.")

        # Show selected material
        if st.session_state.spo_material:
            st.markdown("#### 📦 Material Selected")
            for idx, m in enumerate(st.session_state.spo_material):
                mc1, mc2, mc3, mc4 = st.columns([3, 1, 1, 1])
                with mc1:
                    st.markdown(f"**{m['item_name']}** — {m.get('specification', '')}")
                with mc2:
                    st.caption(f"{m['quantity']} {m['unit']}")
                with mc3:
                    st.caption(f"From: {m.get('source', 'Inventory')}")
                with mc4:
                    if st.button("🗑️", key=f"spo_mr_{idx}"):
                        st.session_state.spo_material.pop(idx)
                        st.rerun()

        # ─── Step 2: Service description + rate ───────────────
        st.markdown("---")
        section_header("Step 2: Service Charge", "💰")
        st.markdown("*Describe the service and rate. The material items from Step 1 will be included in the PO automatically.*")

        if "spo_service" not in st.session_state:
            st.session_state.spo_service = {"description": "", "rate": 0.0}

        with st.form("spo_svc_form"):
            sc1, sc2 = st.columns([3, 1])
            with sc1:
                svc_desc = st.text_input("Service Description *", placeholder="e.g., Laser Cutting, Powder Coating, Bending")
            with sc2:
                svc_rate = st.number_input("Service Rate (₹)", min_value=0.0, step=0.5)
            if st.form_submit_button("✅ Set Service"):
                if svc_desc:
                    st.session_state.spo_service = {"description": svc_desc, "rate": svc_rate}
                    st.success(f"Service set: **{svc_desc}** — ₹{svc_rate:,.2f}")
                else:
                    st.error("Service description is required.")

        if st.session_state.spo_service.get("description"):
            st.markdown(f"**Service:** {st.session_state.spo_service['description']} | **Rate:** {format_currency(st.session_state.spo_service['rate'])}")

        # ─── Step 3: Summary & Save/Place ─────────────────────
        st.markdown("---")
        section_header("Step 3: Review & Place", "🚀")

        has_material = len(st.session_state.spo_material) > 0
        has_service = bool(st.session_state.spo_service.get("description"))

        if has_material or has_service:
            # Build summary
            if has_material:
                st.markdown("**Material to send:**")
                for m in st.session_state.spo_material:
                    st.caption(f"• {m['item_name']} — {m['quantity']} {m['unit']}")

            if has_service:
                st.markdown(f"**Service:** {st.session_state.spo_service['description']} — {format_currency(st.session_state.spo_service['rate'])}")

            # Build PO line items: material items + service charge
            po_line_items = []
            for m in st.session_state.spo_material:
                po_line_items.append({
                    "description": m["item_name"],
                    "specification": m.get("specification", ""),
                    "quantity": m["quantity"],
                    "unit": m["unit"],
                    "unit_price": 0,  # material cost is already in inventory
                })
            if has_service:
                total_material_qty = sum(m["quantity"] for m in st.session_state.spo_material) if st.session_state.spo_material else 1
                po_line_items.append({
                    "description": st.session_state.spo_service["description"],
                    "specification": "Service charge",
                    "quantity": total_material_qty,
                    "unit": "Lot" if not st.session_state.spo_material else st.session_state.spo_material[0].get("unit", "Nos"),
                    "unit_price": st.session_state.spo_service["rate"],
                })

            total = sum(i["quantity"] * i["unit_price"] for i in po_line_items)
            if total > 0:
                st.markdown(f"### Service Total: {format_currency(total)}")

            st.markdown("")
            cs, cp = st.columns(2)
            with cs:
                if st.button("💾 Save Draft", key="spo_d", use_container_width=True):
                    po = create_service_po(project["project_id"], vendor["vendor_id"], vendor["name"],
                        pt, str(ed), po_line_items, notes, gst_pct)
                    if has_material:
                        issue_material_to_service_vendor(po["po_id"], st.session_state.spo_material)
                    for f in (new_spo_attachments or []):
                        upload_attachment(po["po_id"], f.name, f.read(), f.type)
                    st.success(f"SPO **{po['po_id']}** saved. Material deducted from inventory.")
                    st.session_state.spo_material = []
                    st.session_state.spo_service = {"description": "", "rate": 0.0}
                    st.rerun()
            with cp:
                if st.button("📤 Place Order", key="spo_pl", use_container_width=True, type="primary"):
                    po = create_service_po(project["project_id"], vendor["vendor_id"], vendor["name"],
                        pt, str(ed), po_line_items, notes, gst_pct)
                    if has_material:
                        issue_material_to_service_vendor(po["po_id"], st.session_state.spo_material)
                    place_service_po_via_sqs(po["po_id"], vendor.get("email", ""), vendor["name"],
                        po_line_items, total, pt, str(ed))
                    pk = generate_po_pdf(po, po_line_items, "Service")
                    if pk:
                        update_po_pdf_key(po["po_id"], pk, "service_po")
                    for f in (new_spo_attachments or []):
                        upload_attachment(po["po_id"], f.name, f.read(), f.type)
                    st.success(f"SPO **{po['po_id']}** placed! Material deducted from inventory.")
                    st.session_state.spo_material = []
                    st.session_state.spo_service = {"description": "", "rate": 0.0}
                    st.rerun()
        else:
            st.info("Select material from inventory (Step 1) and/or add a service charge (Step 2) to proceed.")

    # ═══════════════════════════════════════════════════════════
    #  ALL SERVICE POs — grouped by month
    # ═══════════════════════════════════════════════════════════
    with tab1:
        all_pos = get_all_service_pos()
        if not all_pos:
            empty_state("🛠️", "No service POs yet")
            return

        current_month = datetime.utcnow().strftime("%Y-%m")
        by_month = defaultdict(list)
        for po in all_pos:
            created = po.get("created_at", "")
            mk = created[:7] if created and len(created) >= 7 else "Unknown"
            by_month[mk].append(po)

        sorted_months = sorted(by_month.keys(), reverse=True)
        total_pos = len(all_pos)
        current_count = len(by_month.get(current_month, []))
        st.markdown(f"**{total_pos} total SPOs** | **{current_count} this month** | **{len(sorted_months)} months**")
        st.markdown("---")

        for month_key in sorted_months:
            month_pos = sorted(by_month[month_key], key=lambda x: x.get("created_at", ""), reverse=True)
            try:
                mlabel = datetime.strptime(month_key, "%Y-%m").strftime("%B %Y")
            except Exception:
                mlabel = month_key
            count = len(month_pos)
            month_total = sum(p.get("total_amount", 0) for p in month_pos)

            if month_key == current_month:
                st.markdown(f"### 📅 {mlabel} — {count} SPO(s) — {format_currency(month_total)}")
                for po in month_pos:
                    _render_spo(po)
                st.markdown("---")
            else:
                with st.expander(f"📁 {mlabel} — {count} SPO(s) — {format_currency(month_total)}"):
                    for po in month_pos:
                        _render_spo(po)


def _render_spo(po):
    """Render a single Service PO expander."""
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

        # Issued Material
        issued = po.get("issued_material", [])
        if issued:
            st.markdown("**📦 Material Sent to Vendor:**")
            for m in issued:
                st.caption(f"• {m.get('item_name', '')} — {m.get('quantity', 0)} {m.get('unit', '')} | {m.get('specification', '')}")

        # PDFs
        pdf_key = po.get("pdf_key", "")
        if pdf_key:
            pb = get_po_pdf_download(pdf_key)
            if pb:
                st.download_button("📄 Download Service PO PDF", pb, f"{po['po_id']}.pdf",
                    "application/pdf", key=f"spdf_{po['po_id']}")
        elif status in ("Placed", "In Progress"):
            if st.button("📄 Generate PDF", key=f"sgpdf_{po['po_id']}"):
                pi = get_service_po_items(po["po_id"])
                pk = generate_po_pdf(po, pi, "Service")
                if pk:
                    update_po_pdf_key(po["po_id"], pk, "service_po")
                    st.success("PDF generated!")
                    st.rerun()

        # Delivery Challan
        if status in ("Placed", "In Progress", "Draft"):
            with st.expander("🚚 Delivery Challan"):
                dc_items = issued if issued else []
                if not dc_items:
                    dc_items_raw = get_service_po_items(po["po_id"])
                    dc_items = [{"item_name": i.get("description", ""), "specification": i.get("specification", ""),
                                 "quantity": i.get("quantity", 0), "unit": i.get("unit", "")} for i in dc_items_raw]

                if dc_items:
                    for m in dc_items:
                        st.caption(f"• {m.get('item_name', '')} — {m.get('quantity', 0)} {m.get('unit', '')}")
                    if st.button("📄 Generate Delivery Challan", key=f"dc_{po['po_id']}"):
                        challan_items = [{"description": m.get("item_name", ""), "item_name": m.get("item_name", ""),
                                          "specification": m.get("specification", ""),
                                          "quantity": m.get("quantity", 0), "unit": m.get("unit", ""),
                                          "hsn_code": ""} for m in dc_items]
                        po_with_addr = dict(po)
                        v = get_service_vendor(po.get("vendor_id", ""))
                        if v:
                            po_with_addr["vendor_address"] = v.get("address", "")
                        dc_key = generate_delivery_challan(po_with_addr, challan_items)
                        if dc_key:
                            dc_bytes = get_po_pdf_download(dc_key)
                            if dc_bytes:
                                st.download_button("⬇️ Download Delivery Challan", dc_bytes,
                                    f"DC-{po['po_id']}.pdf", "application/pdf", key=f"dcpdf_{po['po_id']}")
                            st.success("Delivery Challan generated!")

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
                                max_value=remaining if remaining > 0 else 1.0, value=0.0, step=1.0,
                                key=f"srn_{po['po_id']}_{item['item_id']}")
                            mark_done = st.checkbox("All received — close this item",
                                value=False, key=f"smd_{po['po_id']}_{item['item_id']}")
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
                                if scr > 0:
                                    add_scrap_item(
                                        item.get("description", ""), "Scrap",
                                        item.get("specification", ""), scr,
                                        item.get("unit", "Kg"), po["po_id"],
                                        f"{'Usable' if su else 'Not usable'}: {sn}",
                                    )
                                if recv_now > 0:
                                    st.success(f"Received {recv_now}. Total: {new_total}/{ordered}")
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
