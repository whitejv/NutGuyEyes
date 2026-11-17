# clayEye art

Editable layers for `data/clayEye.h`. Touch up any PNG (or eye.json), then regenerate:

    python3 tools/make_eye_header.py art/clayEye data/clayEye.h

Needs Python 3 with Pillow and numpy (`pip3 install pillow numpy`).

| File | Size | What it is |
|---|---|---|
| skin.png | 240x240 | Everything the eyelids draw: face, brow, fold, and the closed-lid skin over the eye opening |
| sclera.png | 300x306 | Eyeball white. The iris sits at the exact center; the black pupil disc and highlight are painted there |
| iris.png | square | The iris as a disc (pupil area black). Unrolled by the converter |
| lid_upper.png / lid_lower.png | 240x240 gray | Lid threshold maps. 0 = always covered (everything outside the eye opening) |
| shade.png | 240x240 gray | Screen-fixed eyeball shading, 255 = full brightness |
| eye.json | | Rest position, gaze travel, pupil range, lid tracking, no_mirror |
| source_render.png | | Original image the layers were cut from |

`tools/extract_clay_layers.py source_render.png art/clayEye` recreates these layers from the
render (overwrites hand edits).
