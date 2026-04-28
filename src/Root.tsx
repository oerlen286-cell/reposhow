import { Composition } from "remotion";
import { GithubIntro, GithubIntroProps } from "./GithubIntro";

const FPS = 30;
// Scene durations shared across all compositions
const SCENE1 = 4 * FPS;
const SCENE2 = 4 * FPS;
const SCENE3 = 25 * FPS;

// Allow the Auto composition to extend its duration based on scrollDurationSec prop
const autoCalculateMetadata = ({ props }: { props: Record<string, unknown> }) => {
  const scrollSecs = (props.scrollDurationSec as number | undefined) ?? 25;
  return { durationInFrames: (8 + scrollSecs) * FPS };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="AiMoneyHunter"
        component={GithubIntro}
        durationInFrames={SCENE1 + SCENE2 + SCENE3}
        fps={FPS}
        width={1920}
        height={1080}
        defaultProps={{
          repoDescription: "这是一个AI副业赚钱的开源项目",
          starCount: "16.4k",
          fullPageHeight: 10395,
          screenshotDir: "/screenshots",
          scene1Origin: { x: 10, y: 180 },
          scene1Annotation: { left: 135, top: 115, width: 180, height: 5 },
          scene2Origin: { x: 1870, y: 57 },
          scene2Annotation: { left: 1765, top: 118, width: 120, height: 6 },
          scrollSubtitle: "项目内容丰富，涵盖多种AI副业赚钱方式",
          scrollPauseFrames: 60,
          scrollPauseScale: 2.8,
          scrollFromY: 0,
        }}
      />
      {/* Generic composition driven entirely by --props (used by auto_video.py) */}
      <Composition
        id="Auto"
        component={GithubIntro}
        durationInFrames={SCENE1 + SCENE2 + SCENE3}
        fps={FPS}
        width={1920}
        height={1080}
        calculateMetadata={autoCalculateMetadata}
        defaultProps={{
          repoDescription: "",
          starCount: "0",
          fullPageHeight: 4000,
          screenshotDir: "/screenshots/auto",
        }}
      />

      <Composition
        id="ClaudeCodeTips"
        component={GithubIntro}
        durationInFrames={SCENE1 + SCENE2 + SCENE3}
        fps={FPS}
        width={1920}
        height={1080}
        defaultProps={{
          repoDescription: "45个Claude Code高级使用技巧",
          starCount: "7.6k",
          fullPageHeight: 38886,
          screenshotDir: "/screenshots/claude-code-tips",
          scene1Origin: { x: 10, y: 180 },
          scene1Annotation: { left: 110, top: 115, width: 200, height: 5 },
          scene2Origin: { x: 1870, y: 57 },
          scene2Annotation: { left: 1765, top: 118, width: 120, height: 6 },
          scrollSubtitle: "45个技巧帮你用好Claude Code",
          scrollPauseFrames: 90,
          scrollPauseScale: 1.6,
          scrollFromY: 800,
        }}
      />
    </>
  );
};
