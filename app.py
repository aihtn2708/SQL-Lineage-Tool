import streamlit as st
from supabase import create_client, Client
import sqlglot
from sqlglot import exp
import graphviz
from collections import defaultdict
from streamlit_option_menu import option_menu
from streamlit_adjustable_columns import adjustable_columns
import pandas as pd
import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="SQL-Flow SaaS", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM UI / CSS ---
st.markdown("""
<style>
    .centered-title {
        text-align: center;
        font-weight: 800;
        font-size: 3rem;
        margin-bottom: 0.5rem;
        background: -webkit-linear-gradient(45deg, #FF4B4B, #FF8F8F);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .centered-subtitle {
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    [data-testid="stSidebar"] {
        border-right: 1px solid #e0e0e0;
    }
</style>
""", unsafe_allow_html=True)

# --- SUPABASE INIT ---
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_supabase()

# --- SESSION STATE ---
if "user" not in st.session_state:
    st.session_state.user = None
if "editor_sql" not in st.session_state:
    st.session_state.editor_sql = ""
if "lineage_data" not in st.session_state:
    st.session_state.lineage_data = None

def log_activity(action, details=""):
    user_id = st.session_state.user.id if st.session_state.user else None
    try:
        supabase.table("activity_logs").insert({"user_id": user_id, "action": action, "details": details}).execute()
    except Exception:
        pass

# --- HEADER ---
st.markdown("<h1 class='centered-title'>🔗 SQL-Flow</h1>", unsafe_allow_html=True)
st.markdown("<p class='centered-subtitle'>Data Lineage & Impact Analytics</p>", unsafe_allow_html=True)

# --- VERTICAL NAVIGATION (OPTION MENU) ---
menu_options = ["Intro & Examples", "Lineage Tool", "My Projects", "Account"]
menu_icons = ["book", "diagram-3", "folder", "person"]

is_admin = False
if st.session_state.user and st.session_state.user.email == st.secrets.get("ADMIN_EMAIL", ""):
    is_admin = True
    menu_options.append("Admin Board")
    menu_icons.append("shield-lock")

with st.sidebar:
    st.markdown("### Navigation")
    
    # The new, beautiful highlighted menu
    selected_page = option_menu(
        menu_title=None,
        options=menu_options,
        icons=menu_icons,
        default_index=1,
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "#FF8F8F", "font-size": "18px"}, 
            "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px", "--hover-color": "#f0f2f6"},
            "nav-link-selected": {"background-color": "#FF4B4B", "color": "white"},
        }
    )
    
    st.markdown("---")
    if st.session_state.user:
        st.success(f"Logged in:\n**{st.session_state.user.email}**")
    else:
        st.info("Status: **Guest Mode**")

# ==========================================
# PAGE 1: INTRODUCTION & EXAMPLES
# ==========================================
if selected_page == "Intro & Examples":
    st.header("📖 Welcome to SQL-Flow")
    st.markdown("Instantly visualize complex SQL dependencies, track downstream impacts, and save your work.")
    
    st.subheader("Load an Example")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🛒 Load Basic E-commerce SQL", use_container_width=True):
            st.session_state.editor_sql = """WITH raw_users AS (SELECT id, name FROM db.users),
active_users AS (SELECT * FROM raw_users WHERE status = 'active')
SELECT * FROM active_users;"""
            log_activity("Loaded Example", "E-commerce")
            st.success("Loaded! Click 'Lineage Tool' in the sidebar.")
            
    with col2:
        if st.button("📈 Load Complex Finance SQL", use_container_width=True):
            st.session_state.editor_sql = """WITH q1_rev AS (SELECT * FROM (SELECT id, amount FROM db.finance) AS sub1),
q2_rev AS (SELECT id, amount FROM db.finance_q2)
SELECT * FROM q1_rev UNION ALL SELECT * FROM q2_rev;"""
            log_activity("Loaded Example", "Finance")
            st.success("Loaded! Click 'Lineage Tool' in the sidebar.")

