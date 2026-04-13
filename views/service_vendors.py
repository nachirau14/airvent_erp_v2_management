"""Service Vendors Management Page."""
import streamlit as st
import pandas as pd
from utils.db import (
    add_service_vendor, get_all_service_vendors,
    add_service_vendor_service, get_service_vendor_services,
)
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
    st.markdown("*Manage subcontractors and their service offerings*")
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
            empty_state("🔧", "No service vendors registered", "Add your first service vendor")
            return

        st.markdown(f"**{len(vendors)} service vendor(s) registered**")

        for vendor in sorted(vendors, key=lambda x: x.get("name", "")):
            with st.expander(f"🏭 **{vendor['name']}** — {vendor.get('contact_person', '')}"):
                vc1, vc2 = st.columns(2)
                with vc1:
                    st.markdown(f"**Contact:** {vendor.get('contact_person', '')}")
                    st.markdown(f"**Phone:** {vendor.get('phone', '')}")
                    st.markdown(f"**Email:** {vendor.get('email', '')}")
                with vc2:
                    st.markdown(f"**Address:** {vendor.get('address', '')}")
                    st.markdown(f"**GST:** {vendor.get('gst_no', 'N/A')}")
                    st.markdown(f"**Payment Terms:** {vendor.get('payment_terms', '')}")

                st.markdown("---")
                st.markdown("#### 🛠️ Services Offered")

                services = get_service_vendor_services(vendor["vendor_id"])
                if services:
                    df = pd.DataFrame(services)
                    cols = ["service_name", "description", "unit", "rate"]
                    available = [c for c in cols if c in df.columns]
                    if available:
                        display_df = df[available].copy()
                        display_df.columns = [c.replace("_", " ").title() for c in available]
                        st.dataframe(display_df, use_container_width=True, hide_index=True)
                else:
                    st.caption("No services listed yet")

                st.markdown("##### ➕ Add Service")
                with st.form(f"svc_{vendor['vendor_id']}", clear_on_submit=True):
                    sc1, sc2 = st.columns(2)
                    with sc1:
                        service_name = st.selectbox("Service Type", SERVICE_TYPES, key=f"sn_{vendor['vendor_id']}")
                        description = st.text_input("Description", key=f"sd_{vendor['vendor_id']}")
                    with sc2:
                        unit = st.selectbox("Unit", UNITS_OF_MEASURE, key=f"su_{vendor['vendor_id']}")
                        rate = st.number_input("Rate (₹)", min_value=0.0, step=0.5, key=f"sr_{vendor['vendor_id']}")

                    if st.form_submit_button("Add Service"):
                        if service_name:
                            add_service_vendor_service(vendor["vendor_id"], service_name, description, unit, rate)
                            st.success(f"Added **{service_name}**")
                            st.rerun()
