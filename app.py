import streamlit as st
import sqlglot
from sqlglot import exp
import graphviz
from collections import defaultdict

# --- Page Config ---
st.set_page_config(page_title="SQL-Flow V2", layout="wide")
st.title("🔗 SQL-Flow: Lineage & Impact Analysis")

# --- Initialize Session State Memory ---
if "lineage_data" not in st.session_state:
    st.session_state.lineage_data = None

# --- Sidebar / Inputs ---
with st.sidebar:
    st.header("Input Method")
    uploaded_file = st.file_uploader("Upload SQL File", type=["sql", "txt"])
    st.markdown("---")
    st.markdown("💡 **Tip:** Uploading a file will automatically populate the editor. You can then edit the SQL live before generating the map.")

# --- UI Layout ---
col_input, col_viz = st.columns([1, 1.5])

with col_input:
    st.subheader("SQL Editor")
    default_sql = """WITH raw_sales AS (
    SELECT * FROM source_db.sales_data
),
filtered_sales AS (
    SELECT id, amount, region FROM raw_sales WHERE amount > 100
),
regional_summary AS (
    SELECT region, SUM(amount) as total FROM filtered_sales GROUP BY region
)
SELECT * FROM regional_summary;"""

    # Determine what text to show in the editor
    if uploaded_file is not None:
        file_text = uploaded_file.getvalue().decode("utf-8")
    else:
        file_text = default_sql

    # The text area uses the file text (if uploaded) or the default text
    sql_input = st.text_area("Your Query:", value=file_text, height=400)
    analyze_btn = st.button("Parse SQL & Generate Map", type="primary")

# --- Parsing Logic (Runs only when button is clicked) ---
# --- Parsing Logic (Runs only when button is clicked) ---
if analyze_btn and sql_input:
    try:
        parsed_query = sqlglot.parse_one(sql_input)
        
        downstream_map = defaultdict(set)
        upstream_map = defaultdict(set)
        all_nodes = set()
        
        # Find ALL tables in the entire query, no matter how deeply nested
        for table in parsed_query.find_all(exp.Table):
            source_name = table.name
            all_nodes.add(source_name)
            
            # Walk up the AST to see where this table lives
            parent_cte = None
            current_node = table
            
            while current_node:
                if isinstance(current_node, exp.CTE):
                    parent_cte = current_node
                    break
                current_node = current_node.parent
                
            if parent_cte:
                # The table is inside a CTE (even if it's inside a subquery inside the CTE)
                cte_name = parent_cte.alias
                all_nodes.add(cte_name)
                downstream_map[source_name].add(cte_name)
                upstream_map[cte_name].add(source_name)
            else:
                # The table is in the main query (even if it's inside a nested subquery)
                all_nodes.add("Final_Output")
                downstream_map[source_name].add("Final_Output")
                upstream_map["Final_Output"].add(source_name)

        # Save to session memory
        st.session_state.lineage_data = {
            "downstream": downstream_map,
            "upstream": upstream_map,
            "nodes": all_nodes
        }
        
    except Exception as e:
        st.error(f"Failed to parse SQL: {e}")
        st.session_state.lineage_data = None

# --- Visualization & Interactive Analysis ---
with col_viz:
    if st.session_state.lineage_data:
        data = st.session_state.lineage_data
        
        st.subheader("Interactive Graph")
        
        # UI controls for analysis
        col_mode, col_target = st.columns(2)
        with col_mode:
            analysis_mode = st.radio(
                "Select Analysis Mode:", 
                ["Default View", "🔴 Downstream Impact (Domino Effect)", "🟠 Upstream Root Cause"]
            )
        with col_target:
            target_node = st.selectbox(
                "Select Target Table/CTE:", 
                options=["-- None --"] + sorted(list(data["nodes"]))
            )

        # Recursive function to trace paths
        def trace_lineage(node, mapping, visited=None):
            if visited is None:
                visited = set()
            for related_node in mapping.get(node, []):
                if related_node not in visited:
                    visited.add(related_node)
                    trace_lineage(related_node, mapping, visited)
            return visited

        # Determine which nodes to highlight
        highlighted_nodes = set()
        if target_node != "-- None --":
            if "Downstream" in analysis_mode:
                highlighted_nodes = trace_lineage(target_node, data["downstream"])
                highlighted_nodes.add(target_node)
            elif "Upstream" in analysis_mode:
                highlighted_nodes = trace_lineage(target_node, data["upstream"])
                highlighted_nodes.add(target_node)

        # Draw the Graph
        graph = graphviz.Digraph(engine='dot')
        graph.attr(rankdir='LR', size='10,10')
        graph.attr('node', shape='cylinder', style='filled', fontname='Helvetica')

        # Add all nodes
        for node in data["nodes"]:
            if node in highlighted_nodes:
                fill_color = '#ff6b6b' if "Downstream" in analysis_mode else '#ffb067'
            else:
                fill_color = 'lightgreen' if node == "Final_Output" else 'lightblue'
                if node not in data["upstream"] and node != "Final_Output": 
                    fill_color = 'lightgrey'
            
            shape = 'box' if node == "Final_Output" else 'cylinder'
            label = "Final Output" if node == "Final_Output" else node
            
            graph.node(node, label, fillcolor=fill_color, shape=shape)

        # Add all edges
        for parent, children in data["downstream"].items():
            for child in children:
                if parent in highlighted_nodes and child in highlighted_nodes:
                    edge_color = 'red' if "Downstream" in analysis_mode else 'orange'
                    graph.edge(parent, child, color=edge_color, penwidth='2')
                else:
                    graph.edge(parent, child, color='black')

        # Render the chart
        st.graphviz_chart(graph, use_container_width=True)
        
        # Summary messages
        if target_node != "-- None --":
            if "Downstream" in analysis_mode and len(highlighted_nodes) > 1:
                st.warning(f"🚨 Changing `{target_node}` impacts **{len(highlighted_nodes)-1}** downstream components.")
            elif "Upstream" in analysis_mode and len(highlighted_nodes) > 1:
                st.info(f"🔍 `{target_node}` relies on **{len(highlighted_nodes)-1}** upstream data sources.")
