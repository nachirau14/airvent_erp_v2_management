"""Service Purchase Orders Page - with semi-finished and scrap tracking."""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.db import (
    get_all_projects, get_all_service_vendors, get_service_vendor,
    get_service_vendor_services, create_service_po, get_all_service_pos,
    get_service_po_items, update_service_po_item, update_service_po_status,
    place_service_po_via_sqs,
)
from utils.ui_helpers import section_header, po_status_badge, format_currency, empty_state
from config import PAYMENT_TERMS, UNITS_OF_MEASURE, SERVICE_PO_STATUSES


FINISHING_STATUSES = ["Pending", "Semi-Finished", "Complete"]


def render():
    st.markdown("# 🛠️ Service Purchase Orders")
    st.markdown("*Manage subcontracted work orders with finishing and scrap tracking*")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📋 All Service POs", "➕ Create Service PO"])

    # ─── Create Service PO ────────────────────────────────────────
    with tab2:
        section_header("Create Service Purchase Order", "🆕")

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
            sel_proj = st.selectbox("Project *", list(proj_opts.keys()), key="spo_proj")
        with c2:
            sel_vendor = st.selectbox("Service Vendor *", list(vendor_opts.keys()), key="spo_vendor")

        project = proj_opts[sel_proj]
        vendor = vendor_opts[sel_vendor]

        c3, c4 = st.columns(2)
        with c3:
            payment_terms = st.selectbox("Payment Terms", PAYMENT_TERMS, key="spo_terms")
        with c4:
            expected_delivery = st.date_input("Expected Return Date", value=datetime.now().date() + timedelta(days=14), key="spo_ed")

        notes = st.text_area("Notes", key="spo_notes")

        # Service items
        if "spo_items" not in st.session_state:
            st.session_state.spo_items = []

        vendor_services = get_service_vendor_services(vendor["vendor_id"])
        if vendor_services:
            with st.expander("📂 Quick Add from Vendor Services"):
                for svc in vendor_services:
                    sc1, sc2, sc3, sc4 = st.columns([3, 1, 1, 1])
                    with sc1:
                        st.markdown(f"**{svc['service_name']}** — {svc.get('description', '')}")
                    with sc2:
                        st.caption(f"₹{svc.get('rate', 0)}/{svc.get('unit', '')}")
                    with sc3:
                        qty = st.number_input("Qty", min_value=0.0, step=1.0, key=f"sq_{svc['service_id']}", label_visibility="collapsed")
                    with sc4:
                        if st.button("Add", key=f"sadd_{svc['service_id']}"):
                            if qty > 0:
                                st.session_state.spo_items.append({
                                    "description": svc["service_name"],
                                    "specification": svc.get("description", ""),
                                    "quantity": qty,
                                    "unit": svc.get("unit", "Nos"),
                                    "unit_price": svc.get("rate", 0),
                                })
                                st.rerun()

        with st.form("spo_manual", clear_on_submit=True):
            mc1, mc2, mc3, mc4, mc5 = st.columns([3, 2, 1, 1, 1])
            with mc1:
                desc = st.text_input("Service Description *", key="spo_desc")
            with mc2:
                spec = st.text_input("Details", key="spo_spec")
            with mc3:
                qty = st.number_input("Qty", min_value=0.0, step=1.0, key="spo_qty")
            with mc4:
                unit = st.selectbox("Unit", UNITS_OF_MEASURE, key="spo_unit")
            with mc5:
                price = st.number_input("Rate ₹", min_value=0.0, step=0.5, key="spo_price")

            if st.form_submit_button("➕ Add Line Item"):
                if desc and qty > 0:
                    st.session_state.spo_items.append({
                        "description": desc, "specification": spec,
                        "quantity": qty, "unit": unit, "unit_price": price,
                    })
                    st.rerun()

        if st.session_state.spo_items:
            st.markdown("#### Current Service Items")
            for idx, item in enumerate(st.session_state.spo_items):
                ic1, ic2, ic3, ic4 = st.columns([4, 1, 1, 1])
                with ic1:
                    st.markdown(f"**{item['description']}** — {item.get('specification', '')}")
                with ic2:
                    st.caption(f"{item['quantity']} {item['unit']}")
                with ic3:
                    st.caption(format_currency(item['quantity'] * item['unit_price']))
                with ic4:
                    if st.button("🗑️", key=f"srem_{idx}"):
                        st.session_state.spo_items.pop(idx)
                        st.rerun()

            total = sum(i["quantity"] * i["unit_price"] for i in st.session_state.spo_items)
            st.markdown(f"### Total: {format_currency(total)}")

            c_save, c_place = st.columns(2)
            with c_save:
                if st.button("💾 Save as Draft", key="spo_draft", use_container_width=True):
                    po = create_service_po(
                        project["project_id"], vendor["vendor_id"], vendor["name"],
                        payment_terms, str(expected_delivery), st.session_state.spo_items, notes,
                    )
                    st.success(f"Service PO **{po['po_id']}** saved")
                    st.session_state.spo_items = []
                    st.rerun()
            with c_place:
                if st.button("📤 Save & Place Order", key="spo_place", use_container_width=True, type="primary"):
                    po = create_service_po(
                        project["project_id"], vendor["vendor_id"], vendor["name"],
                        payment_terms, str(expected_delivery), st.session_state.spo_items, notes,
                    )
                    place_service_po_via_sqs(
                        po["po_id"], vendor.get("email", ""), vendor["name"],
                        st.session_state.spo_items, total, payment_terms, str(expected_delivery),
                    )
                    st.success(f"Service PO **{po['po_id']}** placed via SQS!")
                    st.session_state.spo_items = []
                    st.rerun()

    # ─── All Service POs ──────────────────────────────────────────
    with tab1:
        all_pos = get_all_service_pos()
        if not all_pos:
            empty_state("🛠️", "No service POs yet")
            return

        for po in sorted(all_pos, key=lambda x: x.get("created_at", ""), reverse=True):
            status = po.get("status", "Draft")

            with st.expander(f"{po_status_badge(status)} **{po['po_id']}** — {po.get('vendor_name', '')} | {format_currency(po.get('total_amount', 0))}"):
                st.markdown(f"{po_status_badge(status)}", unsafe_allow_html=True)

                pc1, pc2, pc3 = st.columns(3)
                with pc1:
                    st.markdown(f"**Vendor:** {po.get('vendor_name', '')}")
                    st.markdown(f"**Payment:** {po.get('payment_terms', '')}")
                with pc2:
                    st.markdown(f"**Expected Return:** {po.get('expected_delivery', '')}")
                with pc3:
                    st.markdown(f"**Total:** {format_currency(po.get('total_amount', 0))}")

                st.markdown("---")
                st.markdown("#### Service Items — Receipt & Finishing Status")

                po_items = get_service_po_items(po["po_id"])
                all_received = True

                for item in po_items:
                    st.markdown(f"**{item.get('description', '')}** — {item.get('specification', '')}")

                    rc1, rc2, rc3 = st.columns(3)
                    with rc1:
                        st.caption(f"Ordered: {item.get('quantity', 0)} {item.get('unit', '')}")
                        qty_recv = st.number_input(
                            "Qty Received", min_value=0.0,
                            max_value=float(item.get("quantity", 0)),
                            value=float(item.get("quantity_received", 0)),
                            step=1.0, key=f"sr_{po['po_id']}_{item['item_id']}",
                        )
                        is_received = st.checkbox(
                            "Received", value=item.get("received", False),
                            key=f"sc_{po['po_id']}_{item['item_id']}",
                        )
                    with rc2:
                        finishing_status = st.selectbox(
                            "Finishing Status", FINISHING_STATUSES,
                            index=FINISHING_STATUSES.index(item.get("finishing_status", "Pending"))
                            if item.get("finishing_status") in FINISHING_STATUSES else 0,
                            key=f"fs_{po['po_id']}_{item['item_id']}",
                        )
                        finishing_comment = st.text_area(
                            "Finishing Comment",
                            value=item.get("finishing_comment", ""),
                            placeholder="e.g., Welding complete, grinding pending...",
                            key=f"fc_{po['po_id']}_{item['item_id']}",
                            height=80,
                        )
                    with rc3:
                        st.markdown("**Scrap Details**")
                        scrap_received = st.number_input(
                            "Scrap Qty", min_value=0.0, step=0.5,
                            value=float(item.get("scrap_received", 0)),
                            key=f"scr_{po['po_id']}_{item['item_id']}",
                        )
                        scrap_usable = st.checkbox(
                            "Usable Scrap?", value=item.get("scrap_usable", False),
                            key=f"su_{po['po_id']}_{item['item_id']}",
                        )
                        scrap_notes = st.text_input(
                            "Scrap Notes",
                            value=item.get("scrap_notes", ""),
                            placeholder="e.g., Partially usable 2mm sheet offcuts",
                            key=f"sn_{po['po_id']}_{item['item_id']}",
                        )

                    if not is_received:
                        all_received = False

                    if st.button("💾 Update Item", key=f"supd_{po['po_id']}_{item['item_id']}"):
                        update_service_po_item(
                            po["po_id"], item["item_id"], qty_recv, is_received,
                            finishing_status, finishing_comment,
                            scrap_received, scrap_usable, scrap_notes,
                        )
                        st.success("Item updated!")
                        st.rerun()

                    st.markdown("<hr style='margin:8px 0;border-color:#f1f5f9'>", unsafe_allow_html=True)

                # Status updates
                if all_received and po_items and status != "Complete":
                    if st.button("✅ Mark Complete", key=f"scomp_{po['po_id']}", type="primary"):
                        update_service_po_status(po["po_id"], "Complete")
                        st.success("Service PO marked as Complete!")
                        st.rerun()

                if status == "Draft":
                    if st.button("📤 Place Order", key=f"splace_{po['po_id']}", type="primary"):
                        vendor = get_service_vendor(po.get("vendor_id", ""))
                        place_service_po_via_sqs(
                            po["po_id"], vendor.get("email", "") if vendor else "",
                            po.get("vendor_name", ""), [], po.get("total_amount", 0),
                            po.get("payment_terms", ""), po.get("expected_delivery", ""),
                        )
                        st.success("Service PO placed!")
                        st.rerun()
