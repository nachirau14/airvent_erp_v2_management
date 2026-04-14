"""Order Staging — review/adjust/place POs grouped by vendor from BOQ."""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.db import (get_staged_orders, update_staged_order_items,
                       update_staged_order_status, delete_staged_order,
                       get_all_projects, get_all_vendors,
                       create_raw_material_po, update_raw_material_po_status,
                       generate_po_pdf, update_po_pdf_key, get_po_pdf_download)
from utils.ui_helpers import section_header, format_currency, empty_state
from config import PAYMENT_TERMS


def render():
    st.markdown("# 🚀 Order Staging")
    st.markdown("*Review BOQ-generated POs, adjust quantities and rates, then place orders*")
    st.markdown("---")

    projects = get_all_projects()
    if not projects:
        empty_state("🚀", "No projects yet"); return

    proj_opts = {f"{p['name']} ({p['project_id']})": p for p in projects}
    sel_proj = st.selectbox("Select Project", list(proj_opts.keys()), key="stg_proj")
    project = proj_opts[sel_proj]

    staged = get_staged_orders(project["project_id"])
    staged = [s for s in staged if s.get("status") != "Sent"]

    if not staged:
        empty_state("🚀", "No staged orders for this project",
                     "Go to Projects & BOQ → click 'Stage Purchase Orders from BOQ'"); return

    st.success(f"**{len(staged)} vendor PO(s)** ready for review")
    st.markdown("---")

    vendors = get_all_vendors()
    vendor_by_name = {v["name"]: v for v in vendors}

    for order in sorted(staged, key=lambda x: x.get("vendor_name", "")):
        vendor_name = order.get("vendor_name", "Unknown")
        line_items = order.get("line_items", order.get("items", []))  # backwards compat
        total = order.get("total_amount", 0)
        stage_id = order["stage_id"]

        with st.expander(f"🏢 **{vendor_name}** — {len(line_items)} items — {format_currency(total)}", expanded=True):
            st.markdown("#### Edit Quantities & Rates")
            updated = []
            new_total = 0

            for idx, item in enumerate(line_items):
                ic1, ic2, ic3, ic4, ic5 = st.columns([3, 1, 1, 1, 1])
                with ic1:
                    st.markdown(f"**{item.get('item_name', item.get('description', ''))}**")
                    st.caption(f"{item.get('specification', '')} | {item.get('category', '')}")
                with ic2:
                    nq = st.number_input("Qty", value=int(item.get("quantity", 0)),
                        min_value=0, step=1, key=f"sq_{stage_id}_{idx}")
                with ic3:
                    st.caption(item.get("unit", ""))
                with ic4:
                    nr = st.number_input("Rate ₹", value=float(item.get("rate", item.get("unit_price", 0))),
                        min_value=0.0, step=0.5, key=f"sr_{stage_id}_{idx}")
                with ic5:
                    lt = nq * nr
                    st.markdown(f"**{format_currency(lt)}**")
                    new_total += lt

                ui = dict(item)
                ui["quantity"] = nq
                ui["rate"] = nr
                ui["unit_price"] = nr
                ui["total"] = lt
                ui["total_price"] = lt
                updated.append(ui)

            st.markdown(f"### Total: {format_currency(new_total)}")

            if st.button("💾 Save Changes", key=f"save_{stage_id}"):
                update_staged_order_items(stage_id, updated, new_total)
                st.success("Saved!"); st.rerun()

            st.markdown("---")
            pc1, pc2 = st.columns(2)
            with pc1:
                vm = vendor_by_name.get(vendor_name)
                pt = st.selectbox("Payment Terms", PAYMENT_TERMS,
                    index=PAYMENT_TERMS.index(vm.get("payment_terms", PAYMENT_TERMS[0]))
                    if vm and vm.get("payment_terms") in PAYMENT_TERMS else 0, key=f"pt_{stage_id}")
            with pc2:
                ed = st.date_input("Expected Delivery", value=datetime.now().date() + timedelta(days=7), key=f"ed_{stage_id}")

            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("📤 Place PO", key=f"pl_{stage_id}", type="primary", use_container_width=True):
                    vid = vm["vendor_id"] if vm else ""
                    po_items = [{"description": i.get("item_name", i.get("description", "")),
                                 "specification": i.get("specification", ""),
                                 "quantity": i["quantity"], "unit": i.get("unit", "Nos"),
                                 "unit_price": i.get("rate", i.get("unit_price", 0))}
                                for i in updated if i["quantity"] > 0]
                    if po_items:
                        po = create_raw_material_po(project["project_id"], vid, vendor_name, pt, str(ed), po_items)
                        update_raw_material_po_status(po["po_id"], "Placed")
                        # Generate PDF
                        pdf_key = generate_po_pdf(po, po_items, "Material")
                        if pdf_key:
                            update_po_pdf_key(po["po_id"], pdf_key)
                        update_staged_order_status(stage_id, "Sent")
                        st.success(f"PO **{po['po_id']}** placed for **{vendor_name}**!")
                        st.rerun()
            with bc2:
                if st.button("🗑️ Discard", key=f"dis_{stage_id}", use_container_width=True):
                    delete_staged_order(stage_id); st.success("Discarded"); st.rerun()

    st.markdown("---")
    st.markdown("### 🚀 Place All Orders at Once")
    if st.button("📤 Place All POs", type="primary", use_container_width=True, key="place_all"):
        placed = 0
        for order in staged:
            if order.get("status") == "Sent": continue
            vn = order.get("vendor_name", "")
            vm = vendor_by_name.get(vn)
            vid = vm["vendor_id"] if vm else ""
            pay = vm.get("payment_terms", PAYMENT_TERMS[0]) if vm else PAYMENT_TERMS[0]
            li = order.get("line_items", order.get("items", []))
            po_items = [{"description": i.get("item_name", i.get("description", "")),
                         "specification": i.get("specification", ""),
                         "quantity": i["quantity"], "unit": i.get("unit", "Nos"),
                         "unit_price": i.get("rate", i.get("unit_price", 0))}
                        for i in li if i.get("quantity", 0) > 0]
            if po_items:
                po = create_raw_material_po(project["project_id"], vid, vn, pay,
                    str(datetime.now().date() + timedelta(days=7)), po_items)
                update_raw_material_po_status(po["po_id"], "Placed")
                pdf_key = generate_po_pdf(po, po_items, "Material")
                if pdf_key: update_po_pdf_key(po["po_id"], pdf_key)
                update_staged_order_status(order["stage_id"], "Sent")
                placed += 1
        st.success(f"Placed **{placed}** POs!"); st.rerun()
