"use client";

import * as React from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Float, Sparkles } from "@react-three/drei";
import type { Palette } from "./theme-palette";

const CAMERA_Z = 7.5;
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

/** The loop: a torus knot carrying the brand gradient in its vertex colours (indigo low-left →
 *  violet high-right), matte, lit by a soft key and a violet rim from behind. In the light theme
 *  the two endpoints lean a little toward the page colour so the body reads airy, not loud. */
function Knot({ palette, spin }: { palette: Palette; spin: boolean }) {
  const ref = React.useRef<THREE.Mesh>(null);
  const geometry = React.useMemo(() => {
    const g = new THREE.TorusKnotGeometry(1.32, 0.4, 260, 40, 2, 3);
    const pos = g.attributes.position;
    const colors = new Float32Array(pos.count * 3);
    const soften = palette.isDark ? 0 : 0.14;
    const a = new THREE.Color(palette.primary).lerp(new THREE.Color(palette.bg), soften);
    const b = new THREE.Color(palette.violet).lerp(new THREE.Color(palette.bg), soften);
    const c = new THREE.Color();
    for (let i = 0; i < pos.count; i++) {
      const t = clamp01((pos.getY(i) * 0.65 + pos.getX(i) * 0.35) / 3.4 + 0.5);
      c.lerpColors(a, b, t);
      colors[i * 3] = c.r;
      colors[i * 3 + 1] = c.g;
      colors[i * 3 + 2] = c.b;
    }
    g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    return g;
  }, [palette.primary, palette.violet, palette.bg, palette.isDark]);
  React.useEffect(() => () => geometry.dispose(), [geometry]);

  useFrame((_, delta) => {
    if (!spin || !ref.current) return;
    const dt = Math.min(delta, 0.05);
    ref.current.rotation.y += dt * 0.12;
    ref.current.rotation.x += dt * 0.04;
  });

  return (
    <mesh ref={ref} geometry={geometry} rotation={[0.55, -0.35, 0]}>
      <meshStandardMaterial vertexColors roughness={palette.isDark ? 0.42 : 0.56} metalness={palette.isDark ? 0.12 : 0.06} />
    </mesh>
  );
}

/** A hairline ring of small nodes orbiting the knot — the feedback loop itself. */
function OrbitRing({ palette, spin }: { palette: Palette; spin: boolean }) {
  const ref = React.useRef<THREE.Group>(null);
  const N = 14;
  const R = 2.75;
  useFrame((_, delta) => {
    if (!spin || !ref.current) return;
    ref.current.rotation.z += Math.min(delta, 0.05) * 0.09;
  });
  const ringColor = React.useMemo(
    () => new THREE.Color(palette.muted).lerp(new THREE.Color(palette.bg), palette.isDark ? 0.35 : 0.45),
    [palette],
  );
  return (
    <group rotation={[1.2, 0.25, 0.35]}>
      <group ref={ref}>
        <mesh>
          <torusGeometry args={[R, 0.0055, 6, 220]} />
          <meshBasicMaterial color={ringColor} />
        </mesh>
        {Array.from({ length: N }, (_, i) => {
          const angle = (i / N) * Math.PI * 2;
          const major = i % 5 === 0;
          return (
            <mesh key={i} position={[Math.cos(angle) * R, Math.sin(angle) * R, 0]}>
              <sphereGeometry args={[major ? 0.075 : 0.038, 18, 14]} />
              <meshStandardMaterial color={major ? palette.violet : palette.primary} roughness={0.55} metalness={0} />
            </mesh>
          );
        })}
      </group>
    </group>
  );
}

/** Where the loop sits. In the wide layout the copy owns the bottom-left of the column, so the
 *  loop rides up and to the right (bleeding off the edge is intended); in the stacked layout the
 *  strip is short and the loop is simply centred, a touch smaller. */
function Stage({ wide, children }: { wide: boolean; children: React.ReactNode }) {
  const aspect = useThree((s) => s.viewport.aspect);
  // (the strip also keeps clear of the brand mark in its top-left corner)
  const position: [number, number, number] = wide ? [0.95, 0.8, 0] : [0.35, -0.15, 0];
  const scale = wide ? 0.92 : aspect > 1.4 ? 0.78 : 0.86;
  return (
    <group position={position} scale={scale}>
      {children}
    </group>
  );
}

/** The camera drifts a little toward the pointer — enough to feel present, never enough to notice. */
function Parallax({ enabled }: { enabled: boolean }) {
  const goal = React.useRef(new THREE.Vector3(0, 0, CAMERA_Z));
  useFrame(({ camera, pointer }, delta) => {
    if (!enabled) return;
    goal.current.set(pointer.x * 0.5, pointer.y * 0.32, CAMERA_Z);
    camera.position.lerp(goal.current, 1 - Math.exp(-Math.min(delta, 0.05) * 3));
    camera.lookAt(0, 0.3, 0);
  });
  return null;
}

export function LoginScene({ palette, reduce, wide }: { palette: Palette; reduce: boolean; wide: boolean }) {
  const sky = React.useMemo(() => new THREE.Color(palette.bg).lerp(new THREE.Color(palette.fg), 0.06), [palette]);
  const ground = React.useMemo(() => new THREE.Color(palette.bg).lerp(new THREE.Color(palette.fg), 0.3), [palette]);
  return (
    <Canvas
      flat
      // Reduced motion: one still frame (and whenever the theme flips) — nothing moves.
      frameloop={reduce ? "demand" : "always"}
      dpr={[1, 2]}
      camera={{ position: [0, 0, CAMERA_Z], fov: 34, near: 0.1, far: 40 }}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
    >
      {/* fog to the page background so the scene has no edge — it simply melts into the page */}
      <fog attach="fog" args={[palette.bg, 5.5, palette.isDark ? 13 : 11.5]} />
      <hemisphereLight args={[sky, ground, palette.isDark ? 0.9 : 1.3]} />
      <directionalLight position={[4, 5, 6]} intensity={palette.isDark ? 1.6 : 2.5} />
      <directionalLight position={[-4, 3, -5]} intensity={palette.isDark ? 3.2 : 1.7} color={palette.violet} />
      <directionalLight position={[3, -4, -3]} intensity={palette.isDark ? 1.1 : 0.8} color={palette.primary} />

      <Parallax enabled={!reduce} />
      <Stage wide={wide}>
        <Float enabled={!reduce} speed={1.1} rotationIntensity={0.22} floatIntensity={0.45}>
          <Knot palette={palette} spin={!reduce} />
        </Float>
        <OrbitRing palette={palette} spin={!reduce} />
      </Stage>
      {!reduce && (
        <Sparkles count={46} scale={[7.5, 5.5, 4]} size={1.7} speed={0.22} opacity={palette.isDark ? 0.4 : 0.28} color={palette.violet} />
      )}
    </Canvas>
  );
}
