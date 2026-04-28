import { AbsoluteFill, Audio, Img, interpolate, Easing, staticFile, Sequence, useVideoConfig } from "remotion";
import { useCurrentFrame } from "remotion";
import { RedUnderline } from "./RedUnderline";
import { Subtitle } from "./Subtitle";
import { DebugGrid } from "./DebugGrid";

interface Annotation {
  /** Coordinates in the ORIGINAL screenshot pixels (before zoom) */
  left: number;
  top: number;
  width: number;
  height?: number;
}

interface ZoomSceneProps {
  imageSrc: string;
  durationInFrames: number;
  /** Starting scale */
  scaleFrom?: number;
  /** Target scale — keep 1.3~1.8 for natural-looking zoom */
  scaleTo?: number;
  /**
   * The point in the ORIGINAL screenshot to zoom into (transformOrigin).
   * e.g. originX=310, originY=95 zooms into the repo name area.
   */
  originX?: number;
  originY?: number;
  /**
   * Frame at which zoom finishes. Annotation draws after this.
   * Default: 40% of durationInFrames.
   */
  zoomEndFrame?: number;
  /** Annotation drawn in original-screenshot coordinate space */
  annotation?: Annotation;
  subtitle?: string;
  subtitleStartFrame?: number;
  /** Sound effect played when zoom starts (frame 0) */
  zoomSfxSrc?: string;
  zoomSfxVolume?: number;
  /** How many frames to play the zoom SFX (default 60 = 2s at 30fps) */
  zoomSfxDurationFrames?: number;
  /** Sound effect played when the underline starts drawing */
  sfxSrc?: string;
  sfxVolume?: number;
  /** How many frames to play the underline SFX (default 45 = 1.5s at 30fps) */
  sfxDurationFrames?: number;
  debug?: boolean;
}

export const ZoomScene: React.FC<ZoomSceneProps> = ({
  imageSrc,
  durationInFrames,
  scaleFrom = 1.0,
  scaleTo = 1.6,
  originX = 960,
  originY = 540,
  zoomEndFrame,
  annotation,
  subtitle,
  subtitleStartFrame = 0,
  zoomSfxSrc,
  zoomSfxVolume = 0.7,
  zoomSfxDurationFrames = 60,
  sfxSrc,
  sfxVolume = 0.8,
  sfxDurationFrames = 45,
  debug = false,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const zoomEnd = zoomEndFrame ?? Math.floor(durationInFrames * 0.4);

  const zoomScale = interpolate(frame, [0, zoomEnd], [scaleFrom, scaleTo], {
    easing: Easing.out(Easing.cubic),
    extrapolateRight: "clamp",
  });

  // Breathing: gentle oscillation after zoom settles (±0.012 amplitude, 60-frame cycle)
  const breathingAmplitude = 0.012;
  const breathingCycle = 60;
  const breathing = frame > zoomEnd
    ? breathingAmplitude * Math.sin(((frame - zoomEnd) / breathingCycle) * 2 * Math.PI)
    : 0;

  const scale = zoomScale + breathing;

  const annotationStartFrame = zoomEnd + 5;

  return (
    <AbsoluteFill style={{ overflow: "hidden", background: "#0d1117" }}>
      <div
        style={{
          position: "absolute",
          width,
          height,
          transform: `scale(${scale})`,
          transformOrigin: `${originX}px ${originY}px`,
        }}
      >
        <Img
          src={staticFile(imageSrc)}
          style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "top" }}
        />

        {annotation && (
          <RedUnderline {...annotation} startFrame={annotationStartFrame} />
        )}

        {debug && <DebugGrid />}
      </div>

      {/* Zoom sound: plays at the start of the scene */}
      {zoomSfxSrc && (
        <Sequence from={0} durationInFrames={zoomSfxDurationFrames}>
          <Audio src={staticFile(zoomSfxSrc)} volume={zoomSfxVolume} endAt={zoomSfxDurationFrames} />
        </Sequence>
      )}

      {/* Underline sound: plays when the red line starts drawing */}
      {sfxSrc && (
        <Sequence from={annotationStartFrame} durationInFrames={sfxDurationFrames}>
          <Audio src={staticFile(sfxSrc)} volume={sfxVolume} endAt={sfxDurationFrames} />
        </Sequence>
      )}

      {subtitle && (
        <Subtitle text={subtitle} startFrame={subtitleStartFrame} />
      )}
    </AbsoluteFill>
  );
};
