"""Service Vendors — view, edit, delete subcontractors."""
import streamlit as st
import pandas as pd
from utils.db import (add_service_vendor, get_all_service_vendors,
                       update_service_vendor, delete_service_vendor,
                       add_service_vendor_service, get_service_vendor_services)
from utils.ui_helpers import section_header, empty_state
from config import PAYMENT_TERMS, UNITS_OF_MEASURE


SERVICE_TYPES = [
    "Laser Cutting", "Bending", "Rolling", "CNC Machining", "Turning",
    "Milling", "Surface Treatment", "Galvanizing", "Powder Coating",
    "Zinc Plating", "Sandblasting", "Heat Treatment", "Welding",
    "Assembly", "Testing", "Custom",
]


def render():
    st.markdown("# 🔧 Service Vendors")
    st.markdown("*Manage subcontractors — edit details, services, or remove*")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📋 All Service Vendors", "➕ Add Service Vendor"])

    with tab2:
        section_header("Register Service Vendor", "➕")
        with st.form("add_svc_vendor", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Company Name *")
                contact_person = st.text_input("Contact Person *")
                phone = st.text_input("Phone *")
                email = st.text_input("Email *")
            with c2:
                address = st.text_area("Address *", height=80)
                gst_no = st.text_input("GST Number")
                payment_terms = st.selectbox("Payment Terms", PAYMENT_TERMS)

            if st.form_submit_button("✅ Register Service Vendor", use_container_width=True):
                if name and contact_person and phone and email and address:
                    v = add_service_vendor(name, contact_person, phone, email, address, gst_no, payment_terms)
                    st.success(f"Service Vendor **{name}** registered! ID: `{v['vendor_id']}`")
                    st.rerun()
                else:
                    st.error("All required fields must be filled.")

    with tab1:
        vendors = get_all_service_vendors()
        if not vendors:
            empty_state("🔧", "No service vendors registered")
            return

        st.markdown(f"**{len(vendors)} service vendor(s) registered**")

        for vendor in sorted(vendors, key=lambda x: x.get("name", "")):
            vid = vendor.get("vendor_id", "")

            with st.expander(f"🏭 **{vendor['name']}** — {vendor.get('contact_person', '')} ({vid})"):
                vc1, vc2 = st.columns(2)
                with vc1:
                    st.markdown(f"**Contact:** {vendor.get('contact_person', '')}")
                    st.markdown(f"**Phone:** {vendor.get('phone', '')}")
                    st.markdown(f"**Email:** {vendor.get('email', '')}")
                with vc2:
                    st.markdown(f"**Address:** {vendor.get('address', '')}")
                    st.markdown(f"**GST:** {vendor.get('gst_no', 'N/A')}")
                    st.markdown(f"**Payment Terms:** {vendor.get('payment_terms', '')}")

                # Services
                with st.expander("🛠️ Services Offered"):
                    services = get_service_vendor_services(vid)
                    if services:
                        df = pd.DataFrame(services)
                        cols = ["service_name", "description", "unit", "rate"]
                        available = [c for c in cols if c in df.columns]
                        if available:
                            st.dataframe(df[available], use_container_width=True, hide_index=True)

                    st.markdown("**Add Service:**")
                    with st.form(f"svc_{vid}", clear_on_submit=True):
                        sc1, sc2 = st.columns(2)
                        with sc1:
                            service_name = st.selectbox("Service Type", SERVICE_TYPES, key=f"sn_{vid}")
                            description = st.text_input("Description", key=f"sd_{vid}")
                        with sc2:
                            unit = st.selectbox("Unit", UNITS_OF_MEASURE, key=f"su_{vid}")
                            rate = st.number_input("Rate (INR)", min_value=0.0, step=0.5, key=f"sr_{vid}")
                        if st.form_submit_button("➕ Add Service"):
                            if service_name:
                                add_service_vendor_service(vid, service_name, description, unit, rate)
                                st.success(f"Added **{service_name}**")
                                st.rerun()

                # Edit
                with st.expander("✏️ Edit Vendor Details"):
                    with st.form(f"edit_sv_{vid}"):
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            e_name = st.text_input("Company Name", value=vendor.get("name", ""), key=f"svn_{vid}")
                            e_contact = st.text_input("Contact Person", value=vendor.get("contact_person", ""), key=f"svc_{vid}")
                            e_phone = st.text_input("Phone", value=vendor.get("phone", ""), key=f"svp_{vid}")
                            e_email = st.text_input("Email", value=vendor.get("email", ""), key=f"sve_{vid}")
                        with ec2:
                            e_address = st.text_area("Address", value=vendor.get("address", ""), height=80, key=f"sva_{vid}")
                            e_gst = st.text_input("GST Number", value=vendor.get("gst_no", ""), key=f"svg_{vid}")
                            e_payment = st.selectbox("Payment Terms", PAYMENT_TERMS,
                                index=PAYMENT_TERMS.index(vendor.get("payment_terms", PAYMENT_TERMS[0]))
                                if vendor.get("payment_terms") in PAYMENT_TERMS else 0, key=f"svpt_{vid}")
                        if st.form_submit_button("💾 Save Changes"):
                            update_service_vendor(vid, {
                                "name": e_name, "contact_person": e_contact, "phone": e_phone,
                                "email": e_email, "address": e_address, "gst_no": e_gst,
                                "payment_terms": e_payment,
                            })
                            st.success(f"Service Vendor **{e_name}** updated!")
                            st.rerun()

                # Delete
                st.markdown("")
                dc1, dc2 = st.columns([3, 1])
                with dc1:
                    del_confirm = st.checkbox(f"I confirm deletion of {vendor['name']}", key=f"svdc_{vid}")
                with dc2:
                    if st.button("🗑️ Delete", disabled=not del_confirm, key=f"svdb_{vid}"):
                        delete_service_vendor(vid)
                        st.success(f"Service Vendor **{vendor['name']}** deleted.")
                        st.rerun()
