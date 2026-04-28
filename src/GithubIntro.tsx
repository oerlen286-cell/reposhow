import React, { useMemo } from "react";
import { AbsoluteFill, Sequence, useVideoConfig, Audio, interpolate, staticFile } from "remotion";
import { useCurrentFrame } from "remotion";
import { ZoomScene } from "./components/ZoomScene";
import { ScrollScene } from "./components/ScrollScene";
import { Subtitle } from "./components/Subtitle";
import {
  TransitionOverlay,
  TransitionStyle,
  useTransitionSceneStyle,
  useSceneStyle,
  needsSceneOverlap,
} from "./components/TransitionOverlay";

const staticAsset = (src: string): string => {
  const [path, query] = src.split("?", 2);
  const resolved = staticFile(path);
  return query ? `${resolved}?${query}` : resolved;
};


/**
 * Video structure (30fps):
 *
 * Scene 1 (0-4s):   zoom into repo name → red underline
 * Scene 2 (4-8s):   zoom into Star button → red underline
 * Scene 3 (8-23s):  scroll through full-page screenshot
 */

export interface SubtitleLine {
  text: string;
  startFrame: number;
  endFrame: number;
}

export interface GithubIntroProps {
  repoDescription: string;
  starCount: string;
  fullPageHeight?: number;
  /** Base path under public/ for screenshots, e.g. "/screenshots/claude-code-tips" */
  screenshotDir?: string;
  /** Scene 1 annotation: position of repo name underline in original screenshot pixels */
  scene1Annotation?: { left: number; top: number; width: number; height?: number };
  /** Scene 1 zoom origin in original screenshot pixels */
  scene1Origin?: { x: number; y: number };
  /** Scene 2 annotation: position of star count underline */
  scene2Annotation?: { left: number; top: number; width: number; height?: number };
  /** Scene 2 zoom origin */
  scene2Origin?: { x: number; y: number };
  scrollSubtitle?: string;
  /** Y pixel in the full-page screenshot where scroll starts (e.g. README top) */
  scrollFromY?: number;
  /** Y pixel where scroll ends; defaults to bottom of page */
  scrollToY?: number;
  /** Frames to hold still at the start of scroll scene before scrolling begins */
  scrollPauseFrames?: number;
  /** Zoom-in scale during the pause (1 = no zoom) */
  scrollPauseScale?: number;
  /** Duration of Scene 3 scroll in seconds */
  scrollDurationSec?: number;
  /** Background music path under public/, e.g. "/bgm/lofi.mp3" */
  bgMusic?: string;
  /** Sound effect played when zoom starts, e.g. "/sfx/1.wav" */
  zoomSfx?: string;
  /** Sound effect for the red underline, e.g. "/sfx/2.wav" */
  annotationSfx?: string;
  /** Show coordinate debug grid on Scene 1 & 2 to calibrate annotation positions */
  debug?: boolean;
  /** Narration audio path under public/, e.g. "/narration/my-repo.mp3" */
  narration?: string;
  /** Timed subtitle lines matching the narration audio */
  subtitleLines?: SubtitleLine[];
  /** Scene transition style: none | black | white | chromatic | blur | zoom */
  transitionStyle?: TransitionStyle;
}

