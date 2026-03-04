import streamlit as st
from supabase import create_client, Client
import sqlglot
from sqlglot import exp
import graphviz
from collections import defaultdict
import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="SQL-Flow SaaS", layout="wide")

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

# --- HELPER FUNCTIONS ---
def log_activity(action, details=""):
    """Tracks user activity for the admin dashboard."""
    user_id = st.session_state.user.id if st.session_state.user else None
    try:
        supabase.table("activity_logs").insert({"user_id": user_id, "action": action, "details": details}).execute()
    except Exception as e:
        print(f"Tracking error: {e}")

# --- MAIN APP UI ---
st.title("🔗 SQL-Flow: Lineage & Analytics")

tab_intro, tab_tool, tab_projects, tab_account, tab_admin = st.tabs([
    "📖 Intro & Examples", 
    "🛠️ Lineage Tool", 
    "📁 My Projects", 
    "👤 Account", 
    "👑 Admin Board"
])

# ==========================================
# TAB 1: INTRODUCTION & EXAMPLES
# ==========================================
with tab_intro:
    st.header("Welcome to SQL-Flow")
    st.markdown("""
    Instantly visualize complex SQL dependencies, track downstream impacts, and save your work. 
    **Use it anonymously, or create an account to save projects.**
    
    *Need help? Contact us at support@sqlflow.com*
    """)
    
    st.subheader("Load an Example")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Load Basic E-commerce SQL"):
            st.session_state.editor_sql = """WITH raw_users AS (SELECT id, name FROM db.users),
active_users AS (SELECT * FROM raw_users WHERE status = 'active')
SELECT * FROM active_users;"""
            st.success("Loaded! Go to the '🛠️ Lineage Tool' tab.")
            log_activity("Loaded Example", "E-commerce")
            
    with col2:
        if st.button("Load Complex Finance SQL"):
            st.session_state.editor_sql = """WITH q1_rev AS (SELECT * FROM (SELECT id, amount FROM db.finance) AS sub1),
q2_rev AS (SELECT id, amount FROM db.finance_q2)
SELECT * FROM q1_rev UNION ALL SELECT * FROM q2_rev;"""
            st.success("Loaded! Go to the '🛠️ Lineage Tool' tab.")
            log_activity("Loaded Example", "Finance")

# ==========================================
# TAB 2: LINEAGE TOOL (GUEST & LOGGED IN)
# ==========================================
with tab_tool:
    col_input, col_viz = st.columns([1, 1.5])
    
    with col_input:
        st.subheader("SQL Editor")
        uploaded_file = st.file_uploader("Upload .sql file", type=["sql", "txt"])
        
        if uploaded_file:
            st.session_state.editor_sql = uploaded_file.getvalue().decode("utf-8")
            
        sql_input = st.text_area("Your Query:", value=st.session_state.editor_sql, height=300)
        analyze_btn = st.button("Parse SQL & Generate Map", type="primary")
        
        # Save Work Logic (Only if logged in)
        if st.session_state.user:
            st.markdown("---")
            st.subheader("💾 Save to Project")
            
            # Fetch user's projects
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
        else:
            st.info("💡 Log in via the Account tab to save your work.")

    # Parsing & Visualization Logic
    if analyze_btn and sql_input:
        log_activity("Parsed SQL")
        try:
            parsed_query = sqlglot.parse_one(sql_input)
            downstream_map = defaultdict(set)
            upstream_map = defaultdict(set)
            all_nodes = set()
            
            # AST Subquery climbing logic
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
            st.subheader("Interactive Graph")
            
            c1, c2 = st.columns(2)
            with c1:
                analysis_mode = st.radio("Mode:", ["Default View", "🔴 Downstream Impact", "🟠 Upstream Root Cause"])
            with c2:
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

            graph = graphviz.Digraph(engine='dot')
            graph.attr(rankdir='LR', size='10,10')
            graph.attr('node', shape='cylinder', style='filled', fontname='Helvetica')

            for node in data["nodes"]:
                fill_color = 'lightblue'
                if node in highlighted:
                    fill_color = '#ff6b6b' if "Downstream" in analysis_mode else '#ffb067'
                elif node == "Final_Output":
                    fill_color = 'lightgreen'
                elif node not in data["upstream"] and node != "Final_Output":
                    fill_color = 'lightgrey'
                
                shape = 'box' if node == "Final_Output" else 'cylinder'
                graph.node(node, "Final Output" if node == "Final_Output" else node, fillcolor=fill_color, shape=shape)

            for parent, children in data["downstream"].items():
                for child in children:
                    edge_color = 'red' if ("Downstream" in analysis_mode and parent in highlighted and child in highlighted) else 'black'
                    if "Upstream" in analysis_mode and parent in highlighted and child in highlighted: edge_color = 'orange'
                    graph.edge(parent, child, color=edge_color, penwidth='2' if edge_color != 'black' else '1')

            st.graphviz_chart(graph, use_container_width=True)

# ==========================================
# TAB 3: MY PROJECTS
# ==========================================
with tab_projects:
    if st.session_state.user:
        st.header("Your Workspace")
        
        new_proj = st.text_input("Create New Project")
        if st.button("Create Project") and new_proj:
            supabase.table("projects").insert({"user_id": st.session_state.user.id, "name": new_proj}).execute()
            st.success("Project created!")
            st.rerun()

        st.markdown("### Saved Queries")
        projects_res = supabase.table("projects").select("id, name").eq("user_id", st.session_state.user.id).execute()
        
        for p in projects_res.data:
            with st.expander(f"📁 {p['name']}"):
                queries_res = supabase.table("queries").select("*").eq("project_id", p['id']).execute()
                for q in queries_res.data:
                    st.markdown(f"**{q['name']}**")
                    st.code(q['sql_text'], language="sql")
    else:
        st.warning("Please log in to manage projects.")

# ==========================================
# TAB 4: ACCOUNT (AUTH)
# ==========================================
with tab_account:
    if not st.session_state.user:
        st.header("Authentication")
        auth_mode = st.radio("Select Action", ["Login", "Sign Up", "Forgot Password"])
        
        email = st.text_input("Email")
        if auth_mode != "Forgot Password":
            password = st.text_input("Password", type="password")
            
        if st.button(auth_mode):
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
                    st.success("Password reset link sent!")
            except Exception as e:
                st.error(f"Authentication Error: {e}")
    else:
        st.success(f"Welcome, {st.session_state.user.email}")
        if st.button("Log Out"):
            log_activity("User Logged Out")
            supabase.auth.sign_out()
            st.session_state.user = None
            st.rerun()

# ==========================================
# TAB 5: ADMIN BOARD
# ==========================================
with tab_admin:
    if st.session_state.user and st.session_state.user.email == st.secrets["ADMIN_EMAIL"]:
        st.header("Admin Dashboard: App Usage")
        
        try:
            # Fetch aggregate stats
            users = supabase.auth.admin.list_users() # Note: requires service_role key for actual admin rights in production
            queries = supabase.table("queries").select("id", count="exact").execute()
            activity = supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(20).execute()
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Saved Queries", queries.count)
            col2.metric("Recent Activity Events", len(activity.data))
            
            st.subheader("Recent Activity Stream")
            for act in activity.data:
                user_label = "Guest" if not act['user_id'] else "Registered User"
                st.markdown(f"- **{act['action']}** by *{user_label}* ({act['created_at'][:10]}) - {act['details']}")
                
        except Exception as e:
            st.warning("Ensure your Supabase policies allow Admin reads, or use a Service Role Key for Admin stats.")
    else:
        st.error("🔒 You do not have permission to view the Admin Board.")
