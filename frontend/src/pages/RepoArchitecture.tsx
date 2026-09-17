import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import ReactFlow, { Background, Controls, MarkerType, type Edge, type Node } from "reactflow";
import "reactflow/dist/style.css";
import RepoTabs from "../components/RepoTabs";
import Sidebar from "../components/Sidebar";
import {
  fetchArchitecture,
  fetchDrift,
  type ArchitectureGraph,
  type ArchitectureNode,
  type DriftItem,
} from "../lib/api";

function layoutNodes(nodes: ArchitectureNode[]): Node[] {
  // No layout engine dependency (dagre etc.) -- a simple grid is enough
  // for a handful of modules and keeps the bundle small.
  const cols = Math.max(Math.ceil(Math.sqrt(nodes.length)), 1);
  return nodes.map((n, i) => ({
    id: n.id,
    data: { label: n.label },
    position: { x: (i % cols) * 220, y: Math.floor(i / cols) * 140 },
    style: {
      background: "#161B22",
      border: "1px solid #30363D",
      borderRadius: 8,
      color: "#E6EDF3",
      padding: 10,
      fontSize: 13,
    },
  }));
}

function RepoArchitecture() {
  const { repoId } = useParams<{ repoId: string }>();
  const [graph, setGraph] = useState<ArchitectureGraph | null>(null);
  const [drifts, setDrifts] = useState<DriftItem[]>([]);
  const [selectedNode, setSelectedNode] = useState<ArchitectureNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!repoId) return;
    setLoading(true);
    setError(null);
    try {
      const [arch, driftList] = await Promise.all([
        fetchArchitecture(repoId),
        fetchDrift(repoId).catch(() => []),
      ]);
      setGraph(arch);
      setDrifts(driftList);
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || "Could not load the architecture map. The repo may not have finished indexing yet.");
    } finally {
      setLoading(false);
    }
  }, [repoId]);

  useEffect(() => {
    load();
  }, [load]);

  const nodes: Node[] = useMemo(() => (graph ? layoutNodes(graph.nodes) : []), [graph]);
  const edges: Edge[] = useMemo(
    () =>
      graph
        ? graph.edges.map((e, i) => ({
            id: `e${i}`,
            source: e.source,
            target: e.target,
            label: e.label,
            markerEnd: { type: MarkerType.ArrowClosed },
            style: { stroke: "#30363D" },
          }))
        : [],
    [graph]
  );

  function handleNodeClick(_event: unknown, node: Node) {
    const match = graph?.nodes.find((n) => n.id === node.id) ?? null;
    setSelectedNode(match);
  }

  return (
    <div className="app-shell">
      <Sidebar activeRepoId={repoId} linkTo="architecture" />
      <div className="main-panel">
        <div className="main-panel-header">
          <h2>Architecture map</h2>
          <RepoTabs active="architecture" />
          <button className="btn btn-outline btn-sm" onClick={load} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        <div className="main-panel-body" style={{ padding: 0 }}>
          {error && (
            <p className="error-text" style={{ padding: 24 }}>
              {error}
            </p>
          )}
          {!error && (
            <div className="architecture-layout">
              <div className="architecture-graph">
                {nodes.length > 0 ? (
                  <ReactFlow nodes={nodes} edges={edges} onNodeClick={handleNodeClick} fitView>
                    <Background color="#30363D" />
                    <Controls />
                  </ReactFlow>
                ) : (
                  <div className="empty-state">
                    <p>{loading ? "Analyzing codebase…" : "No architecture data yet."}</p>
                  </div>
                )}
              </div>
              <div className="architecture-detail">
                {selectedNode ? (
                  <>
                    <span className="node-type-badge">{selectedNode.type}</span>
                    <h3>{selectedNode.label}</h3>
                    <p>{selectedNode.description}</p>
                  </>
                ) : (
                  <p className="chat-loading">Click a node to see its description.</p>
                )}

                {drifts.length > 0 && (
                  <>
                    <h3 style={{ marginTop: 28 }}>Drift alerts</h3>
                    <div className="drift-list">
                      {drifts.map((d, i) => (
                        <div className="drift-item" key={i}>
                          <span className={`severity ${d.severity}`}>{d.severity}</span>
                          {d.description}
                          {d.file && (
                            <div
                              style={{
                                marginTop: 4,
                                color: "var(--color-text-dim)",
                                fontFamily: "var(--font-mono)",
                                fontSize: 12,
                              }}
                            >
                              {d.file}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default RepoArchitecture;
