/**
 * Initial Remotion preview props before /api/generate (neutral placeholder — no repo-specific screenshots).
 */

export const demoPreviewVideoProps = {
    lang: "zh",
    scrollDistance: 2500,
    scrollDurationSec: 25,
    transitionStyle: "chromatic",
    bgMusic: "/bgm/lofi.mp3",
    zoomSfx: "/sfx/1.wav",
    annotationSfx: "/sfx/2.wav",
    repoDescription: 'Paste a GitHub URL and click "Load & Parse Repo" to generate screenshots and narration.',
    starCount: "0.0k",
    fullPageHeight: 4000,
    screenshotDir: "/screenshots",
    scene1Origin: { x: 10, y: 180 },
    scene1Annotation: { left: 135, top: 115, width: 180, height: 5 },
    scene2Origin: { x: 1870, y: 57 },
    scene2Annotation: { left: 1765, top: 118, width: 120, height: 6 },
    scrollSubtitle: "",
    scrollPauseFrames: 60,
    scrollPauseScale: 2.8,
    scrollFromY: 0,
};
