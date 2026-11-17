#!/usr/bin/env python3
"""
One-off: split the clay-eye render into the editable layers used by
make_eye_header.py.  Output goes to <outdir>/ as PNGs + eye.json.

Layers (all 240x240 screen space unless noted):
  skin.png        color - everything the eyelids draw (face, brow, fold,
                  and the closed-lid skin over the eye opening)
  sclera.png      color, SCLERA_W x SCLERA_H - eyeball white, with the
                  black pupil disc + highlight painted at its center
  iris.png        color, square - the iris as a disc (pupil black)
  lid_upper.png   gray - upper lid threshold map
  lid_lower.png   gray - lower lid threshold map
  shade.png       gray - screen-fixed eyeball shading (255 = full bright)
  eye.json        geometry / tuning numbers
"""
import json, sys, os
import numpy as np
from PIL import Image
from scipy import ndimage

SRC = sys.argv[1]
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

S = 240
img = Image.open(SRC).convert('RGB')
A = np.array(img).astype(float)

# --- source geometry (pixels in the original render) -----------------------
FACE_CX, FACE_CY, SIDE = 389, 569, 846     # crop square fitted to the face
IRIS_CX, IRIS_CY, IRIS_R = 396.0, 615.0, 111.0
PUPIL_R = 51.0
HL_CX, HL_CY, HL_R = 375.0, 586.0, 14.0    # specular highlight
k = S / SIDE                               # source -> screen scale
x0, y0 = FACE_CX - SIDE / 2, FACE_CY - SIDE / 2

def to_screen(x, y):
    return (x - x0) * k, (y - y0) * k

crop = img.crop((int(x0), int(y0), int(x0) + SIDE, int(y0) + SIDE)).resize((S, S), Image.LANCZOS)
base = np.array(crop).astype(float)
yy, xx = np.mgrid[0:S, 0:S]
icx, icy = to_screen(IRIS_CX, IRIS_CY)
ir = IRIS_R * k
R = int(round(ir))                          # iris radius in screen px (32)

# --- eye opening mask -------------------------------------------------------
r, g, b = base[..., 0], base[..., 1], base[..., 2]
bright = base.sum(2)
ell = ((xx - 121) / 63.0) ** 2 + ((yy - 136) / 54.0) ** 2 < 1
scl = ell & ((r - b) < 42) & (bright > 300)
iris_disc = (xx - icx) ** 2 + (yy - icy) ** 2 < (ir * 1.02) ** 2
opening = scl | iris_disc
opening = ndimage.binary_closing(opening, iterations=2)
opening = ndimage.binary_fill_holes(opening)
lab, n = ndimage.label(opening)
opening = lab == (np.argmax(ndimage.sum(opening, lab, range(1, n + 1))) + 1)
opening = ndimage.binary_opening(opening, iterations=2)
opening = ndimage.binary_fill_holes(opening) & ell
# smooth the outline
opening = ndimage.gaussian_filter(opening.astype(float), 1.5) > 0.5
opening = ndimage.binary_dilation(opening, iterations=1)

# --- screen-fixed shading taken from the render's eyeball -------------------
sclera_px = opening & ~ndimage.binary_dilation(iris_disc, iterations=2)
sclera_px &= ndimage.binary_erosion(opening, iterations=2)
lum = base.mean(2)
white = np.percentile(lum[sclera_px], 97)
sclera_rgb = np.median(base[sclera_px & (lum > np.percentile(lum[sclera_px], 85))], axis=0)
shade = np.where(sclera_px, lum / white, 0.0)
# smooth cubic surface fitted to the eyeball's brightness (no iris/highlight)
ux, uy = (xx - 120) / 120.0, (yy - 120) / 120.0
terms = [np.ones_like(ux), ux, uy, ux*ux, ux*uy, uy*uy, ux**3, ux*ux*uy, ux*uy*uy, uy**3]
M = np.stack([t[sclera_px] for t in terms], 1)
coef, *_ = np.linalg.lstsq(M, (lum / white)[sclera_px], rcond=None)
fit = sum(c * t for c, t in zip(coef, terms))
shade = np.clip(fit, 0.45, 1.0)

# --- skin / lid texture -----------------------------------------------------
cand = (np.abs(base - base[2, 2]).sum(2) < 60) | ((base.max(2) - base.min(2) < 18) & (base.mean(2) < 110))
lab, n = ndimage.label(cand)
edge_labels = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
bg = np.isin(lab, list(edge_labels))
bgw = ndimage.gaussian_filter(bg.astype(float), 1.5)[..., None]
rim = np.array([46, 34, 28.0])
face = ~bg
skin = base * (1 - bgw) + rim * bgw

# closed lid: a skin-colored dome over the opening, shaded like the eyeball
dil = ndimage.binary_dilation(opening, iterations=2)
ring = ndimage.binary_dilation(opening, iterations=9) & ~dil & face
lid_rgb = np.median(base[ring & (base.mean(2) > np.percentile(base[ring].mean(1), 85))], axis=0)
rng = np.random.default_rng(7)
grain = ndimage.gaussian_filter(rng.normal(0, 5.0, (S, S)), 0.7)
dome = (0.82 + 0.22 * (shade - 0.45) / 0.55)
lid = lid_rgb[None, None, :] * dome[..., None] + grain[..., None]
# crease where the upper and lower lids meet (70% down the opening)
cols = np.where(opening.any(0))[0]
top = np.full(S, -1); bot = np.full(S, -1)
for x in cols:
    ys = np.where(opening[:, x])[0]
    top[x], bot[x] = ys.min(), ys.max()
