// HYPNO MODE ---------------------------------------------------------------
// Full-screen rotating color spiral that takes over both displays. None of
// the eye graphics are used while it runs; the eye engine simply pauses and
// resumes (re-opening with a blink) when the spiral ends.
//
// For now the mode is switched by a timer (HYPNO_EYE_TIME / HYPNO_SPIRAL_TIME
// in config.h). Later, music detection can call hypnoSetMode() instead.
//
// How it draws: at startup a 240x240 table stores, for every pixel, a
// "spiral index" = angle * arms + distance * twist (0-255, wraps). Each frame
// a pixel's color is just palette[index + phase]; advancing the phase over
// time makes the spiral rotate. The 256-color palette is rebuilt from random
// colors every HYPNO_COLOR_TIME ms, crossfading from the previous one.

#ifdef HYPNO_MODE

static uint8_t  hypnoIndex[HYPNO_SIZE * HYPNO_SIZE]; // Spiral index per pixel (57.6 KB RAM)
static uint16_t hypnoPal[256];                       // Current palette, RGB565 byte-swapped
static uint8_t  palFrom[HYPNO_STOPS][3], palTo[HYPNO_STOPS][3]; // Color stops being blended
static uint32_t palChangeMs = 0;                     // When the current crossfade started

// Random vivid color: random hue, full saturation, high brightness
void hypnoRandomColor(uint8_t *rgb, float value) {
  float h = random(360) / 60.0, f = h - (int)h;
  float p = 0, q = 1 - f, t = f;
  float r, g, b;
  switch ((int)h) {
    case 0: r = 1; g = t; b = p; break;
    case 1: r = q; g = 1; b = p; break;
    case 2: r = p; g = 1; b = t; break;
    case 3: r = p; g = q; b = 1; break;
    case 4: r = t; g = p; b = 1; break;
    default: r = 1; g = p; b = q; break;
  }
  rgb[0] = r * value * 255; rgb[1] = g * value * 255; rgb[2] = b * value * 255;
}

// Start a crossfade to a new random set of color stops. Even stops are
// bright colors, odd stops are near-black, so the arms stay high-contrast.
void hypnoNewColors(void) {
  memcpy(palFrom, palTo, sizeof palFrom);
  for (uint8_t s = 0; s < HYPNO_STOPS; s++) {
    if (s & 1) hypnoRandomColor(palTo[s], 0.12);      // Dark band (tinted)
    else       hypnoRandomColor(palTo[s], 1.0);       // Bright band
  }
  palChangeMs = millis();
}

// Rebuild the 256-entry palette: smooth cyclic gradient through the color
// stops, crossfaded old->new, scaled by overall brightness (0-256).
void hypnoBuildPalette(uint32_t now, uint16_t brightness) {
  uint32_t fade = now - palChangeMs;
  uint16_t mix = (fade >= HYPNO_COLOR_FADE) ? 256 : (fade * 256) / HYPNO_COLOR_FADE;
  for (uint16_t i = 0; i < 256; i++) {
    uint16_t pos = i * HYPNO_STOPS;                   // 0 .. 256*STOPS
    uint8_t  s0 = pos >> 8, s1 = (s0 + 1) % HYPNO_STOPS;
    uint16_t w = pos & 0xFF;                          // Position between stops
    w = (uint16_t)((1.0 - cosf(w * PI / 256.0)) * 128.0); // Ease for soft band edges
    uint16_t rgb[3];
    for (uint8_t c = 0; c < 3; c++) {
      uint16_t a = (palFrom[s0][c] * (256 - w) + palFrom[s1][c] * w) >> 8;
      uint16_t b = (palTo[s0][c]   * (256 - w) + palTo[s1][c]   * w) >> 8;
      rgb[c] = (((a * (256 - mix) + b * mix) >> 8) * brightness) >> 8;
    }
    uint16_t p = ((rgb[0] & 0xF8) << 8) | ((rgb[1] & 0xFC) << 3) | (rgb[2] >> 3);
    hypnoPal[i] = p >> 8 | p << 8;                    // Pre-swap bytes like drawEye()
  }
}

// Build the per-pixel spiral table. Runs once from setup() (~0.1-0.3 s).
void hypnoInit(void) {
  const float c = (HYPNO_SIZE - 1) / 2.0;
  for (uint16_t y = 0; y < HYPNO_SIZE; y++) {
    for (uint16_t x = 0; x < HYPNO_SIZE; x++) {
      float dx = x - c, dy = y - c;
      float angle = (atan2f(dy, dx) + PI) * (256.0 / (2.0 * PI)); // 0-256 per turn
      float dist  = sqrtf(dx * dx + dy * dy);
      int32_t v = (int32_t)(angle * HYPNO_ARMS + dist * HYPNO_TWIST);
      hypnoIndex[y * HYPNO_SIZE + x] = (uint8_t)(v & 0xFF);
    }
  }
  hypnoNewColors();                                   // Pick a first palette
  memcpy(palFrom, palTo, sizeof palFrom);
}

