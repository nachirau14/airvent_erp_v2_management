"""Vendors Management Page — linked to master items catalog."""
import streamlit as st
import pandas as pd
from utils.db import add_vendor, get_all_vendors, get_all_master_items
from utils.ui_helpers import section_header, empty_state, format_currency
from config import PAYMENT_TERMS


def render():
    st.markdown("# 👥 Material Vendors")
    st.markdown("*Manage your material suppliers — items are linked via the Master Items catalog*")
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
            empty_state("👥", "No vendors registered", "Add your first vendor in the 'Add Vendor' tab")
            return

        master_items = get_all_master_items()
        st.markdown(f"**{len(vendors)} vendor(s) registered**")

        for vendor in sorted(vendors, key=lambda x: x.get("name", "")):
            # Find master items linked to this vendor
            vendor_items = [m for m in master_items if m.get("vendor", "").lower() == vendor["name"].lower()]

            with st.expander(f"🏢 **{vendor['name']}** — {vendor.get('contact_person', '')} | {len(vendor_items)} items ({vendor.get('vendor_id', '')})"):
                vc1, vc2 = st.columns(2)
                with vc1:
                    st.markdown(f"**Phone:** {vendor.get('phone', 'N/A')}")
                    st.markdown(f"**Email:** {vendor.get('email', 'N/A')}")
                    st.markdown(f"**GST:** {vendor.get('gst_no', 'N/A')}")
                with vc2:
                    st.markdown(f"**Address:** {vendor.get('address', 'N/A')}")
                    st.markdown(f"**Payment Terms:** {vendor.get('payment_terms', 'N/A')}")

                st.markdown("---")
                st.markdown("#### 📦 Items from Master Catalog")

                if vendor_items:
                    df = pd.DataFrame(vendor_items)
                    cols = ["item_id", "item_name", "category", "sub_category", "specification", "unit", "price", "revised_price"]
                    available = [c for c in cols if c in df.columns]
                    if available:
                        display_df = df[available].copy()
                        display_df.columns = [c.replace("_", " ").title() for c in available]
                        st.dataframe(display_df, use_container_width=True, hide_index=True)
                else:
                    st.caption("No items in master catalog for this vendor. Add items in 📦 Master Items page with this vendor name.")
