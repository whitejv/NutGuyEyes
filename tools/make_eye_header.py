#!/usr/bin/env python3
"""
make_eye_header.py - build an eye graphics header for Animated_Eyes_1
from a folder of layer PNGs.  Python 3 + Pillow + numpy.

    python3 tools/make_eye_header.py art/clayEye data/clayEye.h

Folder contents (see art/clayEye for an example):
  eye.json       geometry / tuning (screen, sclera_size, iris_radius,
                 pupil_fraction, rest, travel, iris_min, iris_max,
                 lid_rest, lid_look_down)
  sclera.png     SCLERA_W x SCLERA_H. Iris sits at the exact center; paint
                 the pupil (black disc, iris_radius) + highlight there.
  iris.png       square, iris filling the image as a disc, pupil black.
  lid_upper.png  SCREEN x SCREEN gray. Lid covers a pixel when value <= uT.
  lid_lower.png  SCREEN x SCREEN gray. Lid covers a pixel when value <= lT.
                 0 = always covered (use 0 everywhere outside the opening).
  skin.png       SCREEN x SCREEN color drawn wherever the lids are
                 (optional -> EYE_LID_TEXTURE).
  shade.png      SCREEN x SCREEN gray, screen-fixed shading for eyeball
                 pixels, 255 = unchanged (optional -> EYE_SHADE).

Output format matches the Uncanny Eyes / TFT_eSPI tables used by
eye_functions.ino (RGB565 words, polar = angle<<7 | (127 - dist)).
"""
import json, math, os, sys
import numpy as np
from PIL import Image


