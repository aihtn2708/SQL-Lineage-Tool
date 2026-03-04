import streamlit as st
import sqlglot
from sqlglot import exp
import graphviz

# --- Page Config ---
st.set_page_config(page_title="SQL-Flow V1", layout="wide")
st.title("🔗 SQL-Flow: Instant Data Lineage")
st.markdown("Upload a `.sql` file or paste your query below to generate a dependency graph.")

# --- Sidebar / Inputs ---
with st.sidebar:
    st.header("Input Method")
    uploaded_file = st.file_uploader("Upload SQL File", type=["sql", "txt"])

# Main layout
col_input, col_viz = st.columns([1, 1.5])

with col_input:
    st.subheader("SQL Editor")
    # Default placeholder text
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

    # If file is uploaded, use its text; otherwise use text area
    if uploaded_file is not None:
        file_text = uploaded_file.getvalue().decode("utf-8")
        sql_input = st.text_area("Your Query:", value=file_text, height=500)
    else:
        sql_input = st.text_area("Your Query:", value=default_sql, height=500)

    analyze_btn = st.button("Draw Lineage Flow", type="primary")

# --- Core Logic & Visualization ---
from collections import defaultdict

# --- Core Logic & Visualization ---
with col_viz:
    st.subheader("Data Lineage & Impact Analysis")
    
    if analyze_btn and sql_input:
        try:
            # 1. Parse the SQL
            parsed_query = sqlglot.parse_one(sql_input)
            ctes = list(parsed_query.find_all(exp.CTE))
            
            # 2. Track Dependencies (Parent -> Children)
            dependency_map = defaultdict(list)
            all_known_nodes = set()
            
            for cte in ctes:
                cte_name = cte.alias
                all_known_nodes.add(cte_name)
                
                for table in cte.find_all(exp.Table):
                    source_name = table.name
                    all_known_nodes.add(source_name)
                    # Map the source table to the CTE that uses it
                    dependency_map[source_name].append(cte_name)

            # Map the Final Output
            if isinstance(parsed_query, exp.Select):
                for table in parsed_query.find_all(exp.Table):
                    if table.parent is parsed_query or table.parent.parent is parsed_query:
                        dependency_map[table.name].append("Final_Output")
                        all_known_nodes.add("Final_Output")

            # 3. Interactive UI for Impact Analysis
            st.markdown("---")
            target_node = st.selectbox(
                "🚨 Select a Table/CTE to simulate a change (Domino Effect):", 
                options=["-- None --"] + sorted(list(all_known_nodes))
            )

            # 4. Calculate the Domino Effect (Recursive function)
            def get_downstream_impact(node, dep_map, visited=None):
                if visited is None:
                    visited = set()
                for child in dep_map.get(node, []):
                    if child not in visited:
                        visited.add(child)
                        get_downstream_impact(child, dep_map, visited)
                return visited
            
            impacted_nodes = set()
            if target_node != "-- None --":
                impacted_nodes = get_downstream_impact(target_node, dependency_map)
                # Include the target node itself in the highlight
                impacted_nodes.add(target_node) 

            # 5. Initialize & Draw Graphviz
            graph = graphviz.Digraph(engine='dot')
            graph.attr(rankdir='LR', size='8,8')
            graph.attr('node', shape='cylinder', style='filled', fontname='Helvetica')

            # Draw nodes with conditional coloring
            drawn_nodes = set()
            for parent, children in dependency_map.items():
                # Draw Parent
                if parent not in drawn_nodes:
                    color = '#ff6b6b' if parent in impacted_nodes else 'lightgrey' # Red if impacted
                    graph.node(parent, parent, fillcolor=color)
                    drawn_nodes.add(parent)
                
                # Draw Children & Edges
                for child in children:
                    if child not in drawn_nodes:
                        color = '#ff6b6b' if child in impacted_nodes else 'lightblue'
                        if child == "Final_Output":
                            color = '#ff6b6b' if child in impacted_nodes else 'lightgreen'
                            graph.node(child, "Final Output", fillcolor=color, shape='box')
                        else:
                            graph.node(child, child, fillcolor=color)
                        drawn_nodes.add(child)
                    
                    # Connect them
                    edge_color = 'red' if (parent in impacted_nodes and child in impacted_nodes) else 'black'
                    graph.edge(parent, child, color=edge_color)

            st.graphviz_chart(graph, use_container_width=True)
            
            # Print a summary warning if a target is selected
            if target_node != "-- None --" and len(impacted_nodes) > 1:
                st.warning(f"⚠️ **Warning:** Changing `{target_node}` will directly impact {len(impacted_nodes)-1} downstream components.")

        except sqlglot.errors.ParseError as e:
            st.error("SQL Syntax Error. Please check your query.")
