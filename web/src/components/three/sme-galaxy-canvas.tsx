"use client";

import * as React from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Html, Line, OrbitControls, useCursor } from "@react-three/drei";
import { APPROVAL_BAR, GOOD } from "@/lib/decision";
import type { GalaxyPoint } from "./sme-galaxy";
import type { Palette } from "./theme-palette";

// ── the plot box ──────────────────────────────────────────────────────────────
// x = rating 3.8–5.0 · y = approval 60–100% · z = participation 0–100% (deeper = more of the
// room rated). Values outside the domain sit on the edge; the tooltip always carries the truth.
const W = 6;
const H = 3;
const D = 4;
const FLOOR = -H / 2;
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const X = (rating: number) => ((clamp(rating, 3.8, 5) - 3.8) / 1.2) * W - W / 2;
const Y = (approval: number) => ((clamp(approval, 60, 100) - 60) / 40) * H - H / 2;
const Z = (participation: number) => D / 2 - (clamp(participation, 0, 100) / 100) * D;
const RADIUS = (n: number) => Math.min(0.34, 0.05 + 0.034 * Math.sqrt(n));
const MAX_NODES = 150;
const CAMERA = new THREE.Vector3(6.4, 3.2, 7.7);
const TARGET = new THREE.Vector3(0, -0.35, 0);

type Node = GalaxyPoint & {
  x: number;
  y: number;
  z: number;
  r: number;
  attention: boolean;
};

function toNodes(points: GalaxyPoint[]): Node[] {
  return [...points]
    .filter((p) => p.avgRating != null)
    .sort((a, b) => b.n - a.n)
    .slice(0, MAX_NODES)
    .map((p) => {
      const rating = p.avgRating!;
      return {
        ...p,
        x: X(rating),
        // No vote recorded → sits on the bar: a missing signal is never a penalty.
        y: Y(p.approval ?? APPROVAL_BAR),
        z: Z(p.avgParticipation ?? 50),
        r: RADIUS(p.n),
        attention: rating < GOOD || (p.approval != null && p.approval < APPROVAL_BAR),
      };
    });
}

const mix = (a: string, b: string, t: number) => new THREE.Color(a).lerp(new THREE.Color(b), t);

// ── labels ───────────────────────────────────────────────────────────────────
function Label({
  at,
  children,
  strong,
  caption,
}: {
  at: [number, number, number];
  children: React.ReactNode;
  strong?: boolean;
  caption?: boolean;
}) {
  return (
    <Html position={at} center zIndexRange={[20, 0]} wrapperClass="pointer-events-none">
      <span
        className={
          caption
            ? "text-muted-foreground text-[11px] font-medium tracking-wide whitespace-nowrap"
            : strong
              ? "text-foreground font-mono text-[10px] font-semibold whitespace-nowrap"
              : "text-muted-foreground font-mono text-[10px] whitespace-nowrap"
        }
      >
        {children}
      </span>
    </Html>
  );
}

