"""
Capture GitHub repo screenshots for Remotion video.

Screenshots saved to: ./public/screenshots/
  - repo-home.png   : viewport screenshot of the repo homepage
  - star-count.png  : zoomed viewport showing star/fork buttons
  - full-page.png   : full-page long screenshot for the scroll scene

Usage:
    pip install playwright
    playwright install chromium
    python capture_screenshots.py --url https://github.com/bleedline/aimoneyhunter
"""

import argparse
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Page


OUTPUT_DIR = Path(__file__).parent / "public" / "screenshots"  # overridden by --output-dir
VIEWPORT_W = 1920
VIEWPORT_H = 1080


def setup_page(page: Page) -> None:
    """Apply common page settings."""
    # Hide cookie banners and modals that block content
    page.add_style_tag(content="""
        .js-cookie-consent, .cookie-banner, [data-testid="cookie-banner"],
        .signup-prompt, .js-notice { display: none !important; }
    """)


def capture_repo_home(page: Page, url: str) -> dict:
    """
    Capture the repo homepage and return metadata for annotation positioning.
    Returns pixel coordinates for the repo name underline.
    """
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(1500)
    setup_page(page)

    output_path = str(OUTPUT_DIR / "repo-home.png")
    page.screenshot(path=output_path, full_page=False)
    print(f"[✓] repo-home.png saved → {output_path}")

    # Locate the repo name element to get its bounding box for annotation
    try:
        repo_name_el = page.locator("strong[itemprop='name'] a, .AppHeader-context-full strong").first
        box = repo_name_el.bounding_box()
        if box:
            print(f"    Repo name bbox: left={box['x']:.0f}, top={box['y'] + box['height']:.0f}, width={box['width']:.0f}")
            print(f"    → Update annotations in GithubIntro.tsx Scene 1 with these values")
    except Exception:
        pass

    return {}


def capture_star_count(page: Page, url: str) -> None:
    """
    Capture the area around the star/fork buttons.
    Scrolls the page so the buttons are visible and takes a screenshot.
    """
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(1500)
    setup_page(page)

    # Keep page at top so Watch/Star/Fork buttons are fully visible
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(500)

    output_path = str(OUTPUT_DIR / "star-count.png")
    page.screenshot(path=output_path, full_page=False)
    print(f"[✓] star-count.png saved → {output_path}")

    # Get star button position for annotation
    try:
        star_btn = page.locator("[aria-label*='star' i], .starring-container").first
        box = star_btn.bounding_box()
        if box:
            print(f"    Star button bbox: left={box['x']:.0f}, top={box['y'] + box['height']:.0f}, width={box['width']:.0f}")
            print(f"    → Update annotations in GithubIntro.tsx Scene 2 with these values")
    except Exception:
        pass


def capture_full_page(page: Page, url: str) -> int:
    """
    Capture the full-page screenshot for the scroll scene.
    Returns the actual height of the captured image.
    """
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(2000)
    setup_page(page)

    # Get actual page height
    page_height = page.evaluate("document.body.scrollHeight")
    print(f"    Page height: {page_height}px")

    output_path = str(OUTPUT_DIR / "full-page.png")
    page.screenshot(path=output_path, full_page=True)
    print(f"[✓] full-page.png saved → {output_path}")
    print(f"    → Set fullPageHeight={page_height} in Root.tsx defaultProps")

    # Detect README section top Y for scrollFromY
    try:
        readme_el = page.locator("#readme, [data-target='readme-toc.content'], article.markdown-body").first
        readme_box = readme_el.bounding_box()
        if readme_box:
            readme_y = int(readme_box["y"])
            print(f"    README top Y: {readme_y}px")
            print(f"    → Set scrollFromY={readme_y} in Root.tsx to start scroll from README")
    except Exception:
        pass

    return page_height


def main():
    parser = argparse.ArgumentParser(description="Capture GitHub screenshots for Remotion video")
    parser.add_argument("--url", default="https://github.com/bleedline/aimoneyhunter",
                        help="GitHub repo URL")
    parser.add_argument("--scene", choices=["all", "home", "star", "scroll"], default="all",
                        help="Which screenshot(s) to capture")
    parser.add_argument("--output-dir", default=None,
                        help="Output directory under public/ (e.g. screenshots/claude-code-tips)")
    args = parser.parse_args()

    global OUTPUT_DIR
    if args.output_dir:
        OUTPUT_DIR = Path(__file__).parent / "public" / args.output_dir
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=2,  # 2x retina → sharper when zoomed
        )
        page = context.new_page()

        print(f"Capturing screenshots for: {args.url}")
        print(f"Output directory: {OUTPUT_DIR}\n")

        if args.scene in ("all", "home"):
            capture_repo_home(page, args.url)

        if args.scene in ("all", "star"):
            capture_star_count(page, args.url)

        if args.scene in ("all", "scroll"):
            height = capture_full_page(page, args.url)
            print(f"\n[Done] Update fullPageHeight={height} in src/Root.tsx")

        browser.close()

    print("\n[All screenshots captured]")
    print("Next steps:")
    print("  1. cd github-video && npm install")
    print("  2. npm run dev  →  open http://localhost:3000 to preview")
    print("  3. Adjust annotation left/top in src/GithubIntro.tsx to align underlines")
    print("  4. npm run render  →  export to out/github-intro.mp4")


if __name__ == "__main__":
    main()