# ==========================================
# PAGE 2: LINEAGE TOOL
# ==========================================
elif selected_page == "Lineage Tool":
    
    # --- PAGE-SPECIFIC CSS HACK ---
    st.markdown("""
    <style>
        /* Nuke the ugly "Col 1 / Col 2" header bar from the plugin */
        iframe[title*="adjustable_columns"] {
            height: 0px !important;
            min-height: 0px !important;
            visibility: hidden !important;
            margin-bottom: -1.5rem !important; /* Pull content up to remove the empty gap */
        }
    </style>
    """, unsafe_allow_html=True)

    st.info("💡 **Pro-tip:** Hover your mouse in the gap between the editor and the graph to drag and adjust their widths! Hover over elements for Fullscreen mode.")
    
    # We pass empty labels to prevent the plugin from rendering text
    col_input, col_viz = adjustable_columns([1, 1.5], gap="large", labels=["", ""]) 
    
    with col_input:
        st.subheader("📝 SQL Editor")
        uploaded_file = st.file_uploader("Upload .sql file", type=["sql", "txt"])
        
        if uploaded_file:
            st.session_state.editor_sql = uploaded_file.getvalue().decode("utf-8")
            
        sql_input = st.text_area("Your Query:", value=st.session_state.editor_sql, height=450)
        analyze_btn = st.button("🚀 Parse SQL & Generate Map", type="primary", use_container_width=True)
        
        if st.session_state.user:
            with st.expander("💾 Save to Project"):
                projects_res = supabase.table("projects").select("*").eq("user_id", st.session_state.user.id).execute()
                projects = {p['name']: p['id'] for p in projects_res.data}
                
                if not projects:
                    st.warning("Create a project in the 'My Projects' tab first.")
                else:
                    selected_proj_name = st.selectbox("Select Project", options=list(projects.keys()))
                    query_name = st.text_input("Query Name (e.g., Q1 Revenue Model)")
                    if st.button("Save Query"):
                        supabase.table("queries").insert({
                            "project_id": projects[selected_proj_name],
                            "name": query_name,
                            "sql_text": sql_input
                        }).execute()
                        log_activity("Saved Query", query_name)
                        st.success("Query saved successfully!")

    if analyze_btn and sql_input:
        log_activity("Parsed SQL")
        try:
            parsed_query = sqlglot.parse_one(sql_input)
            downstream_map = defaultdict(set)
            upstream_map = defaultdict(set)
            all_nodes = set()
            
            for table in parsed_query.find_all(exp.Table):
                source_name = table.name
                all_nodes.add(source_name)
                parent_cte = None
                current_node = table
                while current_node:
                    if isinstance(current_node, exp.CTE):
                        parent_cte = current_node
                        break
                    current_node = current_node.parent
                    
                if parent_cte:
                    cte_name = parent_cte.alias
                    all_nodes.add(cte_name)
                    downstream_map[source_name].add(cte_name)
                    upstream_map[cte_name].add(source_name)
                else:
                    all_nodes.add("Final_Output")
                    downstream_map[source_name].add("Final_Output")
                    upstream_map["Final_Output"].add(source_name)

            st.session_state.lineage_data = {"downstream": downstream_map, "upstream": upstream_map, "nodes": all_nodes}
        except Exception as e:
            st.error(f"Failed to parse SQL: {e}")
            st.session_state.lineage_data = None

    with col_viz:
        if st.session_state.lineage_data:
            data = st.session_state.lineage_data
            
            # --- Graph Control Panel ---
            st.subheader("📊 Interactive Graph")
            
            c_controls_1, c_controls_2 = st.columns([1, 1])
            with c_controls_1:
                analysis_mode = st.radio(
                    "Analysis Mode:", 
                    ["Default View", "🔴 Downstream Impact", "🟠 Upstream Root Cause"]
                )
            with c_controls_2:
                target_node = st.selectbox("Target Node:", ["-- None --"] + sorted(list(data["nodes"])))

            def trace_lineage(node, mapping, visited=None):
                if visited is None: visited = set()
                for related_node in mapping.get(node, []):
                    if related_node not in visited:
                        visited.add(related_node)
                        trace_lineage(related_node, mapping, visited)
                return visited

            highlighted = set()
            if target_node != "-- None --":
                if "Downstream" in analysis_mode:
                    highlighted = trace_lineage(target_node, data["downstream"])
                elif "Upstream" in analysis_mode:
                    highlighted = trace_lineage(target_node, data["upstream"])
                highlighted.add(target_node)

            # --- Graphviz Rendering ---
            graph = graphviz.Digraph(engine='dot', format='png')
            graph.attr(rankdir='LR', size='12,12', bgcolor='transparent')
            graph.attr('node', shape='box', style='rounded,filled', fontname='Helvetica', margin='0.2')

            for node in data["nodes"]:
                fill_color = '#e0f2fe' 
                if node in highlighted:
                    fill_color = '#fee2e2' if "Downstream" in analysis_mode else '#ffedd5'
                elif node == "Final_Output":
                    fill_color = '#dcfce7' 
                elif node not in data["upstream"] and node != "Final_Output":
                    fill_color = '#f3f4f6' 
                
                graph.node(node, "Final Output" if node == "Final_Output" else node, fillcolor=fill_color)

            for parent, children in data["downstream"].items():
                for child in children:
                    edge_color = '#ef4444' if ("Downstream" in analysis_mode and parent in highlighted and child in highlighted) else '#9ca3af'
                    if "Upstream" in analysis_mode and parent in highlighted and child in highlighted: edge_color = '#f97316'
                    graph.edge(parent, child, color=edge_color, penwidth='2' if edge_color != '#9ca3af' else '1')

            st.graphviz_chart(graph, use_container_width=True)
            
            # --- Image Download Button ---
            try:
                img_bytes = graph.pipe()
                filename_suffix = target_node.replace(" ", "_") if target_node != "-- None --" else "full"
                st.download_button(
                    label="🖼️ Download Graph as PNG",
                    data=img_bytes,
                    file_name=f"lineage_map_{filename_suffix}.png",
                    mime="image/png",
                    use_container_width=True
                )
            except Exception as e:
                st.caption("Image export unavailable right now.")

            # --- Extracted Impact Table ---
            if target_node != "-- None --" and analysis_mode != "Default View":
                st.markdown("---")
                st.subheader(f"📋 Extracted {analysis_mode.split(' ')[1]} Data")
                
                impacted_items = list(highlighted - {target_node})
                
                if impacted_items:
                    df_impact = pd.DataFrame({
                        "Affected Node": impacted_items,
                        "Type": ["Final Output" if n == "Final_Output" else "Table/CTE" for n in impacted_items]
                    })
                    st.dataframe(df_impact, hide_index=True, use_container_width=True)
                else:
                    st.info(f"No direct {analysis_mode.split(' ')[1].lower()} items found for `{target_node}`.")

