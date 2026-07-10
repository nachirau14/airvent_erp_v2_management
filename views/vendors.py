"""Vendors — view, edit, delete material suppliers."""
import streamlit as st
import pandas as pd
from utils.db import (add_vendor, get_all_vendors, update_vendor, delete_vendor,
                       get_all_master_items)
from utils.ui_helpers import section_header, empty_state
from config import PAYMENT_TERMS


def render():
    st.markdown("# 👥 Material Vendors")
    st.markdown("*Manage suppliers — edit details, view linked items, or remove*")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📋 All Vendors", "➕ Add Vendor"])

    with tab2:
        section_header("Register New Vendor", "➕")
        with st.form("add_vendor_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Company Name *")
                contact_person = st.text_input("Contact Person *")
                phone = st.text_input("Phone *")
                email = st.text_input("Email")
            with c2:
                address = st.text_area("Address", height=80)
                gst_no = st.text_input("GST Number")
                payment_terms = st.selectbox("Default Payment Terms", PAYMENT_TERMS)

            if st.form_submit_button("✅ Register Vendor", use_container_width=True):
                if name and contact_person and phone:
                    v = add_vendor(name, contact_person, phone, email, address, gst_no, payment_terms)
                    st.success(f"Vendor **{name}** registered! ID: `{v['vendor_id']}`")
                    st.rerun()
                else:
                    st.error("Company Name, Contact Person, and Phone are required.")

    with tab1:
        vendors = get_all_vendors()
        if not vendors:
            empty_state("👥", "No vendors registered")
            return

        master_items = get_all_master_items()
        st.markdown(f"**{len(vendors)} vendor(s) registered**")

        for vendor in sorted(vendors, key=lambda x: x.get("name", "")):
            vid = vendor.get("vendor_id", "")
            vendor_items = [m for m in master_items if m.get("vendor", "").lower() == vendor["name"].lower()]

            with st.expander(f"🏢 **{vendor['name']}** — {vendor.get('contact_person', '')} | {len(vendor_items)} items ({vid})"):
                vc1, vc2 = st.columns(2)
                with vc1:
                    st.markdown(f"**Phone:** {vendor.get('phone', 'N/A')}")
                    st.markdown(f"**Email:** {vendor.get('email', 'N/A')}")
                    st.markdown(f"**GST:** {vendor.get('gst_no', 'N/A')}")
                with vc2:
                    st.markdown(f"**Address:** {vendor.get('address', 'N/A')}")
                    st.markdown(f"**Payment Terms:** {vendor.get('payment_terms', 'N/A')}")

                # Linked items
                if vendor_items:
                    with st.expander(f"📦 {len(vendor_items)} items in Master Catalog"):
                        df = pd.DataFrame(vendor_items)
                        cols = ["item_id", "item_name", "category", "specification", "unit", "price"]
                        available = [c for c in cols if c in df.columns]
                        if available:
                            st.dataframe(df[available], use_container_width=True, hide_index=True)

                # Edit
                with st.expander("✏️ Edit Vendor"):
                    with st.form(f"edit_ven_{vid}"):
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            e_name = st.text_input("Company Name", value=vendor.get("name", ""), key=f"en_{vid}")
                            e_contact = st.text_input("Contact Person", value=vendor.get("contact_person", ""), key=f"ec_{vid}")
                            e_phone = st.text_input("Phone", value=vendor.get("phone", ""), key=f"ep_{vid}")
                            e_email = st.text_input("Email", value=vendor.get("email", ""), key=f"ee_{vid}")
                        with ec2:
                            e_address = st.text_area("Address", value=vendor.get("address", ""), height=80, key=f"ea_{vid}")
                            e_gst = st.text_input("GST Number", value=vendor.get("gst_no", ""), key=f"eg_{vid}")
                            e_payment = st.selectbox("Payment Terms", PAYMENT_TERMS,
                                index=PAYMENT_TERMS.index(vendor.get("payment_terms", PAYMENT_TERMS[0]))
                                if vendor.get("payment_terms") in PAYMENT_TERMS else 0, key=f"ept_{vid}")
                        if st.form_submit_button("💾 Save Changes"):
                            update_vendor(vid, {
                                "name": e_name, "contact_person": e_contact, "phone": e_phone,
                                "email": e_email, "address": e_address, "gst_no": e_gst,
                                "payment_terms": e_payment,
                            })
                            st.success(f"Vendor **{e_name}** updated!")
                            st.rerun()

                # Delete
                st.markdown("")
                dc1, dc2 = st.columns([3, 1])
                with dc1:
                    del_confirm = st.checkbox(f"I confirm deletion of {vendor['name']}", key=f"vdc_{vid}")
                with dc2:
                    if st.button("🗑️ Delete Vendor", disabled=not del_confirm, key=f"vdb_{vid}"):
                        delete_vendor(vid)
                        st.success(f"Vendor **{vendor['name']}** deleted.")
                        st.rerun()
