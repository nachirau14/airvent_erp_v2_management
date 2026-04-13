"""Order Staging — Review and send POs grouped by vendor from BOQ."""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.db import (get_staged_orders, get_staged_order, update_staged_order_items,
                       update_staged_order_status, delete_staged_order,
                       get_all_projects, get_all_vendors, get_vendor,
                       create_raw_material_po, update_raw_material_po_status)
from utils.ui_helpers import section_header, po_status_badge, format_currency, empty_state
from config import PAYMENT_TERMS


def render():
    st.markdown("# 🚀 Order Staging")
    st.markdown("*Review BOQ-generated POs, adjust quantities and rates, then place all orders*")
    st.markdown("---")

    projects = get_all_projects()
    if not projects:
        empty_state("🚀", "No projects yet")
        return

    proj_opts = {f"{p['name']} ({p['project_id']})": p for p in projects}
    sel_proj = st.selectbox("Select Project", list(proj_opts.keys()), key="stg_proj")
    project = proj_opts[sel_proj]

    staged = get_staged_orders(project["project_id"])
    staged = [s for s in staged if s.get("status") != "Sent"]

    if not staged:
        empty_state("🚀", "No staged orders for this project",
                     "Go to Projects & BOQ → click 'Stage Purchase Orders from BOQ'")
        return

    st.success(f"**{len(staged)} vendor PO(s)** staged and ready for review")
    st.markdown("---")

    # Vendor registry for linking
    vendors = get_all_vendors()
    vendor_by_name = {v["name"]: v for v in vendors}

    for order in sorted(staged, key=lambda x: x.get("vendor_name", "")):
        vendor_name = order.get("vendor_name", "Unknown")
        items = order.get("items", [])
        total = order.get("total_amount", 0)
        stage_id = order["stage_id"]

        with st.expander(f"🏢 **{vendor_name}** — {len(items)} items — {format_currency(total)} ({stage_id})", expanded=True):
            st.markdown(f"**Status:** {po_status_badge(order.get('status', 'Staged'))}", unsafe_allow_html=True)

            # Editable items table
            st.markdown("#### Edit Quantities & Rates")
            updated_items = []
            new_total = 0

            for idx, item in enumerate(items):
                ic1, ic2, ic3, ic4, ic5 = st.columns([3, 1, 1, 1, 1])
                with ic1:
                    st.markdown(f"**{item.get('item_name', item.get('description', ''))}**")
                    st.caption(f"{item.get('specification', '')} | {item.get('category', '')}")
                with ic2:
                    new_qty = st.number_input("Qty", value=float(item.get("quantity", 0)),
                                              min_value=0.0, step=0.5, key=f"sq_{stage_id}_{idx}")
                with ic3:
                    st.caption(item.get("unit", ""))
                with ic4:
                    new_rate = st.number_input("Rate ₹", value=float(item.get("rate", item.get("unit_price", 0))),
                                               min_value=0.0, step=0.5, key=f"sr_{stage_id}_{idx}")
                with ic5:
                    line_total = new_qty * new_rate
                    st.markdown(f"**{format_currency(line_total)}**")
                    new_total += line_total

                updated_item = dict(item)
                updated_item["quantity"] = new_qty
                updated_item["rate"] = new_rate
                updated_item["unit_price"] = new_rate
                updated_item["total"] = line_total
                updated_item["total_price"] = line_total
                updated_items.append(updated_item)

            st.markdown(f"### Total: {format_currency(new_total)}")

            # Save changes
            if st.button("💾 Save Changes", key=f"save_{stage_id}"):
                update_staged_order_items(stage_id, updated_items, new_total)
                st.success("Quantities and rates updated!")
                st.rerun()

            st.markdown("---")

            # Place PO
            st.markdown("#### Place Purchase Order")
            pc1, pc2 = st.columns(2)
            with pc1:
                vendor_match = vendor_by_name.get(vendor_name)
                payment_terms = st.selectbox("Payment Terms", PAYMENT_TERMS,
                    index=PAYMENT_TERMS.index(vendor_match.get("payment_terms", PAYMENT_TERMS[0]))
                    if vendor_match and vendor_match.get("payment_terms") in PAYMENT_TERMS else 0,
                    key=f"pt_{stage_id}")
            with pc2:
                exp_delivery = st.date_input("Expected Delivery",
                    value=datetime.now().date() + timedelta(days=7), key=f"ed_{stage_id}")

            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("📤 Place PO", key=f"place_{stage_id}", type="primary", use_container_width=True):
                    vendor_id = vendor_match["vendor_id"] if vendor_match else ""
                    po_items = [{"description": i.get("item_name", i.get("description", "")),
                                 "specification": i.get("specification", ""),
                                 "quantity": i["quantity"], "unit": i.get("unit", "Nos"),
                                 "unit_price": i.get("rate", i.get("unit_price", 0))}
                                for i in updated_items if i["quantity"] > 0]
                    if po_items:
                        po = create_raw_material_po(project["project_id"], vendor_id, vendor_name,
                                                     payment_terms, str(exp_delivery), po_items)
                        update_raw_material_po_status(po["po_id"], "Placed")
                        update_staged_order_status(stage_id, "Sent")
                        st.success(f"PO **{po['po_id']}** placed for **{vendor_name}**!")
                        st.rerun()
                    else:
                        st.error("No items with quantity > 0")
            with bc2:
                if st.button("🗑️ Discard", key=f"discard_{stage_id}", use_container_width=True):
                    delete_staged_order(stage_id)
                    st.success("Staged order discarded")
                    st.rerun()

    # Place ALL button
    st.markdown("---")
    st.markdown("### 🚀 Place All Orders at Once")
    st.warning("This will place POs for ALL staged vendors above with current quantities and rates.")
    if st.button("📤 Place All POs", type="primary", use_container_width=True, key="place_all"):
        placed = 0
        for order in staged:
            if order.get("status") == "Sent":
                continue
            vendor_name = order.get("vendor_name", "")
            vendor_match = vendor_by_name.get(vendor_name)
            vendor_id = vendor_match["vendor_id"] if vendor_match else ""
            payment = vendor_match.get("payment_terms", PAYMENT_TERMS[0]) if vendor_match else PAYMENT_TERMS[0]
            items = order.get("items", [])
            po_items = [{"description": i.get("item_name", i.get("description", "")),
                         "specification": i.get("specification", ""),
                         "quantity": i["quantity"], "unit": i.get("unit", "Nos"),
                         "unit_price": i.get("rate", i.get("unit_price", 0))}
                        for i in items if i.get("quantity", 0) > 0]
            if po_items:
                po = create_raw_material_po(project["project_id"], vendor_id, vendor_name,
                                             payment, str(datetime.now().date() + timedelta(days=7)), po_items)
                update_raw_material_po_status(po["po_id"], "Placed")
                update_staged_order_status(order["stage_id"], "Sent")
                placed += 1
        st.success(f"Placed **{placed}** purchase orders!")
        st.rerun()
