import streamlit as st
import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import math

st.set_page_config(page_title="RouteIQ | Logistics Control", page_icon="🚚", layout="wide")

# -------------------- Demo road network --------------------
# Coordinates are illustrative positions, not real geographic locations.
NODES = {
    "Warehouse": (0.0, 2.0),
    "North Hub": (1.4, 3.2),
    "West Junction": (1.5, 1.0),
    "Central Hub": (3.0, 2.4),
    "East Junction": (4.3, 1.0),
    "Customer A": (5.3, 2.7),
    "Customer B": (6.1, 0.4),
    "Airport Depot": (4.8, 3.8),
}
ROADS = [
    ("Warehouse", "North Hub", 4.0, 22),
    ("Warehouse", "West Junction", 3.5, 28),
    ("North Hub", "Central Hub", 3.2, 32),
    ("West Junction", "Central Hub", 2.8, 18),
    ("North Hub", "Airport Depot", 4.8, 24),
    ("Central Hub", "Airport Depot", 2.6, 38),
    ("Central Hub", "East Junction", 3.0, 26),
    ("West Junction", "East Junction", 4.7, 48),
    ("East Junction", "Customer A", 3.1, 20),
    ("Airport Depot", "Customer A", 2.4, 16),
    ("East Junction", "Customer B", 2.6, 36),
    ("Central Hub", "Customer B", 5.0, 30),
]
NAMES = list(NODES.keys())
TRAFFIC_LEVELS = {"Low": 0.75, "Normal": 1.0, "Busy": 1.25, "Rush hour": 1.55}

def membership(traffic):
    """Small fuzzy system: membership degrees for Low, Medium and High traffic."""
    low = max(0.0, min(1.0, (50 - traffic) / 35))
    medium = max(0.0, min(1.0, 1 - abs(traffic - 50) / 30))
    high = max(0.0, min(1.0, (traffic - 45) / 40))
    total = low + medium + high
    if total:
        return {"Low": low / total, "Medium": medium / total, "High": high / total}
    return {"Low": 0.0, "Medium": 1.0, "High": 0.0}

def traffic_penalty(traffic):
    m = membership(traffic)
    return 10*m["Low"] + 45*m["Medium"] + 85*m["High"]

def build_graph(traffic_mode, incident_road, incident_severity, closed_roads):
    g = nx.Graph()
    for a, b, distance, base_traffic in ROADS:
        key = f"{a} — {b}"
        if key in closed_roads:
            continue
        traffic = min(100, round(base_traffic * TRAFFIC_LEVELS[traffic_mode]))
        if incident_road == key:
            traffic = min(100, round(traffic + incident_severity))
        speed = max(12, 48 * (1 - 0.006 * traffic))
        minutes = distance / speed * 60
        g.add_edge(a, b, distance=distance, traffic=traffic, minutes=minutes,
                   penalty=traffic_penalty(traffic), key=key)
    return g

def route_stats(g, path, priority):
    dist = mins = fuzzy = 0.0
    traffics = []
    for a, b in zip(path, path[1:]):
        e = g[a][b]
        dist += e["distance"]
        mins += e["minutes"]
        fuzzy += e["penalty"]
        traffics.append(e["traffic"])
    avg = sum(traffics)/len(traffics) if traffics else 0
    # Urgent deliveries care more about time; standard deliveries balance time and distance.
    score = dist*1.8 + mins*(1.45 if priority == "Urgent" else 0.8) + fuzzy*0.2
    return {"path": path, "distance": dist, "minutes": mins, "traffic": avg, "score": score}

def get_routes(g, source, destination, priority, limit=5):
    paths = nx.shortest_simple_paths(g, source, destination, weight="minutes")
    result = []
    for path in paths:
        result.append(route_stats(g, path, priority))
        if len(result) >= limit:
            break
    return result

def path_position(path, progress):
    points = [NODES[n] for n in path]
    lengths = []
    total = 0.0
    for p, q in zip(points, points[1:]):
        length = math.dist(p, q)
        lengths.append(length)
        total += length
    if not lengths or total == 0:
        return points[0]
    remaining = (progress / 100.0) * total
    for i, length in enumerate(lengths):
        if remaining <= length:
            frac = remaining / length if length else 0
            return (points[i][0] + (points[i+1][0]-points[i][0])*frac,
                    points[i][1] + (points[i+1][1]-points[i][1])*frac)
        remaining -= length
    return points[-1]

