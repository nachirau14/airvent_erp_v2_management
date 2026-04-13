"""Dashboard - Overview of the entire ERP system."""
import streamlit as st
import pandas as pd
from utils.db import (
    get_all_projects, get_all_raw_material_pos, get_all_service_pos,
    get_all_inventory, get_all_master_items,
    get_finished_goods, get_dispatched_goods,
)
from utils.ui_helpers import styled_metric, project_status_badge, po_status_badge, section_header, empty_state


def render():
    st.markdown("# 📊 Dashboard")
    st.markdown("*Overview of your fabrication operations*")
    st.markdown("---")

    # Fetch data
    projects = get_all_projects()
    rm_pos = get_all_raw_material_pos()
    svc_pos = get_all_service_pos()
    inv = get_all_inventory()
    inv_con = []
    fg = get_finished_goods()
    dispatched = get_dispatched_goods()

    # ─── Top Metrics ──────────────────────────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        styled_metric("Projects", len(projects), color="#1e40af")
    with c2:
        active = len([p for p in projects if p.get("status") in ("Planning", "BOQ Ready", "Procurement", "In Production")])
        styled_metric("Active", active, color="#7c3aed")
    with c3:
        styled_metric("Material POs", len(rm_pos), color="#0369a1")
    with c4:
        styled_metric("Service POs", len(svc_pos), color="#0e7490")
    with c5:
        styled_metric("Raw Stock Items", len(inv), color="#15803d")
    with c6:
        styled_metric("Finished Goods", len([f for f in fg if f.get("status") == "In Store"]), color="#b45309")

    st.markdown("")

    # ─── Projects Overview ────────────────────────────────────────
    col_left, col_right = st.columns([3, 2])

    with col_left:
        section_header("Active Projects", "📋")
        if projects:
            for proj in sorted(projects, key=lambda x: x.get("created_at", ""), reverse=True)[:8]:
                with st.container():
                    pc1, pc2, pc3 = st.columns([3, 2, 1])
                    with pc1:
                        st.markdown(f"**{proj['name']}**")
                        st.caption(f"Client: {proj.get('client_name', 'N/A')} • {proj.get('product_type', '')}")
                    with pc2:
                        st.markdown(project_status_badge(proj.get("status", "Planning")), unsafe_allow_html=True)
                    with pc3:
                        st.caption(proj.get("project_id", "")[:12])
                    st.markdown("<hr style='margin:4px 0;border-color:#f1f5f9'>", unsafe_allow_html=True)
        else:
            empty_state("📋", "No projects yet", "Create your first project to get started")

    with col_right:
        section_header("PO Status Summary", "📦")

        # Material POs breakdown
        po_status_counts = {}
        for po in rm_pos:
            s = po.get("status", "Draft")
            po_status_counts[s] = po_status_counts.get(s, 0) + 1

        if po_status_counts:
            st.markdown("**Raw Material POs**")
            for status, count in po_status_counts.items():
                st.markdown(f"{po_status_badge(status)} × **{count}**", unsafe_allow_html=True)
        else:
            st.caption("No material POs yet")

        st.markdown("")

        svc_status_counts = {}
        for po in svc_pos:
            s = po.get("status", "Draft")
            svc_status_counts[s] = svc_status_counts.get(s, 0) + 1

        if svc_status_counts:
            st.markdown("**Service POs**")
            for status, count in svc_status_counts.items():
                st.markdown(f"{po_status_badge(status)} × **{count}**", unsafe_allow_html=True)
        else:
            st.caption("No service POs yet")

    # ─── Outstanding POs ──────────────────────────────────────────
    st.markdown("")
    section_header("Outstanding Purchase Orders", "⚠️")

    outstanding_pos = [po for po in rm_pos if po.get("status") in ("Placed", "Partially Received")]
    if outstanding_pos:
        df = pd.DataFrame(outstanding_pos)
        cols_to_show = ["po_id", "vendor_name", "status", "total_amount", "expected_delivery", "project_id"]
        available_cols = [c for c in cols_to_show if c in df.columns]
        if available_cols:
            display_df = df[available_cols].copy()
            display_df.columns = [c.replace("_", " ").title() for c in available_cols]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.success("No outstanding material POs")

    outstanding_svc = [po for po in svc_pos if po.get("status") in ("Placed", "In Progress", "Partially Received")]
    if outstanding_svc:
        df = pd.DataFrame(outstanding_svc)
        cols_to_show = ["po_id", "vendor_name", "status", "total_amount", "expected_delivery"]
        available_cols = [c for c in cols_to_show if c in df.columns]
        if available_cols:
            display_df = df[available_cols].copy()
            display_df.columns = [c.replace("_", " ").title() for c in available_cols]
            st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ─── Recent Dispatches ────────────────────────────────────────
    section_header("Recent Dispatches", "🚚")
    if dispatched:
        df = pd.DataFrame(dispatched)
        cols = ["dispatch_id", "project_id", "dispatch_to", "vehicle_no", "dispatched_at"]
        available = [c for c in cols if c in df.columns]
        if available:
            st.dataframe(df[available].head(5), use_container_width=True, hide_index=True)
    else:
        empty_state("🚚", "No dispatches yet")
