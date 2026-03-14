Visualization & Architecture Optimization Plan
This plan introduces a graph-based visualization (Obsidians-style) and an interactive playground to help users understand their codebase structure and semantic "memory" (observations).

User Review Required
IMPORTANT

This plan adds a new /analysis/graph endpoint and significantly enhances the 
memory_viewer.py
 (renaming it to a more comprehensive visualizer). It does not modify existing indexing or storage logic, so it is non-breaking.

Proposed Changes
[Backend] CodeIndex API
Add support for graph data extraction and enhanced analysis reporting.

[MODIFY] 
analysis.py
Add extract_graph_data function to build a node-link model from the database.
Enhance 
analyze_dependencies
 to return structured edges for the graph.
[MODIFY] 
server.py
Add /analysis/graph endpoint.
Update MCP tools to include a graph retrieval tool.
[Frontend] Visualizer & Playground
Upgrade the visualization experience from a simple list to a rich interactive dashboard.

[MODIFY] 
memory_viewer.py
[NEW] Implement a Graph View using a force-directed layout (e.g., D3 or Force-Graph).
[NEW] Add a "Playground" mode to visualize vector search results and chunking.
Improve UI/UX with a modern, glassmorphic design.
Architecture Recommendations (Optimization)
Semantic Backlinks: Automatically generate "backlinks" between memory_observations and the code chunks they cite. This enables "Discovery" – seeing what high-level thoughts exist for a specific function.
Cluster Visualization: Use the 
embedding
 data to visualize "clusters" of similar code in the graph, even if they aren't directly imported.
Lazy Loading: The graph should be "explorable" – users click a node to expand its neighbors, preventing performance issues with massive repos.
Verification Plan
Automated Tests
pytest tests/test_server.py: Verify the new /analysis/graph endpoint returns valid JSON with 
nodes
 and links.
pytest tests/test_analysis.py: Verify dependency extraction consistency.
Manual Verification
Run python -m codeindex.cli serve
Navigate to http://localhost:9090/memory/viewer (or the new /playground route).
Interact with the graph: click nodes, hover to see snippets, and use the playground to test semantic search.
Verify that clicking an Observation highlights the relevant code file in the graph.