def make_map(g, chosen_route, all_routes, vehicle_progress):
    fig = go.Figure()
    recommended_edges = set()
    if chosen_route:
        recommended_edges = {frozenset((a,b)) for a,b in zip(chosen_route["path"], chosen_route["path"][1:])}
    # Draw road segments separately so each can have traffic color.
    for a, b, d in g.edges(data=True):
        x1, y1 = NODES[a]
        x2, y2 = NODES[b]
        color = "#ef4444" if d["traffic"] >= 65 else "#f59e0b" if d["traffic"] >= 40 else "#22c55e"
        width = 6 if frozenset((a,b)) in recommended_edges else 3
        fig.add_trace(go.Scatter(
            x=[x1, x2], y=[y1, y2], mode="lines",
            line=dict(color=color, width=width),
            hovertemplate=f"{a} ↔ {b}<br>{d['distance']:.1f} km · traffic {d['traffic']}/100<br>{d['minutes']:.1f} min<extra></extra>",
            showlegend=False
        ))
        fig.add_annotation(x=(x1+x2)/2, y=(y1+y2)/2, text=f"{d['distance']:.1f} km",
                           showarrow=False, font=dict(size=10, color="#cbd5e1"),
                           bgcolor="rgba(15,23,42,0.75)", borderpad=2)
    # Nodes
    fig.add_trace(go.Scatter(
        x=[NODES[n][0] for n in NAMES], y=[NODES[n][1] for n in NAMES],
        mode="markers+text", text=NAMES, textposition="top center",
        marker=dict(size=19, color="#e2e8f0", line=dict(color="#334155", width=2)),
        textfont=dict(color="#e2e8f0", size=11),
        hovertemplate="%{text}<extra></extra>", showlegend=False
    ))
    if chosen_route:
        vx, vy = path_position(chosen_route["path"], vehicle_progress)
        fig.add_trace(go.Scatter(
            x=[vx], y=[vy], mode="markers+text", text=["🚚 Vehicle"],
            textposition="bottom center",
            marker=dict(size=25, color="#38bdf8", symbol="diamond", line=dict(color="white", width=2)),
            textfont=dict(color="white", size=12),
            hovertemplate=f"Vehicle progress: {vehicle_progress}%<extra></extra>",
            showlegend=False
        ))
    fig.update_layout(
        height=520, margin=dict(l=10,r=10,t=10,b=10),
        paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
        xaxis=dict(visible=False, range=[-0.8, 7.0], fixedrange=True),
        yaxis=dict(visible=False, range=[-0.3, 4.5], fixedrange=True, scaleanchor="x", scaleratio=1),
        hoverlabel=dict(bgcolor="#111827", font_color="white"),
    )
    return fig

