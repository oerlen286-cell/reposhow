import { useVideoConfig } from "remotion";

/**
 * Debug overlay: renders a coordinate grid every 100px.
 * Pass debug={true} to ZoomScene/ScrollScene to enable.
 * Read the coordinates from the grid to calibrate annotation positions.
 */
export const DebugGrid: React.FC = () => {
  const { width, height } = useVideoConfig();

  const verticals = Array.from({ length: Math.floor(width / 100) }, (_, i) => (i + 1) * 100);
  const horizontals = Array.from({ length: Math.floor(height / 100) }, (_, i) => (i + 1) * 100);

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      {/* Vertical lines */}
      {verticals.map((x) => (
        <div key={`v${x}`}>
          <div
            style={{
              position: "absolute",
              left: x,
              top: 0,
              width: 1,
              height: "100%",
              background: x % 500 === 0 ? "rgba(255,255,0,0.5)" : "rgba(255,255,255,0.15)",
            }}
          />
          <span
            style={{
              position: "absolute",
              left: x + 3,
              top: 4,
              color: x % 500 === 0 ? "#FFE000" : "rgba(255,255,255,0.6)",
              fontSize: 18,
              fontFamily: "monospace",
              fontWeight: x % 500 === 0 ? "bold" : "normal",
            }}
          >
            {x}
          </span>
        </div>
      ))}

      {/* Horizontal lines */}
      {horizontals.map((y) => (
        <div key={`h${y}`}>
          <div
            style={{
              position: "absolute",
              left: 0,
              top: y,
              width: "100%",
              height: 1,
              background: y % 500 === 0 ? "rgba(255,255,0,0.5)" : "rgba(255,255,255,0.15)",
            }}
          />
          <span
            style={{
              position: "absolute",
              left: 4,
              top: y + 3,
              color: y % 500 === 0 ? "#FFE000" : "rgba(255,255,0.6)",
              fontSize: 18,
              fontFamily: "monospace",
              fontWeight: y % 500 === 0 ? "bold" : "normal",
            }}
          >
            {y}
          </span>
        </div>
      ))}

      {/* Corner label */}
      <div
        style={{
          position: "absolute",
          top: 8,
          right: 16,
          background: "rgba(0,0,0,0.7)",
          color: "#FFE000",
          fontSize: 22,
          fontFamily: "monospace",
          padding: "4px 12px",
          borderRadius: 6,
        }}
      >
        DEBUG GRID (每格 100px)
      </div>
    </div>
  );
};
