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
with col_viz:
    st.subheader("Data Lineage Map")
    
    if analyze_btn and sql_input:
        try:
            # 1. Initialize Graphviz Directed Graph
            graph = graphviz.Digraph(engine='dot')
            graph.attr(rankdir='LR', size='8,8') # LR = Left to Right flow
            graph.attr('node', shape='cylinder', style='filled', fillcolor='lightblue', fontname='Helvetica')

            # 2. Parse the SQL
            parsed_query = sqlglot.parse_one(sql_input)
            
            # 3. Extract CTEs and map dependencies
            ctes = list(parsed_query.find_all(exp.CTE))
            cte_names = [cte.alias for cte in ctes]

            # Track what we've added to avoid duplicate nodes
            added_nodes = set()

            for cte in ctes:
                cte_name = cte.alias
                if cte_name not in added_nodes:
                    graph.node(cte_name, cte_name)
                    added_nodes.add(cte_name)
                
                # Find all tables referenced inside this specific CTE
                for table in cte.find_all(exp.Table):
                    source_name = table.name
                    if source_name not in added_nodes:
                        # Color source tables differently
                        graph.node(source_name, source_name, fillcolor='lightgrey')
                        added_nodes.add(source_name)
                    
                    # Draw the line from the source table to the CTE
                    graph.edge(source_name, cte_name)

            # 4. Handle the Final SELECT statement
            # Find the main SELECT scope (excluding the CTE definitions)
            graph.node("Final_Output", "Final Output", fillcolor='lightgreen', shape='box')
            
            # We look at the base tables of the final query
            if isinstance(parsed_query, exp.Select):
                for table in parsed_query.find_all(exp.Table):
                    # Only link to the final output if it's referenced in the main query, not inside a CTE
                    # (This is a simplified check for V1)
                    if table.parent is parsed_query or table.parent.parent is parsed_query:
                        graph.edge(table.name, "Final_Output")

            # 5. Render in Streamlit
            st.graphviz_chart(graph, use_container_width=True)
            st.success("Lineage mapped successfully!")

        except sqlglot.errors.ParseError as e:
            st.error(f"SQL Syntax Error. Please check your query.\n\nDetails: {e}")
        except Exception as e:
            st.error(f"An error occurred while mapping: {e}")
