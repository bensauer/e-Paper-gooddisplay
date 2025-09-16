#!/usr/bin/env python3
# Word Processor Test for Waveshare 7.5" mono V2
# Displays a series of test words slowly with partial refresh

import sys, time
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1] / "lib"))

from PIL import Image, ImageDraw, ImageFont
from waveshare_epd import epd7in5_V2 as driver

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Test words to display
TEST_WORDS = [
    "Hello", "World", "E-Paper", "Display", "Partial", "Refresh", 
    "Test", "Word", "Processor", "Slow", "Typing", "Effect",
    "Waveshare", "7.5inch", "Monochrome", "Screen", "Arduino",
    "Raspberry", "Pi", "Python", "Library", "Driver", "Code"
]

def load_font(size=28):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()

def align8(x):  # controller packs 8 px per byte
    return x - (x % 8)

def up8(x):
    return x if x % 8 == 0 else x + (8 - (x % 8))

def draw_base(W, H, font):
    """Draw the base background with title and grid"""
    img = Image.new("1", (W, H), 255)
    d = ImageDraw.Draw(img)
    
    # Title
    d.text((20, 16), "Word Processor Test — 7.5\" V2", font=font, fill=0)
    
    # Light grid to help spot partial vs full updates
    step = 40
    for x in range(0, W, step):
        d.line((x, 0, x, H-1), fill=0)
    for y in range(0, H, step):
        d.line((0, y, W-1, y), fill=0)
    
    return img

class ParagraphWriter:
    """Handles paragraph-style word display with wrapping"""
    
    def __init__(self, W, H, font, start_x=50, start_y=100, line_height=40, margin=50):
        self.W = W
        self.H = H
        self.font = font
        self.start_x = start_x
        self.start_y = start_y
        self.line_height = line_height
        self.margin = margin
        self.max_width = W - 2 * margin
        self.current_x = start_x
        self.current_y = start_y
        self.words_displayed = []
        
    def get_word_width(self, word):
        """Get the width of a word in pixels"""
        bbox = ImageDraw.Draw(Image.new("1", (1, 1))).textbbox((0, 0), word, font=self.font)
        return bbox[2] - bbox[0]
    
    def get_space_width(self):
        """Get the width of a space character"""
        return self.get_word_width(" ")
    
    def check_fit(self, word):
        """Check if word fits on current line"""
        word_width = self.get_word_width(word)
        space_width = self.get_space_width()
        return (self.current_x + space_width + word_width) <= (self.W - self.margin)
    
    def add_word(self, word):
        """Add a word to the paragraph, wrapping if necessary"""
        space_width = self.get_space_width()
        
        # Add space before word (except for first word)
        if self.words_displayed:
            if not self.check_fit(word):
                # Move to next line
                self.current_x = self.start_x
                self.current_y += self.line_height
            else:
                # Add space
                self.current_x += space_width
        else:
            # First word, no space needed
            pass
            
        self.words_displayed.append(word)
        return self.current_x, self.current_y
    
    def get_display_region(self, word):
        """Get the region that needs to be updated for a word"""
        word_width = self.get_word_width(word)
        word_height = self.line_height
        
        # Align to 8-pixel boundaries
        x0 = align8(self.current_x)
        y0 = self.current_y
        x1 = up8(self.current_x + word_width)
        y1 = y0 + word_height
        
        return x0, y0, x1, y1

def draw_paragraph_frame(W, H, font, writer):
    """Draw the paragraph with all words and highlight current word"""
    img = draw_base(W, H, font)
    d = ImageDraw.Draw(img)
    
    # Draw all words in their positions
    current_x = writer.start_x
    current_y = writer.start_y
    
    for i, word in enumerate(writer.words_displayed):
        if i > 0:  # Add space before word (except first)
            space_width = writer.get_space_width()
            if not writer.check_fit(word):
                # Word would wrap, so we're on a new line
                current_x = writer.start_x
                current_y += writer.line_height
            else:
                current_x += space_width
        
        if i == len(writer.words_displayed) - 1:  # Current word
            # Highlight current word with a subtle background
            word_width = writer.get_word_width(word)
            d.rectangle((current_x-2, current_y-2, current_x+word_width+2, current_y+writer.line_height+2), fill=0, outline=0)
            d.text((current_x, current_y), word, font=font, fill=255)  # White text on black background
        else:
            d.text((current_x, current_y), word, font=font, fill=0)  # Black text
    
    return img

def display_word_with_partial(epd, word, writer, delay=1.5):
    """Display a word in paragraph style using partial refresh"""
    W, H = epd.width, epd.height
    
    # Add word to paragraph and get position
    x, y = writer.add_word(word)
    
    # Get the region that needs updating
    x0, y0, x1, y1 = writer.get_display_region(word)
    
    print(f"Displaying: '{word}' at position ({x}, {y}) in region ({x0}, {y0}, {x1}, {y1})")
    
    # Draw the paragraph with all words
    img = draw_paragraph_frame(W, H, writer.font, writer)
    fullbuf = epd.getbuffer(img)
    
    # Extract region bytes for partial update
    bytes_per_row = W // 8
    region_bytes_per_row = (x1 - x0) // 8
    xbyte = x0 // 8
    
    region_bytes = []
    for y in range(y0, y1):
        row_start = y * bytes_per_row
        seg = fullbuf[row_start + xbyte : row_start + xbyte + region_bytes_per_row]
        region_bytes.extend(seg)
    
    # Use partial refresh
    try:
        epd.display_Partial(region_bytes, x0, y0, x1, y1)
        print(f"✓ Partial refresh successful for '{word}'")
    except Exception as e:
        print(f"✗ Partial refresh failed for '{word}': {e}")
        # Fallback to full display
        epd.display(fullbuf)
    
    # Wait before next word
    time.sleep(delay)

def main():
    epd = driver.EPD()

    # Initialize display
    print("Initializing e-paper display...")
    if hasattr(epd, "init_fast"):
        epd.init_fast()
    else:
        epd.init()

    # Clear display
    if hasattr(epd, "Clear"):
        epd.Clear()

    W, H = epd.width, epd.height
    font = load_font(28)  # Good size for paragraph text
    
    print(f"Display size: {W}x{H}")
    print(f"Starting paragraph word processor test with {len(TEST_WORDS)} words...")

    # Create paragraph writer
    writer = ParagraphWriter(W, H, font, start_x=50, start_y=120, line_height=35, margin=50)
    
    print(f"Paragraph area: margin={writer.margin}, line_height={writer.line_height}")

    # Display initial base frame
    print("Setting up base frame...")
    base_img = draw_base(W, H, font)
    base_buf = epd.getbuffer(base_img)
    epd.display(base_buf)
    time.sleep(1.0)

    # Display each word slowly with partial refresh in paragraph style
    print("\nStarting paragraph word display sequence...")
    print("=" * 60)
    
    for i, word in enumerate(TEST_WORDS):
        print(f"\nWord {i+1}/{len(TEST_WORDS)}: '{word}'")
        display_word_with_partial(epd, word, writer, delay=1.8)
    
    print("\n" + "=" * 60)
    print("Paragraph word processor test completed!")
    print(f"Displayed {len(writer.words_displayed)} words in paragraph format.")
    print("All words displayed with partial refresh.")
    
    # Keep display on for a moment before sleeping
    time.sleep(3.0)
    
    # Put display to sleep
    print("Putting display to sleep...")
    epd.sleep()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
