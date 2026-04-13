"""Raw Material Purchase Orders Page."""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.db import (
    get_all_projects, get_all_vendors, get_vendor, get_vendor_items,
    get_boq_items, create_raw_material_po, get_all_raw_material_pos,
    get_raw_material_po_items, update_po_item_receipt,
    update_raw_material_po_status, place_po_via_sqs,
    update_inventory_raw_qty, add_inventory_raw,
)
from utils.ui_helpers import section_header, po_status_badge, format_currency, empty_state
from config import PAYMENT_TERMS, UNITS_OF_MEASURE, PO_STATUSES


def render():
    st.markdown("# 📦 Raw Material Purchase Orders")
    st.markdown("*Create, track, and receive material purchase orders*")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📋 All POs", "➕ Create PO"])

    # ─── Create PO ────────────────────────────────────────────────
    with tab2:
        section_header("Create Raw Material Purchase Order", "🆕")

        projects = get_all_projects()
        vendors = get_all_vendors()

        if not projects:
            st.warning("Create a project first before placing POs.")
            return
        if not vendors:
            st.warning("Register vendors first before placing POs.")
            return

        project_options = {f"{p['name']} ({p['project_id']})": p for p in projects}
        vendor_options = {f"{v['name']} ({v['vendor_id']})": v for v in vendors}

        c1, c2 = st.columns(2)
        with c1:
            selected_project = st.selectbox("Project *", list(project_options.keys()))
        with c2:
            selected_vendor = st.selectbox("Vendor *", list(vendor_options.keys()))

        project = project_options[selected_project]
        vendor = vendor_options[selected_vendor]

        c3, c4 = st.columns(2)
        with c3:
            payment_terms = st.selectbox("Payment Terms", PAYMENT_TERMS,
                                         index=PAYMENT_TERMS.index(vendor.get("payment_terms", PAYMENT_TERMS[0]))
                                         if vendor.get("payment_terms") in PAYMENT_TERMS else 0)
        with c4:
            expected_delivery = st.date_input("Expected Delivery", value=datetime.now().date() + timedelta(days=7))

        notes = st.text_area("Notes", placeholder="Any special instructions...")

        # Show vendor items for quick selection
        vendor_items = get_vendor_items(vendor["vendor_id"])
        boq_items = get_boq_items(project["project_id"])

        st.markdown("#### PO Line Items")
        st.caption("Add items to this purchase order")

        if "po_items" not in st.session_state:
            st.session_state.po_items = []

        # Quick add from vendor catalog
        if vendor_items:
            with st.expander("📂 Quick Add from Vendor Catalog"):
                for vi in vendor_items:
                    qc1, qc2, qc3, qc4 = st.columns([3, 1, 1, 1])
                    with qc1:
                        st.markdown(f"**{vi['item_name']}** — {vi.get('specification', '')}")
                    with qc2:
                        st.caption(f"₹{vi.get('current_price', 0)}/{vi.get('unit', '')}")
                    with qc3:
                        qty = st.number_input("Qty", min_value=0.0, step=1.0, key=f"viq_{vi['item_id']}", label_visibility="collapsed")
                    with qc4:
                        if st.button("Add", key=f"vadd_{vi['item_id']}"):
                            if qty > 0:
                                st.session_state.po_items.append({
                                    "description": vi["item_name"],
                                    "specification": vi.get("specification", ""),
                                    "quantity": qty,
                                    "unit": vi.get("unit", "Kg"),
                                    "unit_price": vi.get("current_price", 0),
                                })
                                st.rerun()

        # Manual add
        with st.form("manual_item", clear_on_submit=True):
            mc1, mc2, mc3, mc4, mc5 = st.columns([3, 2, 1, 1, 1])
            with mc1:
                desc = st.text_input("Description *", key="mi_desc")
            with mc2:
                spec = st.text_input("Specification", key="mi_spec")
            with mc3:
                qty = st.number_input("Qty *", min_value=0.0, step=1.0, key="mi_qty")
            with mc4:
                unit = st.selectbox("Unit", UNITS_OF_MEASURE, key="mi_unit")
            with mc5:
                price = st.number_input("Rate ₹", min_value=0.0, step=0.5, key="mi_price")

            if st.form_submit_button("➕ Add Line Item"):
                if desc and qty > 0:
                    st.session_state.po_items.append({
                        "description": desc, "specification": spec,
                        "quantity": qty, "unit": unit, "unit_price": price,
                    })
                    st.rerun()

        # Display current items
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

            c_save, c_place = st.columns(2)
            with c_save:
                if st.button("💾 Save as Draft", use_container_width=True):
                    po = create_raw_material_po(
                        project["project_id"], vendor["vendor_id"], vendor["name"],
                        payment_terms, str(expected_delivery), st.session_state.po_items, notes,
                    )
                    st.success(f"PO **{po['po_id']}** saved as Draft")
                    st.session_state.po_items = []
                    st.rerun()
            with c_place:
                if st.button("📤 Save & Place Order (via SQS)", use_container_width=True, type="primary"):
                    po = create_raw_material_po(
                        project["project_id"], vendor["vendor_id"], vendor["name"],
                        payment_terms, str(expected_delivery), st.session_state.po_items, notes,
                    )
                    place_po_via_sqs(
                        po["po_id"], vendor.get("email", ""), vendor["name"],
                        st.session_state.po_items, total, payment_terms, str(expected_delivery),
                    )
                    st.success(f"PO **{po['po_id']}** placed! Email queued via SQS.")
                    st.session_state.po_items = []
                    st.rerun()
        else:
            st.info("No items added yet. Use the vendor catalog or manual entry above.")

    # ─── All POs ──────────────────────────────────────────────────
    with tab1:
        all_pos = get_all_raw_material_pos()
        if not all_pos:
            empty_state("📦", "No purchase orders yet", "Create your first PO in the 'Create PO' tab")
            return

        # Filter
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            status_filter = st.multiselect("Filter by Status", PO_STATUSES)
        with filter_col2:
            proj_filter = st.selectbox("Filter by Project", ["All"] + [p.get("name", "") for p in get_all_projects()])

        filtered = all_pos
        if status_filter:
            filtered = [po for po in filtered if po.get("status") in status_filter]
        if proj_filter != "All":
            proj_ids = [p["project_id"] for p in get_all_projects() if p.get("name") == proj_filter]
            if proj_ids:
                filtered = [po for po in filtered if po.get("project_id") in proj_ids]

        for po in sorted(filtered, key=lambda x: x.get("created_at", ""), reverse=True):
            status = po.get("status", "Draft")

            # Color-coded border
            border_color = {"Draft": "#6b7280", "Placed": "#2563eb", "Partially Received": "#d97706",
                            "Complete": "#16a34a", "Cancelled": "#dc2626"}.get(status, "#6b7280")

            with st.expander(f"{po_status_badge(status)} **{po['po_id']}** — {po.get('vendor_name', '')} | {format_currency(po.get('total_amount', 0))}", expanded=False):
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
                    st.markdown(f"**Email Sent:** {'✅' if po.get('email_sent') else '❌'}")

                st.markdown("---")

                # PO Items with receipt tracking
                po_items = get_raw_material_po_items(po["po_id"])
                if po_items:
                    st.markdown("#### Line Items & Receipt")
                    all_received = True

                    for item in po_items:
                        rc1, rc2, rc3, rc4, rc5 = st.columns([3, 1, 1, 1, 1])
                        with rc1:
                            st.markdown(f"**{item.get('description', '')}**")
                            st.caption(item.get("specification", ""))
                        with rc2:
                            st.caption(f"Ordered: {item.get('quantity', 0)} {item.get('unit', '')}")
                        with rc3:
                            st.caption(f"Received: {item.get('quantity_received', 0)}")
                        with rc4:
                            qty_recv = st.number_input(
                                "Recv Qty", min_value=0.0,
                                max_value=float(item.get("quantity", 0)),
                                value=float(item.get("quantity_received", 0)),
                                step=1.0, key=f"recv_{po['po_id']}_{item['item_id']}",
                                label_visibility="collapsed",
                            )
                        with rc5:
                            is_received = st.checkbox(
                                "✅", value=item.get("received", False),
                                key=f"chk_{po['po_id']}_{item['item_id']}",
                            )

                        if not is_received:
                            all_received = False

                        # Save receipt update
                        if qty_recv != item.get("quantity_received", 0) or is_received != item.get("received", False):
                            if st.button("Save", key=f"save_recv_{po['po_id']}_{item['item_id']}"):
                                update_po_item_receipt(po["po_id"], item["item_id"], qty_recv, is_received)
                                # Add to inventory when received
                                if is_received and qty_recv > 0:
                                    add_inventory_raw(
                                        item.get("description", "Unknown"),
                                        "Received", "PO Receipt",
                                        item.get("specification", ""),
                                        qty_recv, item.get("unit", "Kg"),
                                    )
                                st.success("Receipt updated!")
                                st.rerun()

                    # Auto-update PO status
                    any_received = any(i.get("quantity_received", 0) > 0 for i in po_items)
                    if all_received and status != "Complete":
                        if st.button("✅ Mark PO Complete", key=f"complete_{po['po_id']}", type="primary"):
                            update_raw_material_po_status(po["po_id"], "Complete")
                            st.success("PO marked as Complete!")
                            st.rerun()
                    elif any_received and status not in ("Partially Received", "Complete"):
                        if st.button("🔄 Mark Partially Received", key=f"partial_{po['po_id']}"):
                            update_raw_material_po_status(po["po_id"], "Partially Received")
                            st.rerun()

                # Place draft PO
                if status == "Draft":
                    if st.button("📤 Place Order", key=f"place_{po['po_id']}", type="primary"):
                        vendor = get_vendor(po.get("vendor_id", ""))
                        items_for_sqs = [{"description": i.get("description", ""), "quantity": i.get("quantity", 0),
                                          "unit": i.get("unit", ""), "unit_price": i.get("unit_price", 0),
                                          "total_price": i.get("total_price", 0)} for i in po_items]
                        place_po_via_sqs(
                            po["po_id"], vendor.get("email", "") if vendor else "",
                            po.get("vendor_name", ""), items_for_sqs,
                            po.get("total_amount", 0), po.get("payment_terms", ""),
                            po.get("expected_delivery", ""),
                        )
                        st.success("PO placed via SQS!")
                        st.rerun()
