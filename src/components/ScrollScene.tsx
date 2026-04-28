import { AbsoluteFill, Img, interpolate, Easing, useVideoConfig, staticFile } from "remotion";
import { useCurrentFrame } from "remotion";
import { Subtitle } from "./Subtitle";

interface ScrollSceneProps {
  /** Full-page screenshot path under public/ */
  imageSrc: string;
  /** Total frames for this scene */
  durationInFrames: number;
  /** Full height of the long screenshot in pixels */
  imageHeight: number;
  /** Viewport width */
  viewportWidth?: number;
  /** Pixels to scroll from top, default scrolls to reveal the full page */
  scrollFromY?: number;
  scrollToY?: number;
  /** Frames to hold still at the start before scrolling begins */
  pauseFrames?: number;
  /** Zoom in during pause: scale from 1 → pauseScale over pauseFrames, then hold while scrolling */
  pauseScale?: number;
  subtitle?: string;
  subtitleStartFrame?: number;
  /**
   * "ease"     — smooth ease-in-out (default)
   * "rhythmic" — alternating fast/slow segments for a more dynamic feel
   */
  scrollStyle?: "ease" | "rhythmic";
}

export const ScrollScene: React.FC<ScrollSceneProps> = ({
  imageSrc,
  durationInFrames,
  imageHeight,
  viewportWidth = 1920,
  scrollFromY = 0,
  scrollToY,
  pauseFrames = 0,
  pauseScale = 1,
  subtitle,
  subtitleStartFrame = 0,
  scrollStyle = "rhythmic",
}) => {
  const frame = useCurrentFrame();
  const { width: videoWidth, height: videoHeight } = useVideoConfig();

  const maxScroll = scrollToY ?? imageHeight - videoHeight;
  const scrollStart = Math.min(pauseFrames, durationInFrames - 1);
  const scrollDur = durationInFrames - scrollStart;
  const range = maxScroll - scrollFromY;

  // Rhythmic: slow → fast → slow → fast → slow  (more cinematic)
  // Time %:     0   15%   40%   60%   85%  100%
  // Dist %:     0    3%   45%   55%   97%  100%
  const scrollY = scrollStyle === "rhythmic"
    ? interpolate(
        frame - scrollStart,
        [
          0,
          scrollDur * 0.15,
          scrollDur * 0.40,
          scrollDur * 0.60,
          scrollDur * 0.85,
          scrollDur,
        ],
        [
          scrollFromY,
          scrollFromY + range * 0.03,   // slow start
          scrollFromY + range * 0.45,   // fast burst
          scrollFromY + range * 0.55,   // slow (reading zone)
          scrollFromY + range * 0.97,   // fast burst
          maxScroll,                    // slow end
        ],
        {
          easing: Easing.inOut(Easing.cubic),
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }
      )
    : interpolate(
        frame,
        [scrollStart, durationInFrames],
        [scrollFromY, maxScroll],
        {
          easing: Easing.inOut(Easing.ease),
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }
      );

  // Zoom in during pause (1 → pauseScale), then ease back to 1.0 over first 30% of scroll
  const scrollReleaseEnd = scrollStart + Math.floor(scrollDur * 0.3);
  const zoom = pauseFrames > 0
    ? interpolate(
        frame,
        [0, pauseFrames, scrollReleaseEnd],
        [1, pauseScale, 1],
        {
          easing: Easing.inOut(Easing.cubic),
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }
      )
    : 1;

  // Scale the screenshot to fit video width, then apply zoom centered on screen
  const imageWidth = viewportWidth;
  const displayScale = videoWidth / imageWidth;
  const totalScale = displayScale * zoom;

  return (
    <AbsoluteFill style={{ overflow: "hidden", background: "#0d1117" }}>
      <div
        style={{
          transform: `scale(${totalScale}) translateY(-${scrollY}px)`,
          transformOrigin: "top center",
          width: imageWidth,
        }}
      >
        <Img
          src={staticFile(imageSrc)}
          style={{
            width: imageWidth,
            height: "auto",
            display: "block",
          }}
        />
      </div>

      {/* Subtle scroll indicator on the right */}
      <ScrollIndicator
        progress={scrollY / maxScroll}
        totalHeight={imageHeight}
        viewportHeight={videoHeight}
      />

      {subtitle && (
        <Subtitle text={subtitle} startFrame={subtitleStartFrame} />
      )}
    </AbsoluteFill>
  );
};

// A thin scroll progress bar on the right edge
const ScrollIndicator: React.FC<{
  progress: number;
  totalHeight: number;
  viewportHeight: number;
}> = ({ progress, totalHeight, viewportHeight }) => {
  const trackHeight = 200;
  const thumbHeight = Math.max(20, (viewportHeight / totalHeight) * trackHeight);
  const thumbY = progress * (trackHeight - thumbHeight);

  return (
    <div
      style={{
        position: "absolute",
        right: 16,
        top: "50%",
        transform: "translateY(-50%)",
        width: 6,
        height: trackHeight,
        background: "rgba(255,255,255,0.15)",
        borderRadius: 3,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: thumbY,
          width: 6,
          height: thumbHeight,
          background: "rgba(255,255,255,0.6)",
          borderRadius: 3,
        }}
      />
    </div>
  );
};
