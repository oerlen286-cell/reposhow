import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

interface SubtitleProps {
  text: string;
  startFrame?: number;
  endFrame?: number;
}

export const Subtitle: React.FC<SubtitleProps> = ({
  text,
  startFrame = 0,
  endFrame,
}) => {
  const frame = useCurrentFrame();
  const elapsed = frame - startFrame;

  if (frame < startFrame) return null;
  // Unmount after line ends (+1 frame past fade) so flex stack does not pile up
  if (endFrame !== undefined && frame > endFrame) return null;

  const duration = endFrame !== undefined ? endFrame - startFrame : 9999;
  const slideFrames = Math.min(10, Math.max(1, Math.floor(duration * 0.15)));
  const slideY = interpolate(elapsed, [0, slideFrames], [16, 0], {
    easing: Easing.out(Easing.cubic),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const fadeIn = interpolate(elapsed, [0, 5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const fadeOut =
    endFrame !== undefined
      ? interpolate(frame, [endFrame - 5, endFrame], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 1;

  const opacity = Math.min(fadeIn, fadeOut);

  return (
    <div
      style={{
        position: "absolute",
        bottom: 80,
        left: "50%",
        transform: `translate(-50%, ${slideY}px)`,
        opacity,
        maxWidth: "85%",
        textAlign: "center",
      }}
    >
      <div
        style={{
          background: "rgba(0,0,0,0.78)",
          padding: "14px 36px",
          borderRadius: 10,
        }}
      >
        <span
          style={{
            color: "#FFFFFF",
            fontSize: 48,
            fontWeight: 700,
            fontFamily:
              "'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei', 'Hiragino Sans GB', sans-serif",
            textShadow: "2px 3px 8px rgba(0,0,0,0.95)",
            letterSpacing: 1,
            lineHeight: 1.35,
            wordBreak: "break-word",
          }}
        >
          {text}
        </span>
      </div>
    </div>
  );
};
