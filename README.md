# NutGuyEyes

Animated eyes for the Nut Guy (nutcracker) display: two round 240x240 displays show a
clay-style cartoon eye that darts around, blinks and lets its upper lid follow the gaze.
A **Hypno mode** periodically replaces both eyes with a full-screen rotating color
spiral. A microphone is wired in so that, in a later version, music will trigger Hypno
mode and sync the spiral to the beat (today a timer switches modes).

Based on Adafruit's "Uncanny Eyes" (Phil Burgess) as adapted by Bodmer for the
TFT_eSPI display library.

## Hardware

| Part | Details |
|---|---|
| Processor | **Arduino Nano ESP32**: ESP32-S3 (u-blox NORA-W106), dual-core 240 MHz, 16 MB flash, 8 MB PSRAM, 3.3 V logic |
| Displays | 2 x GC9A01 round 240x240 TFT on a shared SPI bus, one chip select each |
| Microphone | Adafruit I2S MEMS Microphone Breakout, **ICS-43434** (#6049), 3.3 V |

### Display wiring (GC9A01)

| Display signal | Nano ESP32 pin | ESP32-S3 GPIO |
|---|---|---|
| SCK | D13 | 48 |
| MOSI (data to display) | D11 | 38 |
| MISO (not used by display) | D12 | 47 |
| CS, display 1 | D5 | 8 |
| CS, display 2 | D7 | 10 |
| DC | D4 | 7 |
| RST | D3 | 6 |
| Backlight | D6 | 9 |
| SD card CS (unused) | D2 | 5 |
| VIN | 3.3V | |
| GND | GND | |

SCK, MOSI, MISO, DC, RST and backlight are set in the TFT_eSPI library's setup file. The
two chip selects are set in `config.h` (`TFT1_CS`, `TFT2_CS`).

> **Check:** `config.h` currently has `TFT1_CS 18`, while the wiring table above
> (from the wiring spreadsheet) shows display 1's CS on D5 / GPIO8. Confirm which is
> correct for the current build.

### Microphone wiring (ICS-43434, I2S)

| Mic pin | Nano ESP32 pin | ESP32-S3 GPIO |
|---|---|---|
| 3V | 3.3V | |
| GND | GND | |
| BCLK | A0 | 1 |
| LRCL (word select) | A3 | 4 |
| DOUT | A6 | 13 |
| SEL | GND (left channel) | |

None of these pins are boot/strapping pins or used by the board's LEDs or USB. The
I2S peripheral is routed to them in software. In code, use the raw GPIO numbers
(1, 4, 13) for the I2S driver.

### Pin numbering

`config.h` uses raw GPIO numbers (e.g. `TFT2_CS 10` = D7). In the Arduino IDE, set
**Tools > Pin Numbering > By GPIO number** for the Nano ESP32, or the numbers will
refer to different pins.

### Related: Nut Guy body lighting (separate WLED controller)

The body LEDs run on a separate QuinLED Uno controller running WLED, not on this board.
Recorded here for reference.

| Segment | Part | LEDs | GPIO |
|---|---|---|---|
| 0 | Leg R | 40 | 4 |
| 1 | Leg L | 40 | 16 |
| 2 | Body | 147 | 17 |
| 3 | Arm R | 30 | 12 |
| 4 | Arm L | 30 | 21 |
| 5 | Head | 300 | 2 |
| 6 | Mace | 179 | 22 |
| 7 | Base | 161 | 5 |

| WLED sound input | GPIO |
|---|---|
| Mic WS | 27 |
| Mic SD | 25 |
| Mic SCK | 32 |

## Files

| File | Purpose |
|---|---|
| `NutGuyEyes.ino` | Main tab: display setup, mode switch, `setup()` / `loop()` |
| `eye_functions.ino` | Eye engine: per-pixel eye drawing, eye movement, blinking, eyelid tracking |
| `hypno.ino` | Hypno mode: full-screen color spiral, random palettes, eye/spiral timer |
| `config.h` | **All settings**: which eye to use, display pins and rotation, movement and blink options, Hypno mode settings |
| `user.cpp` | Empty hooks (`user_setup`, `user_loop`) for add-on code; required by the sketch |
| `data/clayEye.h` | The clay cartoon eye (in use). Generated, don't edit by hand |
| `data/*.h` (other 13) | Stock Uncanny Eyes designs, selectable in `config.h` |
| `art/clayEye/` | Editable source layers for the clay eye (PNGs + `eye.json`) and the original render |
| `tools/make_eye_header.py` | Converts an eye's layer PNGs + `eye.json` into a `data/*.h` header |
| `tools/extract_clay_layers.py` | One-time script that cut the clay eye layers from `source_render.png` |
| `AnimatedEye1.xlsx` | Wiring spreadsheet (local only, excluded from git) |

The Arduino IDE compiles every `.ino` in the folder as one program (main tab first,
then the others alphabetically), so all tabs share globals. `user.cpp` is compiled
separately.

## Display options (config.h)

- **Display rotation:** `TFT_1_ROT` / `TFT_2_ROT` (0-3, 90 degree steps). A display mounted
  upside down uses a value 2 away from the other (currently 3 and 1).
- **Eye movement:** random darting by default; `TRACKING` (upper lid follows the gaze),
  `AUTOBLINK`; optional joystick or `DIAMOND_PATTERN_MODE`.
- **Hypno mode:** `HYPNO_MODE` on/off, eye and spiral times (20 s each), fade time, color
  change interval, spin speed, number of arms, twist, counter-rotation. Comment out
  `HYPNO_MODE` to run eyes only.
- **Performance:** uncomment `USE_DMA` at the top of `NutGuyEyes.ino` for faster SPI
  transfers (also reduces spiral tearing).

## Defining the eyes

The eye is built from layers that the engine combines each frame:

- **Sclera:** the eyeball image, larger than the screen so it can slide as the eye looks
  around. The black pupil disc and highlight are painted at its exact center.
- **Iris:** a disc stored "unrolled" (angle x distance) so the pupil can grow and shrink.
- **Upper / lower lid maps:** grayscale maps. A pixel is drawn as eyelid when its value is
  at or below the current lid threshold. Moving the threshold opens and closes the lids.
- **Skin (optional):** a color image drawn wherever the lids are (face, brow, closed lid).
  Without it, lids are a solid color.
- **Shade (optional):** screen-fixed shading so the eyeball looks round as the iris moves.

### Use a stock eye

In `config.h`, uncomment one `#include "data/...h"` line and comment out the others.
For `owlEye`, `naugaEye` and `doeEye`, also comment out `TRACKING`.

### Change or create an eye

1. **Make the layers** in a folder such as `art/myEye/` (copy `art/clayEye/` as a starting point):

   | File | Size | Contents |
   |---|---|---|
   | `sclera.png` | e.g. 300x306 | Eyeball; pupil disc + highlight at the exact center |
   | `iris.png` | square | Iris filling the image as a disc, pupil area black |
   | `lid_upper.png`, `lid_lower.png` | 240x240 gray | Lid threshold maps; 0 = always covered (everything outside the eye opening) |
   | `skin.png` | 240x240 | Optional: what the lids show |
   | `shade.png` | 240x240 gray | Optional: eyeball shading, 255 = full brightness |

2. **Set the numbers in `eye.json`:**
   - `rest`: iris center on screen when looking straight ahead
   - `travel`: how far the eye may move in each direction, in pixels
   - `iris_radius`, `pupil_fraction`, `iris_min` / `iris_max`: iris size and pupil range
   - `lid_rest` / `lid_look_down`: upper-lid position when level and when looking down
   - `no_mirror`: `true` uses identical art on both displays (consistent lighting)

3. **Generate the header** (Python 3 with Pillow and numpy):

       python3 tools/make_eye_header.py art/myEye data/myEye.h

   The script checks that the gaze range fits the sclera size and reports the flash used
   (the clay eye is about 500 KB).

4. **Select it** in `config.h` with `#include "data/myEye.h"`, then compile and upload.

5. **Test** a full blink, all four gaze extremes and the smallest/largest pupil. Most fixes
   are made in the lid maps and `eye.json`, then regenerate.

The header tells the engine which optional features to use (`EYE_LID_TEXTURE`,
`EYE_SHADE`, `EYE_NO_MIRROR`, the gaze range and lid tracking values), so the stock
eyes keep working unchanged alongside custom ones.

`tools/extract_clay_layers.py` shows how the clay layers were cut from a single rendered
image. Its crop and positions are tuned to `source_render.png`, so treat it as a template
rather than a general tool.

## Planned

- Microphone beat detection on the second core: music starts Hypno mode, the spiral
  spins in tempo and flashes on each beat, colors change on bars, and the eyes return
  when the music stops. This replaces the 20-second timer.
- Distance sensor so the eyes follow people (next year).
