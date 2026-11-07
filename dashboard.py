import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
import glob
import re
from dotenv import load_dotenv

load_dotenv()

# --- Database Connection ---
db_url = os.getenv("DB_DSN").replace("postgresql+psycopg://", "postgresql://")
engine = create_engine(db_url)

st.set_page_config(page_title="Baton Agency", layout="wide", page_icon="🚀")
st.title("🚀 Baton Agency Pipeline")
st.markdown("Your autonomous AI sales engine for finding and closing clients.")

# --- Fetch Data ---
@st.cache_data(ttl=10)  # Refresh every 10 seconds
def load_data():
    with engine.connect() as conn:
        # 1. FIXED: CAST id to TEXT so pandas matches it with filenames
        # 2. FIXED: Removed "WHERE score >= 50" so we don't accidentally hide data
        leads = pd.read_sql(text("""
            SELECT 
                CAST(id AS TEXT) as "Lead ID",
                COALESCE(metadata->>'name', 'Unknown Business') as "Business Name", 
                COALESCE(metadata->>'category', 'Local Business') as "Category",
                metadata->>'email' as "Email",
                COALESCE(metadata->>'website', metadata->>'link') as "Website",
                metadata->>'instagram' as "Instagram",
                metadata->>'facebook' as "Facebook",
                metadata->>'linkedin' as "LinkedIn",
                COALESCE(score, 0) as "Score", 
                stage as "Stage"
            FROM leads 
            WHERE stage IN ('quoted', 'done', 'qualified')
            ORDER BY score DESC NULLS LAST
        """), conn)
        
        # Clean up website URLs so they are clickable
        def clean_url(url):
            if pd.isna(url) or not url or str(url).lower() == "none": 
                return None
            url = str(url).strip()
            return f"https://{url}" if not url.startswith("http") else url

        for col in ["Website", "Instagram", "Facebook", "LinkedIn"]:
            if col in leads.columns:
                leads[col] = leads[col].apply(clean_url)
        
        # 3. FIXED: Properly handle empty emails (None vs NaN vs "")
        leads["Email"] = leads["Email"].astype(str)
        leads["Email"] = leads["Email"].replace(['None', 'nan', 'NULL', ''], None)
        
        sent_df = leads[leads["Email"].notna()]
        drafted_df = leads[leads["Email"].isna()]
        
        # Fetch Approvals
        approvals = pd.read_sql(text("""
            SELECT 
                COALESCE(l.metadata->>'name', 'Unknown Business') as "Business Name",
                q.total_amount as "Quote Amount ($)",
                a.status as "Status"
            FROM approvals a
            JOIN quotations q ON a.quotation_id = q.id
            JOIN leads l ON q.lead_id = l.id
            WHERE a.status = 'pending'
        """), conn)
        
    return leads, sent_df, drafted_df, approvals

leads, sent_df, drafted_df, approvals = load_data()

# Count drafted emails in the local outbox folder
outbox_files = glob.glob("outbox/*.txt")

# --- Top Metrics ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("✅ Emails Sent", len(sent_df))
col2.metric("📝 Gmail Drafts Created", len(drafted_df))
col3.metric("🚨 Pending Approvals", len(approvals))
col4.metric("Total Scored Leads", len(leads))

st.divider()

# --- Table Column Configurations (Makes links clickable) ---
link_config = {
    "Website": st.column_config.LinkColumn("Website", display_text="Visit Site"),
    "Instagram": st.column_config.LinkColumn("Instagram", display_text="IG Profile"),
    "Facebook": st.column_config.LinkColumn("Facebook", display_text="FB Profile"),
    "LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="LinkedIn"),
    "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d")
}

# --- Approvals Section ---
st.subheader("🚨 Pending Human Approvals")
if not approvals.empty:
    st.dataframe(approvals, use_container_width=True, hide_index=True)
else:
    st.success("No pending approvals right now.")

st.divider()

# --- Sent Emails Section ---
st.subheader("✅ Sent Automatically (Had Email)")
st.markdown("*These businesses received a personalized cold email directly to their inbox.*")
if not sent_df.empty:
    st.dataframe(
        sent_df[["Business Name", "Score", "Email", "Website", "Instagram", "Facebook"]], 
        use_container_width=True, 
        hide_index=True,
        column_config=link_config
    )
else:
    st.info("No emails have been sent yet.")

st.divider()

# --- Drafted Emails Section ---
st.subheader("📝 Saved to Gmail Drafts (No Email Found)")
st.markdown("*The AI couldn't find an email, so it saved the draft to your Gmail. Use these links to call them or DM them manually.*")
if not drafted_df.empty:
    st.dataframe(
        drafted_df[["Business Name", "Score", "Website", "Instagram", "Facebook", "LinkedIn"]], 
        use_container_width=True, 
        hide_index=True,
        column_config=link_config
    )
else:
    st.info("No drafted leads yet.")

st.divider()

# --- Local Outbox Viewer ---
st.subheader("📁 Read Local Email Drafts")
if outbox_files:
    email_mapping = {}
    for filepath in outbox_files:
        match = re.search(r'email_([a-f0-9\-]+)\.txt', filepath)
        if match:
            lead_id = match.group(1)
            # 4. FIXED: String matching now works perfectly because of CAST(id AS TEXT)
            lead_row = leads[leads["Lead ID"] == lead_id]
            if not lead_row.empty:
                name = lead_row.iloc[0]["Business Name"]
                email_mapping[f"{name} ({lead_id[:8]})"] = filepath
            else:
                email_mapping[f"Unknown Lead ({lead_id[:8]})"] = filepath

    if email_mapping:
        selected_name = st.selectbox("Select a business to read their drafted email:", list(email_mapping.keys()))
        selected_file = email_mapping[selected_name]
        
        with open(selected_file, "r", encoding="utf-8") as f:
            email_content = f.read()
        st.text_area("Email Content (Backup)", email_content, height=250)
else:
    st.info("No local backup drafts found.")