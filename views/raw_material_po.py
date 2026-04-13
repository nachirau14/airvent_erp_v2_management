"""Raw Material Purchase Orders Page — uses master items for item selection."""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.db import (
    get_all_projects, get_all_vendors, get_vendor, get_all_master_items,
    create_raw_material_po, get_all_raw_material_pos,
    get_raw_material_po_items, update_po_item_receipt,
    update_raw_material_po_status, place_po_via_sqs,
    add_inventory_item,
)
from utils.ui_helpers import section_header, po_status_badge, format_currency, empty_state
from config import PAYMENT_TERMS, PO_STATUSES


def render():
    st.markdown("# 📦 Purchase Orders")
    st.markdown("*Create, track, and receive material purchase orders*")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📋 All POs", "➕ Create PO"])

    with tab2:
        section_header("Create Purchase Order", "🆕")

        projects = get_all_projects()
        vendors = get_all_vendors()
        if not projects:
            st.warning("Create a project first."); return
        if not vendors:
            st.warning("Register vendors first."); return

        proj_opts = {f"{p['name']} ({p['project_id']})": p for p in projects}
        vendor_opts = {f"{v['name']} ({v['vendor_id']})": v for v in vendors}

        c1, c2 = st.columns(2)
        with c1: selected_project = st.selectbox("Project *", list(proj_opts.keys()))
        with c2: selected_vendor = st.selectbox("Vendor *", list(vendor_opts.keys()))

        project = proj_opts[selected_project]
        vendor = vendor_opts[selected_vendor]

        c3, c4 = st.columns(2)
        with c3:
            payment_terms = st.selectbox("Payment Terms", PAYMENT_TERMS,
                index=PAYMENT_TERMS.index(vendor.get("payment_terms", PAYMENT_TERMS[0]))
                if vendor.get("payment_terms") in PAYMENT_TERMS else 0)
        with c4:
            expected_delivery = st.date_input("Expected Delivery", value=datetime.now().date() + timedelta(days=7))

        notes = st.text_area("Notes", placeholder="Special instructions...")

        if "po_items" not in st.session_state:
            st.session_state.po_items = []

        # Quick add from master items for this vendor
        master_items = get_all_master_items()
        vendor_master = [m for m in master_items if m.get("vendor", "").lower() == vendor["name"].lower()]

        if vendor_master:
            with st.expander(f"📂 Quick Add from Master Catalog ({len(vendor_master)} items for {vendor['name']})"):
                for mi in vendor_master[:30]:
                    qc1, qc2, qc3, qc4 = st.columns([3, 1, 1, 1])
                    with qc1:
                        st.markdown(f"**{mi['item_name']}** — {mi.get('specification', '')}")
                    with qc2:
                        price = mi.get("revised_price", 0) or mi.get("price", 0)
                        st.caption(f"₹{price}/{mi.get('unit', '')}")
                    with qc3:
                        qty = st.number_input("Qty", min_value=0.0, step=1.0, key=f"viq_{mi['item_id']}", label_visibility="collapsed")
                    with qc4:
                        if st.button("Add", key=f"vadd_{mi['item_id']}"):
                            if qty > 0:
                                st.session_state.po_items.append({
                                    "description": mi["item_name"],
                                    "specification": mi.get("specification", ""),
                                    "quantity": qty,
                                    "unit": mi.get("unit", "Kg"),
                                    "unit_price": price,
                                })
                                st.rerun()

        # Manual add
        with st.form("manual_item", clear_on_submit=True):
            mc1, mc2, mc3, mc4, mc5 = st.columns([3, 2, 1, 1, 1])
            with mc1: desc = st.text_input("Description *", key="mi_desc")
            with mc2: spec = st.text_input("Specification", key="mi_spec")
            with mc3: qty = st.number_input("Qty *", min_value=0.0, step=1.0, key="mi_qty")
            with mc4: unit = st.selectbox("Unit", ["Kg", "Nos", "Meters", "Sets", "Lots", "Pcs"], key="mi_unit")
            with mc5: price = st.number_input("Rate ₹", min_value=0.0, step=0.5, key="mi_price")

            if st.form_submit_button("➕ Add Line Item"):
                if desc and qty > 0:
                    st.session_state.po_items.append({"description": desc, "specification": spec,
                        "quantity": qty, "unit": unit, "unit_price": price})
                    st.rerun()

        if st.session_state.po_items:
            st.markdown("#### Current PO Items")
            for idx, item in enumerate(st.session_state.po_items):
                ic1, ic2, ic3, ic4 = st.columns([4, 1, 1, 1])
                with ic1: st.markdown(f"**{item['description']}** — {item.get('specification', '')}")
                with ic2: st.caption(f"{item['quantity']} {item['unit']}")
                with ic3: st.caption(format_currency(item['quantity'] * item['unit_price']))
                with ic4:
                    if st.button("🗑️", key=f"rem_{idx}"):
                        st.session_state.po_items.pop(idx); st.rerun()

            total = sum(i["quantity"] * i["unit_price"] for i in st.session_state.po_items)
            st.markdown(f"### Total: {format_currency(total)}")

            c_save, c_place = st.columns(2)
            with c_save:
                if st.button("💾 Save as Draft", use_container_width=True):
                    po = create_raw_material_po(project["project_id"], vendor["vendor_id"], vendor["name"],
                        payment_terms, str(expected_delivery), st.session_state.po_items, notes)
                    st.success(f"PO **{po['po_id']}** saved as Draft")
                    st.session_state.po_items = []; st.rerun()
            with c_place:
                if st.button("📤 Save & Place Order", use_container_width=True, type="primary"):
                    po = create_raw_material_po(project["project_id"], vendor["vendor_id"], vendor["name"],
                        payment_terms, str(expected_delivery), st.session_state.po_items, notes)
                    place_po_via_sqs(po["po_id"], vendor.get("email", ""), vendor["name"],
                        st.session_state.po_items, total, payment_terms, str(expected_delivery))
                    st.success(f"PO **{po['po_id']}** placed!")
                    st.session_state.po_items = []; st.rerun()

    # ─── All POs ──────────────────────────────────────────────
    with tab1:
        all_pos = get_all_raw_material_pos()
        if not all_pos:
            empty_state("📦", "No purchase orders yet"); return

        for po in sorted(all_pos, key=lambda x: x.get("created_at", ""), reverse=True):
            status = po.get("status", "Draft")
            with st.expander(f"{po_status_badge(status)} **{po['po_id']}** — {po.get('vendor_name', '')} | {format_currency(po.get('total_amount', 0))}"):
                st.markdown(f"{po_status_badge(status)}", unsafe_allow_html=True)
                pc1, pc2, pc3 = st.columns(3)
                with pc1:
                    st.markdown(f"**Vendor:** {po.get('vendor_name', '')}")
                    st.markdown(f"**Payment:** {po.get('payment_terms', '')}")
                with pc2:
                    st.markdown(f"**Expected Delivery:** {po.get('expected_delivery', '')}")
                    st.markdown(f"**Created:** {po.get('created_at', '')[:10]}")
                with pc3:
                    st.markdown(f"**Total:** {format_currency(po.get('total_amount', 0))}")

                st.markdown("---")
                po_items = get_raw_material_po_items(po["po_id"])
                if po_items:
                    all_received = True
                    for item in po_items:
                        rc1, rc2, rc3, rc4, rc5 = st.columns([3, 1, 1, 1, 1])
                        with rc1:
                            st.markdown(f"**{item.get('description', '')}**")
                            st.caption(item.get("specification", ""))
                        with rc2: st.caption(f"Ordered: {item.get('quantity', 0)} {item.get('unit', '')}")
                        with rc3: st.caption(f"Received: {item.get('quantity_received', 0)}")
                        with rc4:
                            qty_recv = st.number_input("Recv", min_value=0.0, max_value=float(item.get("quantity", 0)),
                                value=float(item.get("quantity_received", 0)), step=1.0,
                                key=f"recv_{po['po_id']}_{item['item_id']}", label_visibility="collapsed")
                        with rc5:
                            is_received = st.checkbox("✅", value=item.get("received", False),
                                key=f"chk_{po['po_id']}_{item['item_id']}")
                        if not is_received: all_received = False

                        if qty_recv != item.get("quantity_received", 0) or is_received != item.get("received", False):
                            if st.button("Save", key=f"sr_{po['po_id']}_{item['item_id']}"):
                                update_po_item_receipt(po["po_id"], item["item_id"], qty_recv, is_received)
                                if is_received and qty_recv > 0:
                                    add_inventory_item("", item.get("description", ""), po.get("vendor_name", ""),
                                        "Received", "PO Receipt", item.get("specification", ""),
                                        qty_recv, item.get("unit", "Kg"), "Main Store", item.get("unit_price", 0))
                                st.success("Updated!"); st.rerun()

                    if all_received and po_items and status != "Complete":
                        if st.button("✅ Mark Complete", key=f"comp_{po['po_id']}", type="primary"):
                            update_raw_material_po_status(po["po_id"], "Complete"); st.rerun()

                if status == "Draft":
                    if st.button("📤 Place Order", key=f"place_{po['po_id']}", type="primary"):
                        place_po_via_sqs(po["po_id"], "", po.get("vendor_name", ""), [], 0, "", "")
                        st.success("PO placed!"); st.rerun()
