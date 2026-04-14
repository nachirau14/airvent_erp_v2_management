"""Email Setup — configure sender, test emails, trigger reminders and digests."""
import streamlit as st
from datetime import datetime, timedelta
from utils.db import (
    get_email_config, save_email_config, send_test_email,
    get_all_raw_material_pos, get_all_service_pos,
    send_reminder_email, send_weekly_digest,
    get_all_vendors, get_all_service_vendors,
)
from utils.ui_helpers import section_header, empty_state, styled_metric


def render():
    st.markdown("# 📧 Email Setup")
    st.markdown("*Configure sender email, test delivery, manage reminders and weekly digests*")
    st.markdown("---")

    tab_config, tab_test, tab_reminders, tab_digest = st.tabs([
        "⚙️ Configuration", "🧪 Test Email", "⏰ Delivery Reminders", "📊 Weekly Digest"
    ])

    # ─── Configuration ────────────────────────────────────────
    with tab_config:
        section_header("Email Configuration", "⚙️")

        config = get_email_config()

        with st.form("email_config_form"):
            st.markdown("**Sender Settings**")
            sender_email = st.text_input("Sender Email (SES verified) *",
                value=config.get("sender_email", ""), placeholder="erp@yourdomain.com")
            st.caption("This email must be verified in AWS SES. In sandbox mode, recipient emails must also be verified.")

            company_name = st.text_input("Company Name (appears in emails)",
                value=config.get("company_name", "FabriFlow"))

            st.markdown("---")
            st.markdown("**Management Recipients**")
            st.caption("These emails receive delivery reminders and weekly digests. One per line.")
            mgmt_raw = st.text_area("Management Email Addresses",
                value="\n".join(config.get("management_emails", [])),
                height=100, placeholder="manager1@company.com\nmanager2@company.com")

            st.markdown("---")
            st.markdown("**Automation Settings**")
            c1, c2 = st.columns(2)
            with c1:
                reminder_enabled = st.checkbox("Enable delivery reminders",
                    value=config.get("reminder_enabled", True))
                st.caption("Sends reminder when PO delivery is due next day")
            with c2:
                digest_enabled = st.checkbox("Enable weekly digest",
                    value=config.get("digest_enabled", True))
                st.caption("Sends weekly summary of received POs")

            if st.form_submit_button("💾 Save Configuration", use_container_width=True, type="primary"):
                mgmt_emails = [e.strip() for e in mgmt_raw.strip().split("\n") if e.strip()]
                new_config = {
                    "sender_email": sender_email.strip(),
                    "company_name": company_name.strip(),
                    "management_emails": mgmt_emails,
                    "reminder_enabled": reminder_enabled,
                    "digest_enabled": digest_enabled,
                }
                if save_email_config(new_config):
                    st.success("Email configuration saved!")
                    st.rerun()

        # SES verification status
        st.markdown("---")
        st.markdown("#### SES Verification")
        st.info("""
        **To verify your sender email in AWS SES:**
        ```
        aws ses verify-email-identity --email-address your@email.com --region ap-south-1
        ```
        Check your inbox and click the verification link. In SES sandbox mode, you must also verify each recipient email.
        To request production access (send to any email), apply via AWS Console → SES → Account Dashboard → Request Production Access.
        """)

    # ─── Test Email ───────────────────────────────────────────
    with tab_test:
        section_header("Send Test Email", "🧪")

        config = get_email_config()
        st.markdown(f"**Current sender:** `{config.get('sender_email', 'Not configured')}`")

        with st.form("test_email_form"):
            test_to = st.text_input("Send test to *", placeholder="recipient@example.com")
            test_sender = st.text_input("Override sender (optional)",
                value=config.get("sender_email", ""), placeholder="Leave blank to use configured sender")

            if st.form_submit_button("📤 Send Test Email", use_container_width=True, type="primary"):
                if test_to:
                    with st.spinner("Sending..."):
                        result = send_test_email(test_to.strip(), test_sender.strip() or None)
                    if result is True:
                        st.success(f"Test email sent to **{test_to}**!")
                    else:
                        st.error(f"Failed: {result}")
                else:
                    st.error("Enter a recipient email.")

        st.markdown("---")
        st.markdown("#### Troubleshooting")
        st.markdown("""
        - **MessageRejected**: Sender email not verified in SES, or in sandbox mode and recipient not verified
        - **AccessDenied**: IAM user missing `ses:SendEmail` permission
        - **Throttling**: SES sending rate exceeded — wait and retry
        - **InvalidParameterValue**: Malformed email address
        """)

    # ─── Delivery Reminders ───────────────────────────────────
    with tab_reminders:
        section_header("Delivery Reminders", "⏰")

        config = get_email_config()
        mgmt_emails = config.get("management_emails", [])

        st.markdown(f"**Status:** {'🟢 Enabled' if config.get('reminder_enabled') else '🔴 Disabled'}")
        st.markdown(f"**Management recipients:** {', '.join(mgmt_emails) if mgmt_emails else 'None configured'}")

        st.markdown("---")
        st.markdown("#### Outstanding POs Due Tomorrow")

        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Material POs
        rm_pos = get_all_raw_material_pos()
        due_rm = [po for po in rm_pos
                  if po.get("status") in ("Placed", "Partially Received")
                  and po.get("expected_delivery", "") <= tomorrow
                  and po.get("expected_delivery", "") >= today]

        # Service POs
        svc_pos = get_all_service_pos()
        due_svc = [po for po in svc_pos
                   if po.get("status") in ("Placed", "In Progress", "Partially Received")
                   and po.get("expected_delivery", "") <= tomorrow
                   and po.get("expected_delivery", "") >= today]

        vendors = {v["vendor_id"]: v for v in get_all_vendors()}
        svc_vendors = {v["vendor_id"]: v for v in get_all_service_vendors()}

        if due_rm:
            st.markdown(f"**{len(due_rm)} Material PO(s) due:**")
            for po in due_rm:
                vendor = vendors.get(po.get("vendor_id", ""), {})
                vendor_email = vendor.get("email", "")
                st.markdown(f"- **{po['po_id']}** — {po.get('vendor_name', '')} | Due: {po.get('expected_delivery', '')} | Email: {vendor_email or 'N/A'}")

                if st.button(f"📤 Send Reminder for {po['po_id']}", key=f"rem_rm_{po['po_id']}"):
                    results = send_reminder_email(po, vendor_email, mgmt_emails, "Material")
                    for target, res in results:
                        if res is True:
                            st.success(f"Reminder sent to {target}")
                        else:
                            st.error(f"Failed ({target}): {res}")
        else:
            st.success("No material POs due tomorrow")

        if due_svc:
            st.markdown(f"**{len(due_svc)} Service PO(s) due:**")
            for po in due_svc:
                vendor = svc_vendors.get(po.get("vendor_id", ""), {})
                vendor_email = vendor.get("email", "")
                st.markdown(f"- **{po['po_id']}** — {po.get('vendor_name', '')} | Due: {po.get('expected_delivery', '')}")

                if st.button(f"📤 Send Reminder for {po['po_id']}", key=f"rem_svc_{po['po_id']}"):
                    results = send_reminder_email(po, vendor_email, mgmt_emails, "Service")
                    for target, res in results:
                        if res is True:
                            st.success(f"Reminder sent to {target}")
                        else:
                            st.error(f"Failed ({target}): {res}")
        elif not due_rm:
            st.info("No service POs due tomorrow either")

        st.markdown("---")
        st.markdown("#### 🔄 Send All Reminders Now")
        all_due = due_rm + due_svc
        if all_due:
            if st.button(f"📤 Send {len(all_due)} Reminder(s)", type="primary", use_container_width=True):
                sent = 0
                for po in due_rm:
                    v = vendors.get(po.get("vendor_id", ""), {})
                    send_reminder_email(po, v.get("email", ""), mgmt_emails, "Material")
                    sent += 1
                for po in due_svc:
                    v = svc_vendors.get(po.get("vendor_id", ""), {})
                    send_reminder_email(po, v.get("email", ""), mgmt_emails, "Service")
                    sent += 1
                st.success(f"Sent **{sent}** reminder(s)!")

    # ─── Weekly Digest ────────────────────────────────────────
    with tab_digest:
        section_header("Weekly Digest", "📊")

        config = get_email_config()
        mgmt_emails = config.get("management_emails", [])

        st.markdown(f"**Status:** {'🟢 Enabled' if config.get('digest_enabled') else '🔴 Disabled'}")
        st.markdown(f"**Recipients:** {', '.join(mgmt_emails) if mgmt_emails else 'None configured'}")

        st.markdown("---")
        st.markdown("#### POs Completed/Received in the Past 7 Days")

        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        rm_pos = get_all_raw_material_pos()
        recent_rm = [po for po in rm_pos
                     if po.get("status") in ("Complete", "Partially Received")
                     and po.get("updated_at", "") >= week_ago]

        svc_pos = get_all_service_pos()
        recent_svc = [po for po in svc_pos
                      if po.get("status") in ("Complete", "Partially Received")
                      and po.get("updated_at", "") >= week_ago]

        all_recent = recent_rm + recent_svc

        c1, c2, c3 = st.columns(3)
        with c1:
            styled_metric("Material POs", len(recent_rm), color="#1e40af")
        with c2:
            styled_metric("Service POs", len(recent_svc), color="#0e7490")
        with c3:
            total_val = sum(po.get("total_amount", 0) for po in all_recent)
            styled_metric("Total Value", f"₹{total_val:,.0f}", color="#16a34a")

        if all_recent:
            for po in all_recent:
                st.markdown(f"- **{po.get('po_id', '')}** — {po.get('vendor_name', '')} | {po.get('status', '')} | ₹{po.get('total_amount', 0):,.2f}")

        st.markdown("---")
        if mgmt_emails:
            if st.button("📤 Send Weekly Digest Now", type="primary", use_container_width=True):
                results = send_weekly_digest(all_recent, mgmt_emails)
                success = sum(1 for r in results if r is True)
                st.success(f"Digest sent to **{success}** of {len(mgmt_emails)} recipients")
        else:
            st.warning("Configure management email addresses in the Configuration tab first.")