export const GithubIntro: React.FC<GithubIntroProps> = ({
  repoDescription,
  starCount,
  bgMusic,
  zoomSfx,
  annotationSfx,
  narration,
  subtitleLines,
  fullPageHeight = 4000,
  screenshotDir = "/screenshots",
  scene1Annotation = { left: 135, top: 115, width: 180, height: 5 },
  scene1Origin = { x: 10, y: 180 },
  scene2Annotation = { left: 1765, top: 118, width: 120, height: 6 },
  scene2Origin = { x: 1870, y: 57 },
  scrollSubtitle = "项目内容丰富，涵盖多种AI副业赚钱方式",
  scrollFromY = 0,
  scrollToY,
  scrollPauseFrames,
  scrollPauseScale = 1.6,
  scrollDurationSec = 15,
  transitionStyle = "chromatic",
}) => {
  const { fps } = useVideoConfig();

  const scene1Frames = 4 * fps;
  const scene2Frames = 4 * fps;
  const scene3Frames = scrollDurationSec * fps;
  const zoomEnd = Math.floor(scene1Frames * 0.4);  // 48f
  const totalFrames = scene1Frames + scene2Frames + scene3Frames;
  const frame = useCurrentFrame();

  /** At most one narration line visible: overlapping cue windows would otherwise stack. */
  const activeNarrationLine = useMemo(() => {
    if (!subtitleLines?.length) {
      return null;
    }
    const inWindow = subtitleLines.filter(
      (l) => frame >= l.startFrame && frame <= l.endFrame
    );
    if (inWindow.length === 0) {
      return null;
    }
    return inWindow.reduce((a, b) => (a.startFrame >= b.startFrame ? a : b));
  }, [frame, subtitleLines]);

  // BGM volume: fade in over first 30 frames, fade out over last 60 frames
  const bgmVolume = interpolate(
    frame,
    [0, 30, totalFrames - 60, totalFrames],
    [0, 0.25, 0.25, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const boundaries = [scene1Frames, scene1Frames + scene2Frames];
  const sceneWrapperStyle = useTransitionSceneStyle(frame, boundaries, transitionStyle);

  // dissolve/slide need scenes to overlap by HALF frames at each boundary
  const OVERLAP = 5;
  const overlap = needsSceneOverlap(transitionStyle) ? OVERLAP : 0;
  const s1Start = 0;
  const s1Duration = scene1Frames + overlap;
  const s2Start = scene1Frames - overlap;
  const s2Duration = scene2Frames + overlap * 2;
  const s3Start = scene1Frames + scene2Frames - overlap;
  const s3Duration = scene3Frames + overlap;

  // Per-scene styles for dissolve/slide
  const s1Style = useSceneStyle(frame, 0, boundaries, transitionStyle);
  const s2Style = useSceneStyle(frame, 1, boundaries, transitionStyle);
  const s3Style = useSceneStyle(frame, 2, boundaries, transitionStyle);

  return (
    <AbsoluteFill>
      {bgMusic && <Audio src={staticAsset(bgMusic)} volume={bgmVolume} />}
      {narration && <Audio src={staticAsset(narration)} volume={0.9} />}

      {/* Scene wrapper: applies zoom-punch scale when transitionStyle="zoom" */}
      <AbsoluteFill style={sceneWrapperStyle}>

      {/* ── Scene 1: repo name zoom ── */}
      <Sequence from={s1Start} durationInFrames={s1Duration}>
        <AbsoluteFill style={s1Style}>
          <ZoomScene
            imageSrc={`${screenshotDir}/repo-home.png`}
            durationInFrames={s1Duration}
            scaleFrom={1.0}
            scaleTo={1.9}
            originX={scene1Origin.x}
            originY={scene1Origin.y}
            zoomEndFrame={zoomEnd}
            annotation={scene1Annotation}
            subtitle={subtitleLines ? undefined : repoDescription}
            subtitleStartFrame={zoomEnd + 5}
            zoomSfxSrc={zoomSfx}
            sfxSrc={annotationSfx}
          />
        </AbsoluteFill>
      </Sequence>

      {/* ── Scene 2: star count zoom ── */}
      <Sequence from={s2Start} durationInFrames={s2Duration}>
        <AbsoluteFill style={s2Style}>
          <ZoomScene
            imageSrc={`${screenshotDir}/star-count.png`}
            durationInFrames={s2Duration}
            scaleFrom={1.0}
            scaleTo={2.5}
            originX={scene2Origin.x}
            originY={scene2Origin.y}
            zoomEndFrame={zoomEnd}
            annotation={scene2Annotation}
            subtitle={subtitleLines ? undefined : `在GitHub拿下了${starCount}的Star`}
            subtitleStartFrame={zoomEnd + 5}
            zoomSfxSrc={zoomSfx}
            sfxSrc={annotationSfx}
          />
        </AbsoluteFill>
      </Sequence>

      {/* ── Scene 3: full-page scroll ── */}
      <Sequence from={s3Start} durationInFrames={s3Duration}>
        <AbsoluteFill style={s3Style}>
          <ScrollScene
            imageSrc={`${screenshotDir}/full-page.png`}
            durationInFrames={s3Duration}
            imageHeight={fullPageHeight}
            viewportWidth={1920}
            scrollFromY={scrollFromY}
            scrollToY={scrollToY}
            pauseFrames={scrollPauseFrames ?? 0}
            pauseScale={scrollPauseScale}
            subtitle={subtitleLines ? undefined : scrollSubtitle}
            subtitleStartFrame={10}
          />
        </AbsoluteFill>
      </Sequence>

      </AbsoluteFill>{/* end scene wrapper */}

      {/* Transitions first — subtitles must render AFTER so they are not covered */}
      <TransitionOverlay
        frame={frame}
        boundaries={boundaries}
        transitionStyle={transitionStyle}
      />

      {/* Narration subtitles: last in DOM = always on top of scenes + transition FX */}
      {activeNarrationLine && (
        <AbsoluteFill
          style={{
            pointerEvents: "none",
            justifyContent: "flex-end",
            alignItems: "center",
            paddingBottom: 80,
            zIndex: 1000,
          }}
        >
          <Subtitle
            key={`${activeNarrationLine.startFrame}-${activeNarrationLine.endFrame}`}
            text={activeNarrationLine.text}
            startFrame={activeNarrationLine.startFrame}
            endFrame={activeNarrationLine.endFrame}
          />
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
