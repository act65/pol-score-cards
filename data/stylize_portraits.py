"""Stylize the scraped MP portraits into minimal greyscale ink-sketches.

The card design wants low-detail, sketch-like, PURELY GREYSCALE portraits (no
party tint), with the WHOLE FACE visible (never a chin cropped by the stats
panel). This:
  1. face-detects each raw photo and re-frames it as a square with the head
     centred and generous head/chin room (so `object-fit: cover` on the card
     can't clip the face), padding with white where needed;
  2. renders a low-detail greyscale stylization and cleans the background to
     pure white.
Originals are preserved under img/portraits/orig/ so you can re-stylize with a
different look any time without re-scraping.

    cd data && .venv-portraits/bin/python stylize_portraits.py --style posterize
    cd data && .venv-portraits/bin/python stylize_portraits.py --style wireframe
    cd data && .venv-portraits/bin/python stylize_portraits.py --only chris-hipkins

Backgrounds are cut with rembg (U^2-Net) for a clean white cutout on any backdrop;
that needs the isolated pipeline venv (data/.venv-portraits — kept out of the
global env so numpy/opencv stay put) and downloads a ~170MB model on first run.
Masks are cached in img/portraits/masks/ so switching styles never re-runs the
model. Pass --no_mask to skip rembg (classical brightness fallback). Styles:
sketch, woodcut, wireframe, pencil, posterize. Idempotent — always works from the
originals, so re-running (or switching style) is safe.
"""

import argparse
import glob
import os
import shutil

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PDIR = os.path.join(ROOT, "site", "static", "img", "portraits")
ODIR = os.path.join(PDIR, "orig")
MDIR = os.path.join(PDIR, "masks")        # cached rembg foreground alpha, per id
OUT_SIZE = 640

_CASCADE = cv2.CascadeClassifier(
    os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))