def rgb565_dither(a):
    """RGB565 with ordered (Bayer 4x4) dithering for smooth gradients."""
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0 - 0.5
    h, w = a.shape[:2]
    t = np.tile(bayer, (h // 4 + 1, w // 4 + 1))[:h, :w]
    a = a.astype(float)
    r = np.clip(a[..., 0] + t * 8, 0, 255); g = np.clip(a[..., 1] + t * 4, 0, 255); b = np.clip(a[..., 2] + t * 8, 0, 255)
    return rgb565(np.stack([r, g, b], -1).round())


def rgb565(a):
    a = a.astype(np.uint32)
    return ((a[..., 0] >> 3) << 11) | ((a[..., 1] >> 2) << 5) | (a[..., 2] >> 3)


def emit(f, ctype, name, size_expr, data, fmt, per_line):
    f.write(f"const {ctype} {name}[{size_expr}] PROGMEM = {{\n")
    flat = data.ravel()
    for i in range(0, len(flat), per_line):
        f.write("  " + ", ".join(fmt(v) for v in flat[i:i + per_line]) + ",\n")
    f.write("};\n\n")


def bilinear(img, x, y):
    h, w = img.shape[:2]
    x = np.clip(x, 0, w - 1.001); y = np.clip(y, 0, h - 1.001)
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
    fx = (x - x0)[..., None]; fy = (y - y0)[..., None]
    p = (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) +
         img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)
    return p


def main(src, dst):
    P = json.load(open(os.path.join(src, "eye.json")))
    name = P.get("name", os.path.splitext(os.path.basename(dst))[0])
    S = P["screen"]
    SW, SH = P["sclera_size"]
    R = P["iris_radius"]
    IW = IH = 2 * R
    MAP_W, MAP_H = 256, 64
    imin, imax = P["iris_min"], P["iris_max"]
    pf = P["pupil_fraction"]
    rx, ry = P["rest"]; tx, ty = P["travel"]

    def load(fn, mode):
        return np.array(Image.open(os.path.join(src, fn)).convert(mode)).astype(float)

    sclera = load("sclera.png", "RGB")
    assert sclera.shape[:2] == (SH, SW), f"sclera.png must be {SW}x{SH}"
    upper = load("lid_upper.png", "L").astype(np.uint8)
    lower = load("lid_lower.png", "L").astype(np.uint8)
    assert upper.shape == (S, S) and lower.shape == (S, S)
    has_skin = os.path.exists(os.path.join(src, "skin.png"))
    has_shade = os.path.exists(os.path.join(src, "shade.png"))

    # gaze range -> sclera window offsets used by frame()
    # iris center on screen = SCLERA/2 - offset
    x_min, x_max = SW // 2 - (rx + tx), SW // 2 - (rx - tx)
    y_min, y_max = SH // 2 - (ry + ty), SH // 2 - (ry - ty)
    for lo, hi, size, axis in ((x_min, x_max, SW, "X"), (y_min, y_max, SH, "Y")):
        if lo < 0 or hi > size - S:
            sys.exit(f"{axis}: rest/travel need sclera offsets {lo}..{hi}, "
                     f"but sclera allows 0..{size - S}. Enlarge sclera_size.")
    if (SW - IW) % 2 or (SH - IH) % 2:
        sys.exit("sclera_size minus iris diameter must be even in both axes")

    # iris: square disc -> unrolled map (rows = outer edge .. pupil edge)
    iris = load("iris.png", "RGB")
    ih, iw = iris.shape[:2]
    i_ref = 63 * 128 / (127 - 128 * pf)        # iScale at which row 63 = pupil edge
    d = np.arange(MAP_H)[:, None] + 0.5
    a = np.arange(MAP_W)[None, :] + 0.5
    rn = (127 - d * 128 / i_ref) / 128          # 1 = rim, pf = pupil edge
    th = a / MAP_W * 2 * math.pi - math.pi
    ix = iw / 2 + rn * (iw / 2) * np.cos(th)
    iy = ih / 2 + rn * (ih / 2) * np.sin(th)
    iris_map = rgb565(np.clip(bilinear(iris, ix, iy), 0, 255))

    # polar table for the IW x IH iris square
    yy, xx = np.mgrid[0:IH, 0:IW]
    dx = xx - R + 0.5; dy = yy - R + 0.5
    dist = np.hypot(dx, dy) / R
    ang = ((np.arctan2(dy, dx) + math.pi) / (2 * math.pi) * 512).astype(int) & 511
    dd = 127 - np.minimum((dist * 128).astype(int), 127)
    polar = np.where(dist >= 1.0, 127, (ang << 7) | dd).astype(np.uint16)

    with open(dst, "w") as f:
        f.write(f"// {name} - generated by tools/make_eye_header.py from {src}\n")
        f.write("// Do not edit by hand: edit the PNGs / eye.json and regenerate.\n\n")
        f.write(f"#define SCLERA_WIDTH  {SW}\n#define SCLERA_HEIGHT {SH}\n")
        f.write(f"#define IRIS_MAP_WIDTH  {MAP_W}\n#define IRIS_MAP_HEIGHT {MAP_H}\n")
        f.write(f"#define SCREEN_WIDTH  {S}\n#define SCREEN_HEIGHT {S}\n")
        f.write(f"#define IRIS_WIDTH  {IW}\n#define IRIS_HEIGHT {IH}\n")
        f.write(f"#define IRIS_MIN {imin} // smallest pupil (engine iScale)\n")
        f.write(f"#define IRIS_MAX {imax} // largest pupil\n")
        f.write("\n// Gaze range as sclera window offsets (eye rests off screen center)\n")
        f.write(f"#define EYE_X_MIN {x_min}\n#define EYE_X_MAX {x_max}\n")
        f.write(f"#define EYE_Y_MIN {y_min}\n#define EYE_Y_MAX {y_max}\n")
        f.write("\n// Upper-lid tracking: threshold when level and when looking fully down\n")
        f.write(f"#define LID_TRACK_REST {P['lid_rest']}\n#define LID_TRACK_DOWN {P['lid_look_down']}\n")
        if has_skin:
            f.write("#define EYE_LID_TEXTURE // lids drawn from lidTex[] instead of a solid color\n")
        if P.get("no_mirror"):
            f.write("#define EYE_NO_MIRROR   // same art on both displays (no left/right flip)\n")
        if has_shade:
            f.write("#define EYE_SHADE       // screen-fixed shading on eyeball pixels (0-32)\n")
        f.write("\n")

        hx = lambda v: f"0x{int(v):04X}"
        dec = lambda v: str(int(v))
        emit(f, "uint16_t", "sclera", "SCLERA_HEIGHT * SCLERA_WIDTH", rgb565_dither(sclera), hx, 8)
        emit(f, "uint16_t", "iris", "IRIS_MAP_HEIGHT * IRIS_MAP_WIDTH", iris_map, hx, 8)
        emit(f, "uint8_t", "upper", "SCREEN_HEIGHT * SCREEN_WIDTH", upper, dec, 16)
        emit(f, "uint8_t", "lower", "SCREEN_HEIGHT * SCREEN_WIDTH", lower, dec, 16)
        emit(f, "uint16_t", "polar", "IRIS_HEIGHT * IRIS_WIDTH", polar, hx, 8)
        if has_skin:
            skin = load("skin.png", "RGB")
            emit(f, "uint16_t", "lidTex", "SCREEN_HEIGHT * SCREEN_WIDTH", rgb565_dither(skin), hx, 8)
        if has_shade:
            # quantize to 0-32 with Floyd-Steinberg dithering (avoids contour bands)
            v = load("shade.png", "L") / 255 * 32
            shade = np.zeros(v.shape, np.uint8)
            for y in range(v.shape[0]):
                for x in range(v.shape[1]):
                    q = min(32, max(0, int(round(v[y, x]))))
                    shade[y, x] = q
                    err = v[y, x] - q
                    if x + 1 < v.shape[1]: v[y, x + 1] += err * 7 / 16
                    if y + 1 < v.shape[0]:
                        if x > 0: v[y + 1, x - 1] += err * 3 / 16
                        v[y + 1, x] += err * 5 / 16
                        if x + 1 < v.shape[1]: v[y + 1, x + 1] += err * 1 / 16
            emit(f, "uint8_t", "shade", "SCREEN_HEIGHT * SCREEN_WIDTH", shade, dec, 16)

    flash = SW * SH * 2 + MAP_W * MAP_H * 2 + S * S * 2 + IW * IH * 2 \
        + (S * S * 2 if has_skin else 0) + (S * S if has_shade else 0)
    print(f"wrote {dst}: ~{flash // 1024} KB of flash tables; "
          f"gaze X {x_min}..{x_max}, Y {y_min}..{y_max}; iris {IW}x{IH}, i_ref {i_ref:.1f}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
