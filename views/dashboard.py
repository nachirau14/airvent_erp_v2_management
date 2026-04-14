"""Dashboard — overview with clickable navigation to each section."""
import streamlit as st
import pandas as pd
from utils.db import (get_all_projects, get_all_raw_material_pos, get_all_service_pos,
                       get_all_inventory, get_all_master_items,
                       get_finished_goods, get_dispatched_goods)
from utils.ui_helpers import section_header, po_status_badge, format_currency, empty_state, styled_metric


def _nav_button(label, icon, target_page):
    """Render a button that sets sidebar radio to navigate."""
    if st.button(f"{icon} {label}", use_container_width=True, key=f"nav_{target_page}"):
        st.session_state["nav_target"] = target_page
        st.rerun()


def render():
    # Handle navigation from button clicks
    if "nav_target" in st.session_state:
        # This will be picked up on next rerun by the sidebar radio
        pass

    st.markdown("# 📊 Dashboard")
    st.markdown("*Overview of your fabrication operations*")
    st.markdown("---")

    projects = get_all_projects()
    rm_pos = get_all_raw_material_pos()
    svc_pos = get_all_service_pos()
    inv = get_all_inventory()
    master = get_all_master_items()
    fg = get_finished_goods()
    dispatched = get_dispatched_goods()

    # ─── Top Metrics ──────────────────────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1: styled_metric("Master Items", len(master), color="#1e40af")
    with c2: styled_metric("Projects", len(projects), color="#7c3aed")
    with c3: styled_metric("Material POs", len(rm_pos), color="#0369a1")
    with c4: styled_metric("Service POs", len(svc_pos), color="#0e7490")
    with c5: styled_metric("Inventory Items", len(inv), color="#15803d")
    with c6: styled_metric("Finished Goods", len([f for f in fg if f.get("status") == "In Store"]), color="#b45309")

    st.markdown("")

    # ─── Quick Navigation ─────────────────────────────────────
    st.markdown("### ⚡ Quick Navigation")
    nc1, nc2, nc3, nc4, nc5 = st.columns(5)
    with nc1: _nav_button("Master Items", "📦", "📦 Master Items")
    with nc2: _nav_button("Projects & BOQ", "📋", "📋 Projects & BOQ")
    with nc3: _nav_button("Order Staging", "🚀", "🚀 Order Staging")
    with nc4: _nav_button("Purchase Orders", "📦", "📦 Purchase Orders")
    with nc5: _nav_button("Inventory", "📦", "📦 Inventory")

    nc6, nc7, nc8, nc9, nc10 = st.columns(5)
    with nc6: _nav_button("Service POs", "🛠️", "🛠️ Service POs")
    with nc7: _nav_button("Production", "🏗️", "🏗️ Production Tracking")
    with nc8: _nav_button("Finished Goods", "✅", "✅ Finished Goods")
    with nc9: _nav_button("Dispatch", "🚚", "🚚 Dispatch")
    with nc10: _nav_button("Bulk Upload", "📤", "📤 Bulk Upload")

    st.markdown("---")

    # ─── Active Projects ──────────────────────────────────────
    col_left, col_right = st.columns([3, 2])

    with col_left:
        section_header("Active Projects", "📋")
        active = [p for p in projects if p.get("status") not in ("Complete", "Dispatched")]
        if active:
            for proj in sorted(active, key=lambda x: x.get("created_at", ""), reverse=True)[:8]:
                pc1, pc2 = st.columns([3, 1])
                with pc1:
                    st.markdown(f"**{proj['name']}** — {proj.get('client_name', '')}")
                    st.caption(f"{proj.get('product_type', '')} | {proj.get('status', '')}")
                with pc2:
                    st.caption(proj.get("project_id", "")[:12])
                st.markdown("<hr style='margin:4px 0;border-color:#f1f5f9'>", unsafe_allow_html=True)
        else:
            empty_state("📋", "No active projects")

    with col_right:
        section_header("PO Status Summary", "📦")
        po_counts = {}
        for po in rm_pos:
            s = po.get("status", "Draft")
            po_counts[s] = po_counts.get(s, 0) + 1
        if po_counts:
            st.markdown("**Material POs**")
            for status, count in po_counts.items():
                color = {"Draft": "🔘", "Placed": "🔵", "Partially Received": "🟡", "Complete": "🟢", "Cancelled": "🔴"}.get(status, "⚪")
                st.markdown(f"{color} **{status}**: {count}")
        else:
            st.caption("No material POs")

        svc_counts = {}
        for po in svc_pos:
            s = po.get("status", "Draft")
            svc_counts[s] = svc_counts.get(s, 0) + 1
        if svc_counts:
            st.markdown("**Service POs**")
            for status, count in svc_counts.items():
                color = {"Draft": "🔘", "Placed": "🔵", "In Progress": "🟡", "Complete": "🟢"}.get(status, "⚪")
                st.markdown(f"{color} **{status}**: {count}")

    # ─── Outstanding POs ──────────────────────────────────────
    st.markdown("")
    section_header("Outstanding Purchase Orders", "⚠️")
    outstanding = [po for po in rm_pos if po.get("status") in ("Placed", "Partially Received")]
    if outstanding:
        df = pd.DataFrame(outstanding)
        cols = ["po_id", "vendor_name", "status", "total_amount", "expected_delivery", "project_id"]
        available = [c for c in cols if c in df.columns]
        if available:
            st.dataframe(df[available], use_container_width=True, hide_index=True)
    else:
        st.success("No outstanding material POs")

    # ─── Recent Dispatches ────────────────────────────────────
    section_header("Recent Dispatches", "🚚")
    if dispatched:
        df = pd.DataFrame(dispatched)
        cols = ["dispatch_id", "project_id", "dispatch_to", "vehicle_no", "dispatched_at"]
        available = [c for c in cols if c in df.columns]
        if available:
            st.dataframe(df[available].head(5), use_container_width=True, hide_index=True)
    else:
        empty_state("🚚", "No dispatches yet")