// ── the box: floor grid, edges, the two decision planes ──────────────────────
function Frame({ palette }: { palette: Palette }) {
  const grid = React.useMemo(() => {
    const pts: number[] = [];
    for (const r of [3.8, 4.0, 4.2, 4.4, 4.6, 4.8, 5.0]) pts.push(X(r), FLOOR, -D / 2, X(r), FLOOR, D / 2);
    for (const p of [0, 25, 50, 75, 100]) pts.push(-W / 2, FLOOR, Z(p), W / 2, FLOOR, Z(p));
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    return g;
  }, []);
  React.useEffect(() => () => grid.dispose(), [grid]);

  const gridColor = React.useMemo(() => mix(palette.fg, palette.card, palette.isDark ? 0.8 : 0.84), [palette]);
  const edgeColor = React.useMemo(() => mix(palette.fg, palette.card, palette.isDark ? 0.55 : 0.6), [palette]);
  const dash = React.useMemo(() => mix(palette.muted, palette.card, 0.25), [palette]);
  const planeOpacity = palette.isDark ? 0.07 : 0.05;

  const xLine = X(GOOD);
  const yBar = Y(APPROVAL_BAR);
  return (
    <group>
      <lineSegments geometry={grid}>
        <lineBasicMaterial color={gridColor} transparent opacity={0.9} />
      </lineSegments>
      {/* the floor outline + the back-left vertical edge that carries the approval ticks */}
      <Line
        points={[
          [-W / 2, FLOOR, D / 2],
          [W / 2, FLOOR, D / 2],
          [W / 2, FLOOR, -D / 2],
          [-W / 2, FLOOR, -D / 2],
          [-W / 2, FLOOR, D / 2],
        ]}
        color={edgeColor}
        lineWidth={1}
      />
      <Line
        points={[
          [-W / 2, FLOOR, -D / 2],
          [-W / 2, FLOOR + H, -D / 2],
        ]}
        color={edgeColor}
        lineWidth={1}
      />

      {/* rating 4.55 — the vertical plane; everything to its left is below the line */}
      <mesh position={[xLine, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
        <planeGeometry args={[D, H]} />
        <meshBasicMaterial color={palette.bad} transparent opacity={planeOpacity} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <Line
        points={[
          [xLine, FLOOR, D / 2],
          [xLine, FLOOR + H, D / 2],
          [xLine, FLOOR + H, -D / 2],
          [xLine, FLOOR, -D / 2],
          [xLine, FLOOR, D / 2],
        ]}
        color={dash}
        lineWidth={1}
        dashed
        dashSize={0.14}
        gapSize={0.09}
      />

      {/* approval 80% — the horizontal plane; everything under it is below the bar */}
      <mesh position={[0, yBar, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[W, D]} />
        <meshBasicMaterial color={palette.bad} transparent opacity={planeOpacity} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <Line
        points={[
          [-W / 2, yBar, D / 2],
          [W / 2, yBar, D / 2],
          [W / 2, yBar, -D / 2],
          [-W / 2, yBar, -D / 2],
          [-W / 2, yBar, D / 2],
        ]}
        color={dash}
        lineWidth={1}
        dashed
        dashSize={0.14}
        gapSize={0.09}
      />

      {/* ticks at the domain ends + the two thresholds, captions beyond the ends */}
      <Label at={[X(3.8), FLOOR, D / 2 + 0.3]}>3.8</Label>
      <Label at={[xLine, FLOOR, D / 2 + 0.3]} strong>
        {GOOD}
      </Label>
      <Label at={[X(5), FLOOR, D / 2 + 0.3]}>5.0</Label>
      <Label at={[X(4.12), FLOOR - 0.42, D / 2 + 0.3]} caption>
        rating →
      </Label>

      <Label at={[-W / 2 - 0.42, FLOOR, -D / 2]}>60%</Label>
      <Label at={[-W / 2 - 0.42, yBar, -D / 2]} strong>
        {APPROVAL_BAR}%
      </Label>
      <Label at={[-W / 2 - 0.42, FLOOR + H, -D / 2]}>100%</Label>
      <Label at={[-W / 2 - 0.42, FLOOR + H + 0.42, -D / 2]} caption>
        approval ↑
      </Label>

      <Label at={[W / 2 + 0.4, FLOOR, Z(0) - 0.25]}>0%</Label>
      <Label at={[W / 2 + 0.4, FLOOR, Z(100) + 0.25]}>100%</Label>
      <Label at={[W / 2 + 0.55, FLOOR, Z(100) - 0.75]} caption>
        participation ↗
      </Label>
    </group>
  );
}

// ── one instructor ───────────────────────────────────────────────────────────
function SphereNode({
  node,
  geometry,
  material,
  hot,
  reduce,
  onOver,
  onOut,
  onClick,
}: {
  node: Node;
  geometry: THREE.BufferGeometry;
  material: THREE.Material;
  hot: boolean;
  reduce: boolean;
  onOver: (e: ThreeEvent<PointerEvent>) => void;
  onOut: () => void;
  onClick: (e: ThreeEvent<MouseEvent>) => void;
}) {
  const ref = React.useRef<THREE.Mesh>(null);
  const spring = React.useRef({ s: 1, v: 0 });
  const invalidate = useThree((s) => s.invalidate);

  // A frame must be requested when the target changes — demand mode never renders on its own.
  React.useEffect(() => invalidate(), [hot, invalidate]);

  useFrame((_, delta) => {
    const mesh = ref.current;
    if (!mesh) return;
    const target = hot ? 1.4 : 1;
    const st = spring.current;
    if (reduce) {
      st.s = target;
      st.v = 0;
    } else {
      const dt = Math.min(delta, 0.05);
      const accel = (target - st.s) * 180 - st.v * 15; // a light spring: one soft overshoot
      st.v += accel * dt;
      st.s += st.v * dt;
      if (Math.abs(target - st.s) > 0.002 || Math.abs(st.v) > 0.01) invalidate();
      else {
        st.s = target;
        st.v = 0;
      }
    }
    mesh.scale.setScalar(node.r * st.s);
  });

  return (
    <mesh
      ref={ref}
      position={[node.x, node.y, node.z]}
      scale={node.r}
      geometry={geometry}
      material={material}
      onPointerOver={onOver}
      onPointerOut={onOut}
      onClick={onClick}
    />
  );
}

const fmtPct = (v: number | null) => (v == null ? "—" : `${Math.round(v)}%`);

// ── the scene ────────────────────────────────────────────────────────────────
function GalaxyScene({
  points,
  palette,
  reduce,
  inView,
  resetKey,
  onSelect,
}: {
  points: GalaxyPoint[];
  palette: Palette;
  reduce: boolean;
  inView: boolean;
  resetKey: number;
  onSelect: (name: string) => void;
}) {
  const nodes = React.useMemo(() => toNodes(points), [points]);
  const [hovered, setHovered] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<string | null>(null);
  // A drag "engages" the view for the current reset generation; "Reset view" bumps the
  // generation, which un-engages it (auto-rotate resumes) without a second state write.
  const [engagedAt, setEngagedAt] = React.useState(-1);
  const interacted = engagedAt === resetKey;
  const controls = React.useRef<React.ComponentRef<typeof OrbitControls>>(null);
  const invalidate = useThree((s) => s.invalidate);
  useCursor(hovered != null);

  // A narrower frame (mobile) opens the lens a little so the box still fits. Done just before
  // each render (a resize always schedules one), so the projection is never a frame stale.
  useFrame(({ camera, viewport }) => {
    if (!(camera instanceof THREE.PerspectiveCamera)) return;
    const fov = viewport.aspect < 1.3 ? 48 : 36;
    if (camera.fov !== fov) {
      camera.fov = fov;
      camera.updateProjectionMatrix();
    }
  }, -2);

  // Remember the composed view (target included) so "Reset view" returns to exactly this.
  React.useEffect(() => {
    controls.current?.saveState();
  }, []);
  React.useEffect(() => {
    if (resetKey === 0) return;
    controls.current?.reset();
    invalidate();
  }, [resetKey, invalidate]);

  const geometry = React.useMemo(() => new THREE.SphereGeometry(1, 28, 20), []);
  const materials = React.useMemo(
    () => ({
      good: new THREE.MeshStandardMaterial({ roughness: 0.62, metalness: 0 }),
      bad: new THREE.MeshStandardMaterial({ roughness: 0.62, metalness: 0 }),
      hot: new THREE.MeshStandardMaterial({ roughness: 0.4, metalness: 0, emissiveIntensity: 0.5 }),
    }),
    [],
  );
  React.useEffect(
    () => () => {
      geometry.dispose();
      Object.values(materials).forEach((m) => m.dispose());
    },
    [geometry, materials],
  );
  React.useEffect(() => {
    materials.good.color.set(palette.good);
    materials.bad.color.set(palette.bad);
    materials.hot.color.set(palette.primary);
    materials.hot.emissive.set(palette.primary);
    invalidate();
  }, [palette, materials, invalidate]);

  const autoRotate = inView && !reduce && !interacted && hovered == null;
  React.useEffect(() => {
    if (autoRotate) invalidate();
  }, [autoRotate, invalidate]);

  const hoveredNode = hovered ? nodes.find((n) => n.name === hovered) : undefined;
  const skyColor = React.useMemo(() => mix(palette.card, palette.fg, palette.isDark ? 0.1 : 0.02), [palette]);
  const groundColor = React.useMemo(() => mix(palette.card, palette.fg, palette.isDark ? 0.35 : 0.3), [palette]);

  return (
    <>
      <fog attach="fog" args={[palette.card, 8.5, 21]} />
      <hemisphereLight args={[skyColor, groundColor, 1.1]} />
      <directionalLight position={[5, 9, 6]} intensity={2.2} />
      <directionalLight position={[-7, 3, -5]} intensity={0.6} color={palette.violet} />

      <Frame palette={palette} />

      {nodes.map((node) => {
        const hot = node.name === hovered || node.name === selected;
        return (
          <SphereNode
            key={node.name}
            node={node}
            geometry={geometry}
            material={hot ? materials.hot : node.attention ? materials.bad : materials.good}
            hot={hot}
            reduce={reduce}
            onOver={(e) => {
              e.stopPropagation();
              setHovered(node.name);
            }}
            onOut={() => setHovered((h) => (h === node.name ? null : h))}
            onClick={(e) => {
              e.stopPropagation();
              setSelected(node.name);
              onSelect(node.name);
            }}
          />
        );
      })}

      {hoveredNode && (
        // wrapperClass reaches drei's positioned portal element — the one box that can still take
        // the pointer. Its bounds extend down over the sphere, and if it catches the pointer the
        // canvas sees a pointerout and the hover collapses the moment the tooltip appears.
        <Html
          position={[hoveredNode.x, hoveredNode.y + hoveredNode.r * 1.4 + 0.1, hoveredNode.z]}
          zIndexRange={[60, 40]}
          wrapperClass="pointer-events-none"
        >
          <div
            data-galaxy-tooltip
            className="glass shadow-pop -translate-x-1/2 -translate-y-full rounded-lg border px-2.5 py-2 whitespace-nowrap"
          >
            <div className="text-foreground text-xs font-semibold">{hoveredNode.name}</div>
            <div className="text-muted-foreground mt-0.5 text-[11px]" data-numeric>
              {hoveredNode.n} classes · {hoveredNode.avgRating!.toFixed(2)} avg ·{" "}
              {hoveredNode.approval == null ? "no vote" : `${fmtPct(hoveredNode.approval)} back`} ·{" "}
              {fmtPct(hoveredNode.avgParticipation)} rated
            </div>
            <div className="text-primary mt-1 text-[10px] font-medium">Open profile →</div>
          </div>
        </Html>
      )}

      <OrbitControls
        ref={controls}
        makeDefault
        target={TARGET}
        // Damping is what makes a drag feel weighted — but its tail also carries the auto-rotation
        // on for a few frames after a hover pauses it, sliding the sphere out from under the
        // pointer. So the momentum is dropped the moment something is hovered.
        enableDamping={hovered == null}
        dampingFactor={0.08}
        enablePan={false}
        // Wheel only zooms after a drag, so the page keeps scrolling past a scene nobody touched.
        enableZoom={interacted}
        minDistance={7}
        maxDistance={20}
        minPolarAngle={0.3}
        maxPolarAngle={Math.PI / 2 - 0.06}
        autoRotate={autoRotate}
        autoRotateSpeed={0.55}
        onStart={() => setEngagedAt(resetKey)}
      />
    </>
  );
}

export function GalaxyCanvas(props: {
  points: GalaxyPoint[];
  palette: Palette;
  reduce: boolean;
  inView: boolean;
  resetKey: number;
  onSelect: (name: string) => void;
}) {
  return (
    <Canvas
      flat
      frameloop="demand"
      dpr={[1, 2]}
      camera={{ position: CAMERA, fov: 36, near: 0.5, far: 60 }}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
    >
      <GalaxyScene {...props} />
    </Canvas>
  );
}
