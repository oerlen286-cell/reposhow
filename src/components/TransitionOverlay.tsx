import React from "react";
import { AbsoluteFill, interpolate, Easing } from "remotion";

export type TransitionStyle =
  | "none"
  | "black"
  | "white"
  | "chromatic"
  | "blur"
  | "zoom"
  | "dissolve"
  | "slide";

interface Props {
  frame: number;
  boundaries: number[];
  transitionStyle: TransitionStyle;
}

const HALF = 5; // frames on each side of boundary

/** Find the closest boundary and return signed distance (negative = before, positive = after) */
function closestBoundary(frame: number, boundaries: number[]): number {
  let best = Infinity;
  for (const b of boundaries) {
    const d = frame - b;
    if (Math.abs(d) < Math.abs(best)) best = d;
  }
  return best;
}

/** 0 at edges, 1 at boundary center — bell shape */
function bell(dist: number, half: number): number {
  return interpolate(Math.abs(dist), [0, half], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

// ─── Black flash ──────────────────────────────────────────────────────────────
const BlackFlash: React.FC<{ dist: number }> = ({ dist }) => {
  const opacity = bell(dist, HALF);
  return (
    <AbsoluteFill
      style={{ background: "#000", opacity, pointerEvents: "none" }}
    />
  );
};

// ─── White flash ──────────────────────────────────────────────────────────────
const WhiteFlash: React.FC<{ dist: number }> = ({ dist }) => {
  const opacity = bell(dist, HALF);
  return (
    <AbsoluteFill
      style={{ background: "#fff", opacity, pointerEvents: "none" }}
    />
  );
};

// ─── Chromatic aberration + white peak ────────────────────────────────────────
const ChromaticFlash: React.FC<{ dist: number }> = ({ dist }) => {
  const chromaOpacity = bell(dist, HALF) * 0.55;
  const offset = interpolate(Math.abs(dist), [0, HALF], [28, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const whiteOpacity = interpolate(Math.abs(dist), [0, 2], [0.9, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <>
      <AbsoluteFill style={{
        background: `rgba(255,0,0,${chromaOpacity})`,
        transform: `translateX(${offset}px)`,
        mixBlendMode: "screen",
        pointerEvents: "none",
      }} />
      <AbsoluteFill style={{
        background: `rgba(0,80,255,${chromaOpacity})`,
        transform: `translateX(-${offset}px)`,
        mixBlendMode: "screen",
        pointerEvents: "none",
      }} />
      <AbsoluteFill style={{
        background: `rgba(0,255,120,${chromaOpacity * 0.4})`,
        mixBlendMode: "screen",
        pointerEvents: "none",
      }} />
      {whiteOpacity > 0 && (
        <AbsoluteFill style={{
          background: "#fff",
          opacity: whiteOpacity,
          pointerEvents: "none",
        }} />
      )}
    </>
  );
};

// ─── Blur dissolve (backdrop-filter blurs the scene beneath) ─────────────────
const BlurDissolve: React.FC<{ dist: number }> = ({ dist }) => {
  const strength = bell(dist, HALF);
  const blurPx = strength * 24;
  const dimOpacity = strength * 0.3;

  return (
    <AbsoluteFill style={{
      backdropFilter: `blur(${blurPx}px)`,
      WebkitBackdropFilter: `blur(${blurPx}px)`,
      background: `rgba(0,0,0,${dimOpacity})`,
      pointerEvents: "none",
    }} />
  );
};

// ─── Zoom punch (scale wrapper exported separately — see useTransitionSceneStyle) ──
// The overlay here just adds a subtle white flash to accompany the punch.
const ZoomPunch: React.FC<{ dist: number }> = ({ dist }) => {
  const whiteOpacity = interpolate(Math.abs(dist), [0, 1.5], [0.6, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return whiteOpacity > 0 ? (
    <AbsoluteFill style={{
      background: "#fff",
      opacity: whiteOpacity,
      pointerEvents: "none",
    }} />
  ) : null;
};

// ─── Public hook: scene container style for zoom punch ────────────────────────
/**
 * Returns CSS style to apply to the scene wrapper div.
 * "zoom"    → scale punch before each boundary
 * "dissolve"→ opacity crossfade per scene (use with useSceneStyle)
 * "slide"   → translateX per scene (use with useSceneStyle)
 */
export function useTransitionSceneStyle(
  frame: number,
  boundaries: number[],
  transitionStyle: TransitionStyle,
): React.CSSProperties | undefined {
  if (transitionStyle !== "zoom") return undefined;
  const dist = closestBoundary(frame, boundaries);
  if (Math.abs(dist) > HALF) return undefined;

  const scale = interpolate(dist, [-HALF, 0], [1.0, 1.08], {
    easing: Easing.in(Easing.cubic),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return { transform: `scale(${scale})`, transformOrigin: "center center" };
}

/**
 * Per-scene CSS style for "dissolve" and "slide" transitions.
 * sceneIndex: 0=Scene1, 1=Scene2, 2=Scene3
 * boundaries: [b1, b2] in absolute global frames
 *
 * For other transition styles returns {}.
 */
export function useSceneStyle(
  frame: number,
  sceneIndex: number,
  boundaries: number[],
  transitionStyle: TransitionStyle,
): React.CSSProperties {
  const [b1, b2] = boundaries;

  if (transitionStyle === "dissolve") {
    const fadeIn = (from: number) =>
      interpolate(frame, [from - HALF, from + HALF], [0, 1], {
        extrapolateLeft: "clamp", extrapolateRight: "clamp",
      });
    const fadeOut = (at: number) =>
      interpolate(frame, [at - HALF, at + HALF], [1, 0], {
        extrapolateLeft: "clamp", extrapolateRight: "clamp",
      });

    if (sceneIndex === 0) return { opacity: fadeOut(b1) };
    if (sceneIndex === 1) return { opacity: Math.min(fadeIn(b1), fadeOut(b2)) };
    if (sceneIndex === 2) return { opacity: fadeIn(b2) };
  }

  if (transitionStyle === "slide") {
    // Incoming scene slides in from right (+100%), outgoing stays in place (gets covered)
    const slideIn = (at: number) =>
      interpolate(frame, [at - HALF, at + HALF], [100, 0], {
        easing: Easing.out(Easing.cubic),
        extrapolateLeft: "clamp", extrapolateRight: "clamp",
      });

    if (sceneIndex === 0) {
      // Scene 1 stays; z-index drops when Scene 2 starts sliding in
      return { zIndex: frame < b1 + HALF ? 1 : 0 };
    }
    if (sceneIndex === 1) {
      // Slides in at b1, then stays; at b2 drops z-index
      const tx = frame < b1 + HALF ? slideIn(b1) : 0;
      return {
        transform: `translateX(${tx}%)`,
        zIndex: frame < b2 + HALF ? 2 : 1,
      };
    }
    if (sceneIndex === 2) {
      // Slides in at b2
      return {
        transform: `translateX(${slideIn(b2)}%)`,
        zIndex: 3,
      };
    }
  }

  return {};
}

/** Whether a transition style requires scenes to overlap in time */
export function needsSceneOverlap(style: TransitionStyle): boolean {
  return style === "dissolve" || style === "slide";
}

// ─── Main overlay component ───────────────────────────────────────────────────
export const TransitionOverlay: React.FC<Props> = ({
  frame,
  boundaries,
  transitionStyle,
}) => {
  // dissolve/slide are handled at the scene level, not as an overlay
  if (transitionStyle === "none" || transitionStyle === "dissolve" || transitionStyle === "slide") return null;

  const dist = closestBoundary(frame, boundaries);
  if (Math.abs(dist) > HALF) return null;

  switch (transitionStyle) {
    case "black":     return <BlackFlash dist={dist} />;
    case "white":     return <WhiteFlash dist={dist} />;
    case "chromatic": return <ChromaticFlash dist={dist} />;
    case "blur":      return <BlurDissolve dist={dist} />;
    case "zoom":      return <ZoomPunch dist={dist} />;
    default:          return null;
  }
};
