"""Generate the social-share image and the favicon.

A link to this site shared on Bluesky, Mastodon, Slack or in a Spinoff editor's
inbox currently renders as a bare URL. These two files are what turn it into a
card with a picture, which is most of the difference in whether anyone clicks.

Run after changing the site's name or palette:

    python make_og.py        # -> static/img/og.png, static/favicon.svg

Deliberately a generator rather than a checked-in binary someone has to open
Figma to change: the title lives in one string, and the palette is the site's.
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

# The site palette (style.css): paper, ink, slate, and the single gold accent
# the attribute glyphs use.
PAPER, INK, SLATE, GOLD = "#f8f9fa", "#0f172a", "#475569", "#7a611f"

TITLE = "NZ Politician Scorecards"
SUBTITLE = "Every MP in the 54th Parliament, scored on how they argue"
FOOTER = "Six attributes · 82,569 statements from Hansard · every score links to its quote"

# 1200x630 is the size every platform crops toward; anything else gets letterboxed
# or centre-cropped, and a centre-crop eats the subtitle.
W, H = 1200, 630

_DEJAVU = "/usr/share/fonts/truetype/dejavu"


def _font(name, size):
    for path in (os.path.join(_DEJAVU, name),
                 f"/usr/share/fonts/truetype/liberation/{name}"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _house_means():
    """(attribute, House mean) in card order. Imported from the app so the share
    card cannot quote a number the site does not show; returns [] if the dataset
    is not built yet, and the image is then just the title."""
    try:
        import app as site_app
        shown, _total = site_app._featured()
        means = site_app._house_means(shown)
        return [(a["name"], means[a["name"]])
                for a in site_app.attribute_descriptions if a["name"] in means]
    except Exception:
        return []


def og_image():
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    pad = 72
    # A card-edge motif down the left, echoing the 5:7 border on every scorecard.
    d.rounded_rectangle([pad - 28, pad - 28, W - pad + 28, H - pad + 28],
                        radius=18, outline="#d5cfc2", width=4)

    y = pad + 18
    title_f = _font("DejaVuSans-Bold.ttf", 68)
    for line in _wrap(d, TITLE, title_f, W - 2 * pad):
        d.text((pad, y), line, font=title_f, fill=INK)
        y += 80

    y += 6
    d.rectangle([pad, y, pad + 96, y + 5], fill=GOLD)
    y += 42

    sub_f = _font("DejaVuSans.ttf", 34)
    for line in _wrap(d, SUBTITLE, sub_f, W - 2 * pad):
        d.text((pad, y), line, font=sub_f, fill=SLATE)
        y += 46

    # The House average on each attribute. Filling the space with the actual
    # result rather than decoration: someone who only ever sees the share card
    # still learns the finding, and Rigor at 45 is the finding.
    bars = _house_means()
    if bars:
        by = y + 18
        name_f, num_f = _font("DejaVuSans.ttf", 25), _font("DejaVuSans-Bold.ttf", 25)
        col_w, bar_w = (W - 2 * pad) // 2, 150
        for i, (name, val) in enumerate(bars):
            cx = pad + (i % 2) * col_w
            cy = by + (i // 2) * 48
            d.text((cx, cy), name, font=name_f, fill=SLATE)
            bx = cx + 176
            d.rounded_rectangle([bx, cy + 9, bx + bar_w, cy + 19], radius=5,
                                fill="#e2e6ea")
            d.rounded_rectangle([bx, cy + 9, bx + int(bar_w * val / 100), cy + 19],
                                radius=5, fill=GOLD if val < 50 else SLATE)
            d.text((bx + bar_w + 14, cy), str(round(val)), font=num_f, fill=INK)

    foot_f = _font("DejaVuSans.ttf", 23)
    fy = H - pad - 10
    for line in reversed(_wrap(d, FOOTER, foot_f, W - 2 * pad)):
        fy -= 32
        d.text((pad, fy), line, font=foot_f, fill="#64748b")

    out = os.path.join(STATIC, "img", "og.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out


def favicon():
    """A scorecard in outline: the 5:7 frame with a rule under the portrait
    area. At 16px the detail is gone and it reads as a card, which is the point.
    SVG so it stays crisp on every tab bar and in the bookmark list."""
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="{INK}"/>
  <rect x="9.5" y="6" width="13" height="20" rx="2.5"
        fill="none" stroke="{PAPER}" stroke-width="2"/>
  <path d="M9.5 19.5h13" stroke="{PAPER}" stroke-width="2"/>
  <path d="M12.5 22.5h7" stroke="{GOLD}" stroke-width="2" stroke-linecap="round"/>
</svg>
'''
    out = os.path.join(STATIC, "favicon.svg")
    with open(out, "w") as f:
        f.write(svg)
    return out


if __name__ == "__main__":
    for p in (og_image(), favicon()):
        print(f"wrote {p} ({os.path.getsize(p) / 1024:.0f} KB)")
