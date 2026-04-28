import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

interface RedUnderlineProps {
  /** Frame at which the underline starts drawing */
  startFrame: number;
  /** Left position in pixels */
  left: number;
  /** Top position in pixels */
  top: number;
  /** Full width of the underline */
  width: number;
  /** Line height, default 5 */
  height?: number;
  /** Color, default red */
  color?: string;
}

export const RedUnderline: React.FC<RedUnderlineProps> = ({
  startFrame,
  left,
  top,
  width,
  height = 5,
  color = "#FF3333",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({
    frame: frame - startFrame,
    fps,
    config: { damping: 200, stiffness: 120, mass: 0.5 },
  });

  const currentWidth = interpolate(progress, [0, 1], [0, width], {
    extrapolateRight: "clamp",
  });

  if (frame < startFrame) return null;

  return (
    <div
      style={{
        position: "absolute",
        left,
        top,
        width: currentWidth,
        height,
        backgroundColor: color,
        borderRadius: 3,
        overflow: "hidden",
        boxShadow: `0 0 8px ${color}88`,
      }}
    />
  );
};