# --- framing: put the head high in a square with white padding --------------
def frame_face(bgr):
    """Crop a square around the main (largest) detected face: tight enough to
    exclude neighbours in group shots, with the head sitting HIGH (small headroom
    above the hair, room below for the chin/shoulders) so that — with the card's
    top-aligned portrait — heads aren't pushed down with a white gap on top."""
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    faces = _CASCADE.detectMultiScale(gray, 1.15, 5, minSize=(50, 50))
    if len(faces):
        x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
        side = int(fh * 2.1)                   # tight-ish: crops out adjacent people
        x0 = int(x + fw // 2 - side / 2)
        y0 = int(y - 0.24 * fh)                # only a little hair-room above
    else:                                       # no detection — safe upper-centre square
        side = int(min(h, w) * 1.05)
        x0, y0 = (w - side) // 2, int(h * 0.05)
    x1, y1 = x0 + side, y0 + side
    canvas = np.full((side, side, 3), 255, np.uint8)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    canvas[sy0 - y0:sy0 - y0 + (sy1 - sy0),
           sx0 - x0:sx0 - x0 + (sx1 - sx0)] = bgr[sy0:sy1, sx0:sx1]
    return cv2.resize(canvas, (OUT_SIZE, OUT_SIZE), interpolation=cv2.INTER_AREA)


# --- building blocks --------------------------------------------------------
def _clean_bg(gray, thresh=234):
    """Snap near-white to pure white so scanned/mottled backgrounds go clean."""
    out = gray.copy()
    out[out >= thresh] = 255
    return out


def _whiten_bg(gray, bgr, thr=200):
    """Force regions that were BRIGHT in the source (studio backdrops, blown
    highlights) to pure white — the main 'clean background' lever. Studio
    portraits have light backdrops, so this clears them without segmentation."""
    src = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    src = cv2.GaussianBlur(src, (0, 0), 3)
    out = gray.copy()
    out[src >= thr] = 255
    return out


def _simplify(bgr, s=90, r=0.5):
    """Edge-preserving flatten: kills fine detail (pores, fabric, background)
    while keeping the big shapes — the main 'less detail' lever."""
    return cv2.edgePreservingFilter(bgr, flags=cv2.RECURS_FILTER, sigma_s=s, sigma_r=r)


def _posterize(gray, levels):
    return (gray // (256 // levels) * (255 // (levels - 1))).astype(np.uint8)


def _foreground_mask(bgr):
    """Segment the person from the backdrop with GrabCut, returning a feathered
    0..1 alpha. Because frame_face() centres every head predictably, we seed
    GrabCut with strong geometric priors — face-core = sure foreground, outer
    border = sure background — which separates reliably even when subject and
    backdrop are both dark. Used to force backgrounds to clean white."""
    h, w = bgr.shape[:2]
    mask = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    mask[int(h * 0.10):int(h * 0.96), int(w * 0.18):int(w * 0.82)] = cv2.GC_PR_FGD
    mask[int(h * 0.20):int(h * 0.74), int(w * 0.31):int(w * 0.69)] = cv2.GC_FGD   # face/neck core
    b = int(min(h, w) * 0.045)                                                     # sure background frame
    mask[:b, :] = mask[-b:, :] = cv2.GC_BGD
    mask[:, :b] = mask[:, -b:] = cv2.GC_BGD
    try:
        cv2.grabCut(bgr, mask, None, np.zeros((1, 65), np.float64),
                    np.zeros((1, 65), np.float64), 5, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return np.ones((h, w), np.float32)
    fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    if fg.sum() < 0.05 * 255 * h * w:            # segmentation collapsed → keep all
        return np.ones((h, w), np.float32)
    return cv2.GaussianBlur(fg, (0, 0), 2.5).astype(np.float32) / 255.0


def _on_white(gray, alpha):
    """Composite a greyscale render over white using a 0..1 foreground alpha."""
    g = gray.astype(np.float32)
    return (g * alpha + 255.0 * (1 - alpha)).astype(np.uint8)


def _flood_bg_white(gray, tol=42):
    """Whiten the background by flood-filling inward from the frame edges. With a
    centred head-and-shoulders crop the backdrop is one connected region touching
    the top/side borders, and the subject is an island — so this clears solid
    backdrops (light OR dark) without a segmentation model. Seeds avoid the bottom
    edge so shoulders/torso are preserved."""
    h, w = gray.shape
    filled = gray.copy()
    mask = np.zeros((h + 2, w + 2), np.uint8)
    seeds = [(2, 2), (w - 3, 2), (w // 2, 2),              # top corners + top mid
             (2, h // 3), (w - 3, h // 3),                  # upper sides
             (2, int(h * 0.60)), (w - 3, int(h * 0.60))]    # mid sides
    for sx, sy in seeds:
        cv2.floodFill(filled, mask, (sx, sy), 255,
                      loDiff=tol, upDiff=tol, flags=4 | (255 << 8))
    bg = mask[1:-1, 1:-1].astype(bool)
    out = gray.copy()
    out[bg] = 255
    return out


def _vignette_white(gray, keep=0.60, feather=0.42):
    """Fade the outer edges/corners to pure white (elliptical, centred a touch
    high on the face). With centred head-and-shoulders framing this reliably
    clears the background — dark OR light — without any segmentation."""
    h, w = gray.shape
    yy, xx = np.ogrid[:h, :w]
    dx = (xx - w / 2) / (w * 0.5)
    dy = (yy - h * 0.46) / (h * 0.5)
    d = np.sqrt(dx * dx + dy * dy)
    a = np.clip((d - keep) / feather, 0, 1) ** 1.3        # 0 inside, →1 at edges
    out = gray.astype(np.float32) * (1 - a) + 255.0 * a
    return out.astype(np.uint8)


def _contours(gray, block=11, c=10, blur=7):
    g = cv2.medianBlur(gray, blur)
    return cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                 cv2.THRESH_BINARY, block, c)


def _smooth_flat(flat, k=9):
    """Median-smooth a posterized (flat-tone) image: removes speckle and
    straightens jagged region edges WITHOUT blurring — the tones stay flat."""
    return cv2.medianBlur(flat, k)


def _silhouette_lines(alpha, shape, eps_frac=0.004, thick=2, min_area=400):
    """A single clean outline of the whole subject from the rembg alpha — the
    head-and-shoulders silhouette, polygon-simplified so it's smooth/straight."""
    canvas = np.full(shape, 255, np.uint8)
    if alpha is None:
        return canvas
    m = (alpha > 0.5).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts:
        if cv2.contourArea(c) < min_area:
            continue
        length = cv2.arcLength(c, True)
        cv2.polylines(canvas, [cv2.approxPolyDP(c, eps_frac * length, True)],
                      True, 0, thick, cv2.LINE_AA)
    return canvas


def _region_lines(flat, shape, eps_frac=0.008, min_len=44, thick=2, min_area=140):
    """Clean, straightened outlines between flat tone regions. Each region mask is
    morphologically de-speckled, then its boundary is polygon-approximated
    (approxPolyDP) so wobbles/detail collapse to a few straight segments — the
    'smooth/straighten lines, not blur' request. Tiny regions are dropped."""
    canvas = np.full(shape, 255, np.uint8)
    k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    k9 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    for v in np.unique(flat):
        m = (flat == v).astype(np.uint8) * 255
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k5)      # drop specks
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k9)     # fill pinholes → smooth edge
        cnts, _ = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            if cv2.contourArea(c) < min_area:
                continue
            length = cv2.arcLength(c, True)
            if length < min_len:
                continue
            approx = cv2.approxPolyDP(c, eps_frac * length, True)
            cv2.polylines(canvas, [approx], True, 0, thick, cv2.LINE_AA)
    return canvas


# --- background cut via ML segmentation (rembg / U^2-Net) -------------------
_REMBG_SESSION = None


def _rembg_alpha(framed_bgr):
    """A clean 0..1 foreground alpha from rembg (U^2-Net). Reliably separates the
    person from ANY backdrop — the thing classical flood/vignette can't do. Needs
    the portrait venv (data/.venv-portraits). Returns None if rembg is absent."""
    global _REMBG_SESSION
    try:
        from rembg import new_session, remove
    except Exception:
        return None
    if _REMBG_SESSION is None:
        # isnet-general-use segments people in busy/group photos far better than
        # the default u2net (which returns a rectangle when it can't separate).
        _REMBG_SESSION = new_session("isnet-general-use")
    rgb = cv2.cvtColor(framed_bgr, cv2.COLOR_BGR2RGB)
    m = np.asarray(remove(rgb, session=_REMBG_SESSION,
                          only_mask=True, post_process_mask=True))
    if m.ndim == 3:
        m = m[..., 0]
    return cv2.GaussianBlur(m, (0, 0), 1.2).astype(np.float32) / 255.0


def foreground_alpha(framed_bgr, cache_path=None, refresh=False):
    """rembg alpha for a framed portrait, cached to masks/<id>.png so switching
    styles never re-runs the model. None when rembg is unavailable."""
    if cache_path and not refresh and os.path.exists(cache_path):
        m = cv2.imread(cache_path, cv2.IMREAD_GRAYSCALE)
        if m is not None:
            return m.astype(np.float32) / 255.0
    a = _rembg_alpha(framed_bgr)
    if a is not None and cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        cv2.imwrite(cache_path, (a * 255).astype(np.uint8))
    return a


def _finish(gray, bgr, alpha):
    """Put a greyscale render on a clean white background. With an ML alpha the
    cutout is exact; without it, fall back to the classical brightness whiten."""
    if alpha is not None:
        return _on_white(gray, alpha)
    return _whiten_bg(_clean_bg(gray), bgr)


# --- ML line drawing (Informative Drawings via controlnet_aux) --------------
_LINEART_DETECTOR = None


def _lineart(framed_bgr, coarse=False):
    """Photo → line drawing with the pretrained Informative Drawings model
    (controlnet_aux LineartDetector). Unlike the tonal filters, it's trained to
    put lines where identity lives, so likeness holds. Returns black-on-white
    grey. Needs the portrait venv (torch + controlnet_aux)."""
    global _LINEART_DETECTOR
    from PIL import Image
    from controlnet_aux import LineartDetector
    if _LINEART_DETECTOR is None:
        _LINEART_DETECTOR = LineartDetector.from_pretrained("lllyasviel/Annotators")
    pil = Image.fromarray(cv2.cvtColor(framed_bgr, cv2.COLOR_BGR2RGB))
    out = _LINEART_DETECTOR(pil, coarse=coarse,
                            detect_resolution=512, image_resolution=OUT_SIZE)
    g = np.array(out.convert("L"))
    if g.mean() < 127:                     # model returns white-on-black → invert
        g = 255 - g
    return g


# --- styles (framed BGR + optional foreground alpha) ------------------------
def style_sketch(bgr, alpha=None):
    """Faint graphite wash + clean contour lines — low-detail hand sketch."""
    gray = cv2.cvtColor(_simplify(bgr, 100, 0.5), cv2.COLOR_BGR2GRAY)
    tone = np.clip(gray.astype(np.float32) * 0.5 + 122, 0, 255).astype(np.uint8)
    lines = _contours(gray, block=11, c=11, blur=7)
    return _finish(cv2.min(tone, lines), bgr, alpha)


def style_woodcut(bgr, alpha=None):
    """Posterized flat regions + bold outlines — lino/woodcut."""
    ms = cv2.pyrMeanShiftFiltering(bgr, 25, 45)
    flat = _posterize(cv2.cvtColor(ms, cv2.COLOR_BGR2GRAY), levels=4)
    lines = _contours(cv2.cvtColor(_simplify(bgr, 90, 0.5), cv2.COLOR_BGR2GRAY),
                      block=13, c=9, blur=7)
    return _finish(cv2.min(flat, lines), bgr, alpha)


def style_wireframe(bgr, alpha=None):
    """Pure thin line-art on white — the most minimal look."""
    gray = cv2.cvtColor(_simplify(bgr, 120, 0.55), cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.medianBlur(gray, 5), 40, 110)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8))
    return _finish(255 - edges, bgr, alpha)               # black lines on white