# ---------- Styling ----------
st.markdown("""
<style>
.stApp { background: #080e19; color: #e5e7eb; }
.block-container { padding-top: 1.4rem; max-width: 1500px; }
h1, h2, h3 { color: #f8fafc; }
[data-testid="stMetric"] { background: linear-gradient(135deg,#111c2e,#0e1726); padding: 16px; border: 1px solid #243247; border-radius: 14px; }
div[data-testid="stExpander"] { border: 1px solid #243247; border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

st.title("ROUTEIQ")
st.markdown("### Logistics intelligence · route planning · what-if simulation")
st.caption("Interactive student prototype · road, traffic and time values are simulated")

# Sidebar controls
with st.sidebar:
    st.markdown("## 🚚 Dispatch controls")
    source = st.selectbox("Origin", NAMES, index=NAMES.index("Warehouse"))
    dest_options = [n for n in NAMES if n != source]
    dest_default = "Customer A" if "Customer A" in dest_options else dest_options[0]
    destination = st.selectbox("Destination", dest_options, index=dest_options.index(dest_default))
    priority = st.radio("Shipment priority", ["Standard", "Urgent"], horizontal=True)
    traffic_mode = st.select_slider("City traffic", options=list(TRAFFIC_LEVELS.keys()), value="Normal")
    st.markdown("---")
    st.markdown("### ⚠️ What-if incident")
    road_keys = [f"{a} — {b}" for a,b,_,_ in ROADS]
    incident_road = st.selectbox("Create congestion on road", ["None"] + road_keys)
    incident_severity = st.slider("Extra congestion", 0, 70, 35, 5, disabled=(incident_road == "None"))
    closed_roads = st.multiselect("Close road(s)", road_keys)
    deadline_on = st.checkbox("Enforce delivery deadline")
    deadline = st.slider("Deadline (minutes)", 10, 120, 35, 5, disabled=not deadline_on)
    st.markdown("---")
    st.markdown("**Traffic legend**  🟢 Low · 🟠 Medium · 🔴 High")

graph = build_graph(traffic_mode, None if incident_road == "None" else incident_road,
                    incident_severity, closed_roads)

# Handle disconnected graph gracefully
routes = []
if source != destination and source in graph and destination in graph and nx.has_path(graph, source, destination):
    try:
        routes = get_routes(graph, source, destination, priority, limit=5)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        routes = []

if "progress" not in st.session_state:
    st.session_state.progress = 0

if routes:
    feasible = [r for r in routes if not deadline_on or r["minutes"] <= deadline]
    candidates = feasible if feasible else routes
    best = min(candidates, key=lambda r:r["score"])
else:
    best = None

# Top status
status_cols = st.columns([1.2,1,1,1])
with status_cols[0]:
    st.markdown("#### 🟢 Dispatch status")
    st.markdown("**Route engine ready**" if best else "**No available route**")
with status_cols[1]:
    st.metric("Routes evaluated", len(routes))
with status_cols[2]:
    st.metric("Traffic scenario", traffic_mode)
with status_cols[3]:
    st.metric("Incident", "Active" if incident_road != "None" else "None")

map_col, info_col = st.columns([1.55, 1])
with map_col:
    st.markdown("### 🗺️ Interactive road network")
    if best:
        st.plotly_chart(make_map(graph, best, routes, st.session_state.progress),
                        use_container_width=True, config={"displayModeBar": False})
        st.caption("Hover over roads for distance, traffic and estimated travel time. Thick highlighted roads show the recommended route.")
    else:
        st.warning("No route is available. Try reopening a closed road or choosing different locations.")

with info_col:
    st.markdown("### 🧠 AI dispatch recommendation")
    if best:
        st.markdown(f"<div style='padding:16px;border:1px solid #1d4ed8;border-radius:14px;background:linear-gradient(135deg,#10213b,#101827)'><div style='color:#93c5fd;font-size:12px;font-weight:700;letter-spacing:1px'>RECOMMENDED ROUTE</div><div style='font-size:20px;font-weight:700;margin-top:8px'>{' → '.join(best['path'])}</div><div style='color:#cbd5e1;margin-top:8px'>Best score among the current candidate routes</div></div>", unsafe_allow_html=True)
        k1,k2 = st.columns(2)
        k1.metric("Estimated travel time", f"{best['minutes']:.1f} min")
        k2.metric("Route distance", f"{best['distance']:.1f} km")
        k3,k4 = st.columns(2)
        k3.metric("Average traffic", f"{best['traffic']:.0f}/100")
        k4.metric("Decision score ↓", f"{best['score']:.1f}")
        if deadline_on and not feasible:
            st.warning(f"None of the candidate routes meets the {deadline}-minute deadline. Showing the best-scoring available route.")
        elif deadline_on:
            st.success(f"Recommendation meets the {deadline}-minute deadline.")
        if priority == "Urgent":
            reason = "Urgent priority increases the importance of estimated travel time."
        else:
            reason = "Standard priority balances distance, travel time and traffic penalty."
        st.info(f"**Why this route?** It has the lowest combined score among the evaluated candidates. {reason} Traffic penalty is calculated with fuzzy Low/Medium/High memberships.")
    else:
        st.info("Choose a reachable origin and destination to generate a recommendation.")

st.markdown("### 🎛️ Live vehicle simulation")
if best:
    st.write("Move the slider to move the delivery vehicle along the recommended route. Change traffic or create an incident in the sidebar to recalculate the route.")
    st.session_state.progress = st.slider("Vehicle progress", 0, 100, st.session_state.progress, 5, format="%d%%")
    if st.button("↻ Reset vehicle to start"):
        st.session_state.progress = 0
        st.rerun()
    st.progress(st.session_state.progress / 100)
    st.caption("This is a user-controlled simulation, not real GPS tracking.")

st.markdown("### 🛣️ Candidate route comparison")
if routes:
    rows = []
    for i, r in enumerate(routes, 1):
        rows.append({
            "Option": f"Route {i}",
            "Route": " → ".join(r["path"]),
            "Distance (km)": round(r["distance"], 1),
            "ETA (min)": round(r["minutes"], 1),
            "Avg traffic": round(r["traffic"]),
            "Score (lower is better)": round(r["score"], 1),
            "Deadline": ("✓" if not deadline_on or r["minutes"] <= deadline else "✕"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.write("No route comparison available for this selection.")

with st.expander("📚 AI concepts used (for your project review)"):
    st.markdown("""
    **Unit 3 — Knowledge Representation & Reasoning**
    - Facts represent locations, road connections, shipment priority and road status.
    - Expert rules: closed roads are excluded; urgent shipments place more weight on ETA; a deadline can filter candidate routes.
    - The app explains the selected route in plain language.

    **Unit 4 — Statistical Reasoning**
    - Fuzzy membership functions estimate how much a road belongs to Low, Medium and High traffic categories.
    - Those memberships are combined into a traffic penalty used by the route scoring function.
    - Traffic and travel times are simulated; the prototype does not claim to predict real-world traffic.

    **Route optimization**
    - NetworkX generates alternative paths in a graph.
    - A multi-factor score compares distance, estimated travel time and fuzzy traffic penalty.
    """)

with st.expander("📋 Road data (simulated)"):
    data = []
    for a,b,d,t in ROADS:
        key = f"{a} — {b}"
        scaled = min(100, round(t * TRAFFIC_LEVELS[traffic_mode]))
        if incident_road == key:
            scaled = min(100, scaled + incident_severity)
        data.append({"Road": key, "Distance km": d, "Traffic score": scaled,
                     "Status": "Closed" if key in closed_roads else "Open"})
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

st.markdown("<div style='text-align:center;color:#64748b;padding:20px 0'>ROUTEIQ · Educational prototype · Simulated data only</div>", unsafe_allow_html=True)