# ==========================================
# PAGE 3: MY PROJECTS
# ==========================================
elif selected_page == "My Projects":
    if st.session_state.user:
        st.header("📁 Your Workspace")
        
        with st.container(border=True):
            col_p1, col_p2 = st.columns([3, 1])
            with col_p1:
                new_proj = st.text_input("Create New Project", label_visibility="collapsed", placeholder="Project Name (e.g., Q3 Marketing Migration)")
            with col_p2:
                if st.button("➕ Create", use_container_width=True) and new_proj:
                    supabase.table("projects").insert({"user_id": st.session_state.user.id, "name": new_proj}).execute()
                    st.success("Project created!")
                    st.rerun()

        st.markdown("### Saved Queries")
        projects_res = supabase.table("projects").select("id, name").eq("user_id", st.session_state.user.id).execute()
        
        if not projects_res.data:
            st.info("You don't have any projects yet.")
        else:
            for p in projects_res.data:
                with st.container(border=True):
                    st.markdown(f"#### 📁 {p['name']}")
                    queries_res = supabase.table("queries").select("*").eq("project_id", p['id']).execute()
                    
                    if not queries_res.data:
                        st.caption("No queries saved here yet.")
                    
                    for q in queries_res.data:
                        # Expander keeps the UI clean. Click to view full SQL.
                        with st.expander(f"📝 {q['name']} ({q['created_at'][:10]})"):
                            st.code(q['sql_text'], language="sql")
    else:
        st.warning("Please log in to manage your workspace.")