def style_pencil(bgr, alpha=None):
    """OpenCV's non-photorealistic pencil shading (soft graphite)."""
    gray_sk, _ = cv2.pencilSketch(_simplify(bgr, 60, 0.45),
                                  sigma_s=60, sigma_r=0.07, shade_factor=0.05)
    return _finish(gray_sk, bgr, alpha)


def style_posterize(bgr, alpha=None):
    """Three flat grey tones on clean white — minimal screen-print."""
    gray = cv2.cvtColor(_simplify(bgr, 110, 0.55), cv2.COLOR_BGR2GRAY)
    post = _posterize(gray, 3)
    if alpha is None:                                     # classical fallback
        return _vignette_white(_flood_bg_white(post, 42), keep=0.70, feather=0.33)
    return _on_white(post, alpha)


def style_posterline(bgr, alpha=None):
    """Posterize + wireframe: flat 3-tone fills with clean straightened outlines
    between the tones. The tone regions are median-smoothed and the lines are
    polygon-simplified, so it reads as a crisp minimal print."""
    gray = cv2.cvtColor(_simplify(bgr, 120, 0.6), cv2.COLOR_BGR2GRAY)
    flat = _smooth_flat(_posterize(gray, 3), k=9)
    lines = _region_lines(flat, gray.shape, eps_frac=0.006, min_len=48, thick=2)
    return _finish(cv2.min(flat, lines), bgr, alpha)


