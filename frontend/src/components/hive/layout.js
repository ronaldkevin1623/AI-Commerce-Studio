import { CLUSTERS, SPECIALISTS, TOOLS, TUNABLE } from "./topology";

/**
 * Default hive layout — five columns, left to right:
 *   you → hive → cluster → specialist → tool
 *
 * Every node is described by its CENTRE (cx, cy) plus a box, so edges can
 * anchor to left/right edges without each caller re-deriving the geometry.
 * Dragging only ever overrides cx/cy; nothing here carries meaning.
 */

export const W = 960;
export const FULL_H = 690;

const COL = { you: 52, hive: 170, cluster: 310, specialist: 560, tool: 850 };
const SIZE = {
  you: { w: 44, h: 44 },
  hive: { w: 64, h: 64 },
  cluster: { w: 132, h: 36 },
  specialist: { w: 142, h: 32 },
  tool: { w: 150, h: 28 },
};

const ROW_STEP = 46;
const CLUSTER_GAP = 24;
const FIRST_ROW = 34;
const PAD = 34;

/**
 * A subset of clusters can be laid out on its own — the console turn only
 * ever runs the buyer pipeline, so rendering the growth and post-purchase
 * bands inside every chat turn would be noise, not information. The /hive
 * page passes no filter and gets the whole thing.
 */
function visible(clusterIds, onlyTunable) {
  const clusters = clusterIds ? CLUSTERS.filter((c) => clusterIds.includes(c.id)) : CLUSTERS;
  let specialists = SPECIALISTS.filter((s) => clusters.some((c) => c.id === s.cluster));
  // Narrowed to the nodes that have something to turn. The rest are real —
  // Payment does create the Razorpay order — but they take no parameter, so
  // on a page being used as a control surface they are captions.
  if (onlyTunable) {
    specialists = specialists.filter((s) => TUNABLE.has(s.id));
  }
  // A cluster is placed at the midpoint of its own children, so one left
  // with none produces NaN and the whole band — YOU, the hive, the cluster
  // — lands in the top-left corner. Post-purchase has no tunable node, so
  // narrowing emptied it. An empty band has nothing to say anyway.
  const populated = clusters.filter(
    (c) => specialists.some((s) => s.cluster === c.id));
  const toolIds = new Set(specialists.flatMap((s) => s.tools ?? []));
  const tools = TOOLS.filter((t) => toolIds.has(t.id));
  return { clusters: populated, specialists, tools };
}

export function layoutHeight(clusterIds, onlyTunable) {
  const { clusters, specialists } = visible(clusterIds, onlyTunable);
  const rows = specialists.length * ROW_STEP + (clusters.length - 1) * CLUSTER_GAP;
  return Math.max(rows + PAD, 200);
}

export function defaultLayout(clusterIds, onlyTunable) {
  const { clusters, specialists, tools } = visible(clusterIds, onlyTunable);
  const height = layoutHeight(clusterIds, onlyTunable);
  const nodes = [];

  // Specialists stack in cluster order, with a gap between groups so the
  // halves of the product read as bands rather than one long list.
  const specialistY = {};
  let y = FIRST_ROW;
  for (const cluster of clusters) {
    for (const s of specialists.filter((s) => s.cluster === cluster.id)) {
      specialistY[s.id] = y;
      y += ROW_STEP;
    }
    y += CLUSTER_GAP;
  }

  for (const s of specialists) {
    nodes.push({ ...s, kind: "specialist", cx: COL.specialist, cy: specialistY[s.id], ...SIZE.specialist });
  }

  // A cluster sits at the midpoint of the specialists it owns.
  const clusterY = {};
  for (const cluster of clusters) {
    const ys = specialists.filter((s) => s.cluster === cluster.id).map((s) => specialistY[s.id]);
    clusterY[cluster.id] = (Math.min(...ys) + Math.max(...ys)) / 2;
    nodes.push({ ...cluster, kind: "cluster", cx: COL.cluster, cy: clusterY[cluster.id], ...SIZE.cluster });
  }

  // Tools spread evenly down the right-hand column — hover dimming is what
  // keeps the crossings legible, not clever routing.
  const step = height / (tools.length + 1);
  tools.forEach((t, i) => {
    nodes.push({ ...t, kind: "tool", cx: COL.tool, cy: step * (i + 1), ...SIZE.tool });
  });

  const hubY =
    Object.values(clusterY).reduce((a, b) => a + b, 0) / Object.keys(clusterY).length;

  nodes.push({ id: "hive", label: "Hive", kind: "hive", cx: COL.hive, cy: hubY, ...SIZE.hive });
  nodes.push({ id: "you", label: "You", kind: "you", cx: COL.you, cy: hubY, ...SIZE.you });

  return nodes;
}

/** Directed edges, derived from the topology rather than hand-listed. */
export function edges(clusterIds, onlyTunable) {
  const { clusters, specialists } = visible(clusterIds, onlyTunable);
  const list = [{ from: "you", to: "hive" }];
  for (const c of clusters) list.push({ from: "hive", to: c.id });
  for (const s of specialists) {
    list.push({ from: s.cluster, to: s.id });
    for (const t of s.tools ?? []) list.push({ from: s.id, to: t, kind: "tool" });
  }
  return list;
}

export function rightAnchor(n) {
  return { x: n.cx + n.w / 2, y: n.cy };
}

export function leftAnchor(n) {
  return { x: n.cx - n.w / 2, y: n.cy };
}

export function edgePath(from, to) {
  const a = rightAnchor(from);
  const b = leftAnchor(to);
  const midX = (a.x + b.x) / 2;
  return `M ${a.x} ${a.y} C ${midX} ${a.y}, ${midX} ${b.y}, ${b.x} ${b.y}`;
}
