#!/usr/bin/env python3
# Minimal partial-refresh probe for Waveshare 7.5" mono V2
# Focus: verify *true* partial updates in the simplest possible way.

import sys, time
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1] / "lib"))

from PIL import Image, ImageDraw, ImageFont, ImageChops
from waveshare_epd import epd7in5_V2 as driver

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def load_font(size=28):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()

def align8(x):  # controller packs 8 px per byte
    return x - (x % 8)

def up8(x):
    return x if x % 8 == 0 else x + (8 - (x % 8))

def extract_region_bytes(fullbuf, full_width, x0, y0, x1, y1):
    """
    Slice a full-frame 1bpp buffer into window-only bytes for [x0:x1) x [y0:y1).
    x0/x1 must be 8-aligned. Returns a list of bytes.
    """
    if not isinstance(fullbuf, (bytes, bytearray, list)):
        fullbuf = bytes(fullbuf)
    bytes_per_row = full_width // 8
    region_bytes_per_row = (x1 - x0) // 8
    xbyte = x0 // 8
    out = []
    idx = 0
    for y in range(y0, y1):
        row_start = y * bytes_per_row
        seg = fullbuf[row_start + xbyte : row_start + xbyte + region_bytes_per_row]
        out.extend(seg)
        idx += 1
    return out

def find_partial(epd):
    base = None
    part = None
    for name in ("displayPartBaseImage", "DisplayPartBaseImage", "Display_Base"):
        if hasattr(epd, name):
            base = name; break
    for name in ("display_Partial", "displayPartial", "Display_Partial", "DisplayPartial"):
        if hasattr(epd, name):
            part = name; break
    return base, part

def call_partial_window(epd, method_name, region_bytes, x0, y0, x1, y1):
    """
    Try common partial signatures in priority order.
    Returns True on success.
    """
    fn = getattr(epd, method_name)
    # Most 7.5 V2 drivers use Xstart,Ystart,Xend,Yend (end exclusive or driver -1 internally)
    tries = [
        (region_bytes, x0, y0, x1, y1),
        (region_bytes, x0, y0, (x1 - x0), (y1 - y0)),  # some use width,height
        ([*region_bytes], x0, y0, x1, y1),             # list vs bytes
    ]
    for args in tries:
        try:
            fn(*args)
            return True
        except TypeError:
            continue
    return False

def call_partial_fullframe(epd, method_name, fullbuf, W, H):
    fn = getattr(epd, method_name)
    tries = [
        (fullbuf, 0, 0, W, H),
        (fullbuf,),  # some variants take just a full buffer
    ]
    for args in tries:
        try:
            fn(*args)
            return True
        except TypeError:
            continue
    return False

def draw_base(W, H, font):
    img = Image.new("1", (W, H), 255)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W-1, H-1), outline=0, width=2)
    d.text((20, 16), "Partial Probe — 7.5\" V2", font=font, fill=0)
    # light grid helps spot real partial vs full
    step = 40
    for x in range(0, W, step):
        d.line((x, 0, x, H-1), fill=0)
    for y in range(0, H, step):
        d.line((0, y, W-1, y), fill=0)
    return img

def draw_ticker_frame(W, H, font, flip=False, box=(200, 120, 440, 200)):
    img = draw_base(W, H, font)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    msg = "TICK" if not flip else "TOCK"
    if flip:
        d.rectangle((x0, y0, x1, y1), fill=0, outline=0, width=2)
        d.text((x0+12, y0+18), msg, font=font, fill=255)
    else:
        d.rectangle((x0, y0, x1, y1), fill=255, outline=0, width=2)
        d.text((x0+12, y0+18), msg, font=font, fill=0)
    return img

def main():
    epd = driver.EPD()

    # Init (prefer fast if present)
    if hasattr(epd, "init_fast"):
        epd.init_fast()
    else:
        epd.init()

    # Clean start
    if hasattr(epd, "Clear"):
        epd.Clear()

    W, H = epd.width, epd.height
    font = load_font(24)

    # --- 1) Full base push ---
    base_img = draw_base(W, H, font)
    base_buf = epd.getbuffer(base_img)
    epd.display(base_buf)

    # --- Partial handshake discovery ---
    base_name, part_name = find_partial(epd)
    if base_name:
        try:
            getattr(epd, base_name)(base_buf)
        except Exception:
            base_name = None

    print(f"[probe] partial_method={part_name or 'none'} base_set={bool(base_name)}")

    # If no partial method, at least prove we can still update
    if not part_name:
        print("[probe] No partial method found; doing two normal full updates as a sanity check.")
        for flip in (False, True):
            img = draw_ticker_frame(W, H, font, flip=flip)
            epd.display(epd.getbuffer(img))
            time.sleep(1.0)
        epd.sleep()
        return

    # Define a small test window (8-px aligned in X)
    raw_box = (200, 120, 440, 200)
    x0, y0, x1, y1 = raw_box
    x0 = align8(x0); x1 = up8(x1)
    raw_box = (x0, y0, x1, y1)
    print(f"[probe] window (aligned): {raw_box}")

    # --- 2) REGION PARTIAL: flip box a few times using windowed region bytes ---
    success_region = False
    try:
        for i in range(4):
            img = draw_ticker_frame(W, H, font, flip=(i % 2 == 1), box=raw_box)
            fullbuf = epd.getbuffer(img)
            region = extract_region_bytes(fullbuf, W, x0, y0, x1, y1)
            ok = call_partial_window(epd, part_name, region, x0, y0, x1, y1)
            if not ok:
                print("[probe] region-partial call signature mismatch; aborting region test.")
                success_region = False
                break
            success_region = True
            time.sleep(0.6)
    except Exception as e:
        print(f"[probe] region-partial exception: {e}")
        success_region = False

    # --- 3) FULL-WINDOW PARTIAL: same flip but send full-frame buffer to partial ---
    success_fullwin = False
    try:
        for i in range(4):
            img = draw_ticker_frame(W, H, font, flip=(i % 2 == 1), box=raw_box)
            fullbuf = epd.getbuffer(img)
            ok = call_partial_fullframe(epd, part_name, fullbuf, W, H)
            if not ok:
                print("[probe] full-window partial call mismatch; aborting this test.")
                success_fullwin = False
                break
            success_fullwin = True
            time.sleep(0.6)
    except Exception as e:
        print(f"[probe] full-window-partial exception: {e}")
        success_fullwin = False

    print(f"[result] region_partial={'OK' if success_region else 'NO'} | full_window_partial={'OK' if success_fullwin else 'NO'}")

    # Park panel
    epd.sleep()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