def style_vector(bgr, alpha=None):
    """Minimal vector portrait: the dark features (eyes, brows, hair, jaw shadow)
    as smoothed flat shapes + a single clean silhouette outline. Captures likeness
    from the two darkest tones while staying low-detail — far less busy than
    drawing every tonal boundary."""
    gray = cv2.cvtColor(_simplify(bgr, 120, 0.6), cv2.COLOR_BGR2GRAY)
    post = _smooth_flat(_posterize(gray, 4), k=9)
    vals = sorted(np.unique(post))
    out = np.full_like(post, 255)
    if len(vals) >= 1:
        out[post == vals[0]] = 60                        # darkest → feature shapes
    if len(vals) >= 3:
        out[post == vals[1]] = 150                       # 2nd darkest → soft form
    out = cv2.min(out, _silhouette_lines(alpha, out.shape, thick=2))
    return _finish(out, bgr, alpha)


def style_notan(bgr, alpha=None):
    """Flat 2-value light/dark shapes with smoothed edges, no outlines — a notan
    study. The most minimal 'silhouette-y' look."""
    gray = cv2.cvtColor(_simplify(bgr, 120, 0.6), cv2.COLOR_BGR2GRAY)
    _t, duo = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return _finish(_smooth_flat(duo, k=11), bgr, alpha)