# ==========================================
# PAGE 4: ACCOUNT
# ==========================================
elif selected_page == "Account":
    if not st.session_state.user:
        st.header("👤 Authentication")
        with st.container(border=True):
            auth_mode = st.radio("Action:", ["Login", "Sign Up", "Forgot Password", "Enter Reset Code"], horizontal=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            email = st.text_input("Email")
            
            if auth_mode in ["Login", "Sign Up"]:
                password = st.text_input("Password", type="password")
                
            elif auth_mode == "Enter Reset Code":
                reset_code = st.text_input("6-Digit Reset Code (from email)")
                new_password = st.text_input("New Password", type="password")
                
            if st.button(auth_mode, type="primary"):
                try:
                    if auth_mode == "Login":
                        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                        st.session_state.user = res.user
                        log_activity("User Logged In")
                        st.success("Logged in successfully!")
                        st.rerun()
                        
                    elif auth_mode == "Sign Up":
                        supabase.auth.sign_up({"email": email, "password": password})
                        st.success("Check your email to confirm registration!")
                        
                    elif auth_mode == "Forgot Password":
                        supabase.auth.reset_password_email(email)
                        st.success("Reset code sent! Please check your email and select 'Enter Reset Code' above.")
                        
                    elif auth_mode == "Enter Reset Code":
                        supabase.auth.verify_otp({"email": email, "token": reset_code, "type": "recovery"})
                        supabase.auth.update_user({"password": new_password})
                        st.success("Password updated successfully! You can now select 'Login' to access your account.")
                        
                except Exception as e:
                    st.error(f"Authentication Error: {e}")
    else:
        st.header("👤 Account Settings")
        st.success(f"Verified Email: **{st.session_state.user.email}**")
        
        with st.expander("Update Password"):
            update_password = st.text_input("Enter New Password", type="password", key="update_pw")
            if st.button("Save New Password"):
                try:
                    supabase.auth.update_user({"password": update_password})
                    st.success("Password securely updated.")
                except Exception as e:
                    st.error(f"Failed to update: {e}")
                    
        if st.button("🚪 Log Out", type="secondary"):
            log_activity("User Logged Out")
            supabase.auth.sign_out()
            st.session_state.user = None
            st.rerun()

# ==========================================
# PAGE 5: ADMIN BOARD
# ==========================================
elif selected_page == "Admin Board":
    st.header("👑 Admin Dashboard")
    st.markdown("System metrics and usage analytics.")
    
    try:
        # Fetch Data
        queries_res = supabase.table("queries").select("*").execute()
        activity_res = supabase.table("activity_logs").select("*").execute()
        
        # Load into Pandas for easy charting
        df_queries = pd.DataFrame(queries_res.data)
        df_activity = pd.DataFrame(activity_res.data)
        
        if not df_queries.empty:
            df_queries['created_at'] = pd.to_datetime(df_queries['created_at']).dt.date
            df_queries['sql_length'] = df_queries['sql_text'].str.len()
        
        if not df_activity.empty:
            df_activity['created_at'] = pd.to_datetime(df_activity['created_at']).dt.date

        # Top Level Metrics
        col1, col2 = st.columns(2)
        col1.metric("Total Queries Processed", len(df_queries))
        col2.metric("Total Recorded Actions", len(df_activity))

        st.markdown("---")
        
        # Charts
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            st.subheader("Queries Created Over Time")
            if not df_queries.empty:
                daily_queries = df_queries.groupby('created_at').size().reset_index(name='count')
                st.bar_chart(daily_queries.set_index('created_at'))
            else:
                st.info("Not enough data to graph yet.")
                
        with chart_col2:
            st.subheader("User Activity Flow")
            if not df_activity.empty:
                # Assuming 'User Logged In' or 'Sign Up' equates to user engagement
                daily_activity = df_activity.groupby('created_at').size().reset_index(name='interactions')
                st.line_chart(daily_activity.set_index('created_at'))
            else:
                st.info("Not enough data to graph yet.")

        st.markdown("---")
        st.subheader("Query Complexity Analysis (Length in Characters)")
        if not df_queries.empty:
            # Scatter plot to show length of queries over time
            st.scatter_chart(df_queries, x='created_at', y='sql_length', color='#FF4B4B')

    except Exception as e:
        st.warning(f"Ensure your RLS policies allow Admin reads. Error: {e}")