// Render one frame of the spiral on every display.
void hypnoFrame(void) {
  uint32_t now = millis();
  uint32_t inMode = now - modeStartMs;

  // New random colors every few seconds
  if (now - palChangeMs >= HYPNO_COLOR_TIME) hypnoNewColors();

  // Fade in at the start of the spiral period, out at the end
  uint16_t brightness = 256;
  if (inMode < HYPNO_FADE_TIME) brightness = (inMode * 256) / HYPNO_FADE_TIME;
  else if (inMode + HYPNO_FADE_TIME > HYPNO_SPIRAL_TIME)
    brightness = ((HYPNO_SPIRAL_TIME - min(inMode, (uint32_t)HYPNO_SPIRAL_TIME)) * 256) / HYPNO_FADE_TIME;
  hypnoBuildPalette(now, brightness);

  // Rotation: HYPNO_SPEED palette cycles per second, from elapsed time so
  // the spin rate doesn't depend on frame rate
  uint8_t phase = (uint8_t)((uint32_t)((micros() / 1000.0) * HYPNO_SPEED * 256.0 / 1000.0));

  for (uint8_t e = 0; e < NUM_EYES; e++) {
#ifdef HYPNO_COUNTER_ROTATE
    uint8_t ph = (e & 1) ? -phase : phase;          // Second display spins the other way
#else
    uint8_t ph = phase;
#endif
    // Select this display only (same sequence as drawEye)
    if (NUM_EYES > 1) digitalWrite(eye[e ? 0 : 1].tft_cs, HIGH);
    digitalWrite(eye[e].tft_cs, LOW);
    delayMicroseconds(5);
    tft.setRotation(eyeInfo[e].rotation);             // Upside-down mounts handled here
    tft.startWrite();
    tft.setAddrWindow(0, 0, HYPNO_SIZE, HYPNO_SIZE);

    uint32_t pixels = 0;
    const uint8_t *src = hypnoIndex;
    for (uint32_t i = 0; i < (uint32_t)HYPNO_SIZE * HYPNO_SIZE; i++) {
      pbuffer[dmaBuf][pixels++] = hypnoPal[(uint8_t)(*src++ - ph)];
      if (pixels >= BUFFER_SIZE) {
        yield();
#ifdef USE_DMA
        tft.pushPixelsDMA(&pbuffer[dmaBuf][0], pixels);
        dmaBuf = !dmaBuf;
#else
        tft.pushPixels(pbuffer, pixels);
#endif
        pixels = 0;
      }
    }
    if (pixels) {
#ifdef USE_DMA
      tft.pushPixelsDMA(&pbuffer[dmaBuf][0], pixels);
      dmaBuf = !dmaBuf;
#else
      tft.pushPixels(pbuffer, pixels);
#endif
    }
    tft.endWrite();
    digitalWrite(eye[e].tft_cs, HIGH);
    delayMicroseconds(2);
  }

  user_loop(); // Keep any user*.cpp add-ons running in this mode too
}

// Switch modes. Leaving the spiral: the eyes come back starting closed and
// blink open (DEBLINK state), so the change looks deliberate.
void hypnoSetMode(uint8_t mode) {
  if (mode == displayMode) return;
  displayMode = mode;
  modeStartMs = millis();
  if (mode == MODE_EYE) {
    uint32_t t = micros();
    for (uint8_t e = 0; e < NUM_EYES; e++) {
      eye[e].blink.state     = DEBLINK;
      eye[e].blink.startTime = t;
      eye[e].blink.duration  = 300000; // 0.3 s to open
    }
  } else {
    hypnoNewColors();                  // Fresh colors each time the spiral starts
    memcpy(palFrom, palTo, sizeof palFrom);
  }
}

// Timer-driven mode changes. Called from loop() and from inside the eye
// engine's animation loop, so a switch happens on time even mid-animation.
// Returns the current mode.
uint8_t modeTick(void) {
  uint32_t limit = (displayMode == MODE_EYE) ? HYPNO_EYE_TIME : HYPNO_SPIRAL_TIME;
  if (millis() - modeStartMs >= limit)
    hypnoSetMode(displayMode == MODE_EYE ? MODE_HYPNO : MODE_EYE);
  return displayMode;
}

#endif // HYPNO_MODE