def style_ink(bgr, alpha=None):
    """Bold two-tone ink: dark subject shapes with straightened silhouette edges
    — like a lino print. Threshold, smooth, then clean the boundary."""
    gray = cv2.cvtColor(_simplify(bgr, 140, 0.6), cv2.COLOR_BGR2GRAY)
    flat = _smooth_flat(_posterize(gray, 2), k=11)          # 2 tones (black/white)
    lines = _region_lines(flat, gray.shape, eps_frac=0.010, min_len=60, thick=3)
    return _finish(cv2.min(flat, lines), bgr, alpha)


def style_lineart(bgr, alpha=None):
    """ML pencil-style line drawing (Informative Drawings) — detailed, strong
    likeness. The best likeness/quality of all the styles; needs the venv."""
    return _finish(_lineart(bgr, coarse=False), bgr, alpha)


def style_lineart_coarse(bgr, alpha=None):
    """ML line drawing with fewer, bolder lines — more minimal than `lineart`."""
    return _finish(_lineart(bgr, coarse=True), bgr, alpha)


STYLES = {
    "sketch": style_sketch,
    "woodcut": style_woodcut,
    "wireframe": style_wireframe,
    "pencil": style_pencil,
    "posterize": style_posterize,
    "posterline": style_posterline,
    "vector": style_vector,
    "notan": style_notan,
    "ink": style_ink,
    "lineart": style_lineart,
    "lineart_coarse": style_lineart_coarse,
}


def _ensure_originals():
    """Snapshot any top-level portrait JPG into orig/ once, so we always stylize
    from the untouched source (top-level files may already be stylized)."""
    os.makedirs(ODIR, exist_ok=True)
    for path in glob.glob(os.path.join(PDIR, "*.jpg")):
        pid = os.path.splitext(os.path.basename(path))[0]
        orig = os.path.join(ODIR, pid + ".jpg")
        if not os.path.exists(orig):
            shutil.copyfile(path, orig)


def stylize_one(orig_path, fn, use_mask=True):
    bgr = cv2.imread(orig_path)
    if bgr is None:
        return None
    framed = frame_face(bgr)
    pid = os.path.splitext(os.path.basename(orig_path))[0]
    alpha = foreground_alpha(framed, os.path.join(MDIR, pid + ".png")) if use_mask else None
    return fn(framed, alpha)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", default="sketch", choices=sorted(STYLES))
    ap.add_argument("--only", default="", help="comma-separated ids to (re)process")
    ap.add_argument("--no_mask", action="store_true",
                    help="skip rembg background removal (classical fallback)")
    args = ap.parse_args()

    _ensure_originals()
    fn = STYLES[args.style]
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    use_mask = not args.no_mask

    done = 0
    for path in sorted(glob.glob(os.path.join(ODIR, "*.jpg"))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if only and pid not in only:
            continue
        out = stylize_one(path, fn, use_mask=use_mask)
        if out is None:
            print(f"  ! unreadable: {pid}")
            continue
        cv2.imwrite(os.path.join(PDIR, pid + ".jpg"), out,
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        done += 1
    print(f"stylized {done} portrait(s) with style '{args.style}'"
          f"{'' if use_mask else ' (no mask)'} "
          f"(originals in {os.path.relpath(ODIR, ROOT)})")


if __name__ == "__main__":
    main()