tops = ndimage.uniform_filter1d(top[cols].astype(float), 9); bots = ndimage.uniform_filter1d(bot[cols].astype(float), 9)
crease = np.zeros((S, S))
for j, x in enumerate(cols):
    yc = tops[j] + 0.70 * (bots[j] - tops[j])
    crease[:, x] = np.exp(-((yy[:, x] - yc) / 1.6) ** 2)
lid *= (1 - 0.22 * crease)[..., None]
# soft blend at the opening rim so lid meets face without a seam
w = ndimage.gaussian_filter(dil.astype(float), 0.8)
w = np.where(dil, 1.0, w)
skin = skin * (1 - w[..., None]) + lid * w[..., None]
skin_img = Image.fromarray(np.clip(skin, 0, 255).astype(np.uint8))

# --- lid threshold maps -----------------------------------------------------
# engine: pixel is lid if lower <= lT or upper <= uT
#   outside the opening: lower = 0 (always lid)
#   upper lid closes the top 70%, lower lid the bottom 30%
#   resting thresholds: uT = LID_REST (120), lT = 254 - uT (134)
LID_REST, SPLIT = 120, 0.70
upper = np.zeros((S, S)); lower = np.zeros((S, S))
for x in cols:
    t, bm = top[x], bot[x]
    h = max(bm - t, 1)
    for y in range(t, bm + 1):
        if not opening[y, x]:
            continue
        gfrac = (y - t) / h
        upper[y, x] = LID_REST + 1 + (254 - LID_REST - 1) * gfrac / SPLIT if gfrac <= SPLIT else 255
        ffrac = (bm - y) / h
        lo_rest = 254 - LID_REST + 1
        lower[y, x] = lo_rest + (254 - lo_rest) * ffrac / (1 - SPLIT) if ffrac <= (1 - SPLIT) else 255
upper = np.clip(np.round(upper), 0, 255).astype(np.uint8)
lower = np.clip(np.round(lower), 0, 255).astype(np.uint8)

# --- sclera (eyeball texture that slides) ----------------------------------
REST_X, REST_Y = int(round(icx)), int(round(icy))       # 122, 133
TRAVEL_X, TRAVEL_Y = 28, 20
SW, SH = 300, 306                                        # see eye.json notes
scx, scy = SW // 2, SH // 2
sclera = np.ones((SH, SW, 3)) * sclera_rgb
sgrain = ndimage.gaussian_filter(rng.normal(0, 3.0, (SH, SW)), 0.8)
sclera += sgrain[..., None]
syy, sxx = np.mgrid[0:SH, 0:SW]
# pupil: black disc over the whole iris area (iris ring is drawn on top)
pd = np.hypot(sxx - scx + 0.5, syy - scy + 0.5)
pupil_rgb = np.array([6, 6, 8.0])
sclera = np.where((pd < R + 1)[..., None], pupil_rgb, sclera)
# highlight, pulled slightly toward center so the smallest pupil never hides it
hx, hy = (HL_CX - IRIS_CX) * k * 0.8, (HL_CY - IRIS_CY) * k * 0.8
hr = HL_R * k
hd = np.hypot(sxx - (scx + hx), syy - (scy + hy))
ha = np.clip((hr - hd) / 1.3, 0, 1) ** 1.2
sclera = sclera * (1 - ha[..., None]) + np.array([250, 250, 250.0]) * ha[..., None]
sclera_img = Image.fromarray(np.clip(sclera, 0, 255).astype(np.uint8))

# --- iris (square disc, from the full-res render) --------------------------
IRES = 512
ix0, iy0 = IRIS_CX - IRIS_R, IRIS_CY - IRIS_R
iris_img = img.crop((int(ix0), int(iy0), int(ix0 + 2 * IRIS_R), int(iy0 + 2 * IRIS_R))).resize((IRES, IRES), Image.LANCZOS)
ia = np.array(iris_img).astype(float)
iyy, ixx = np.mgrid[0:IRES, 0:IRES]
idd = np.hypot(ixx - IRES / 2 + 0.5, iyy - IRES / 2 + 0.5) / (IRES / 2)
ia[idd > 0.985] = 0
ia[idd < PUPIL_R / IRIS_R * 0.98] = pupil_rgb          # hide highlight in pupil
iris_img = Image.fromarray(np.clip(ia, 0, 255).astype(np.uint8))

# --- save -------------------------------------------------------------------
skin_img.save(f'{OUT}/skin.png')
sclera_img.save(f'{OUT}/sclera.png')
iris_img.save(f'{OUT}/iris.png')
Image.fromarray(upper).save(f'{OUT}/lid_upper.png')
Image.fromarray(lower).save(f'{OUT}/lid_lower.png')
Image.fromarray(np.clip(shade * 255, 0, 255).astype(np.uint8)).save(f'{OUT}/shade.png')
params = {
    "name": "clayEye",
    "screen": S,
    "sclera_size": [SW, SH],
    "iris_radius": R,
    "pupil_fraction": round(PUPIL_R / IRIS_R, 3),
    "rest": [REST_X, REST_Y],
    "travel": [TRAVEL_X, TRAVEL_Y],
    "iris_min": 108, "iris_max": 132,
    "lid_rest": LID_REST, "lid_look_down": 165,
    "no_mirror": True,
    "notes": "rest = iris center on screen at straight-ahead gaze; travel = +/- px. "
             "iris_min/max = engine iScale range (bigger = bigger pupil). "
             "lid_rest/lid_look_down = upper-lid threshold when level / looking fully down."
}
json.dump(params, open(f'{OUT}/eye.json', 'w'), indent=2)
print('opening box', cols.min(), cols.max(), top[cols].min(), bot[cols].max())
print('rest', REST_X, REST_Y, 'iris R', R, 'sclera rgb', sclera_rgb.round(), 'lid rgb', lid_rgb.round())
