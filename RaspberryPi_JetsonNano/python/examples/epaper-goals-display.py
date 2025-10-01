#!/usr/bin/env python3
# Goals Display for Waveshare 7.5" mono V2
# Downloads and displays goals text from Dropbox

import sys, time, requests
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1] / "lib"))

from PIL import Image, ImageDraw, ImageFont
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

def download_goals_text():
    """Download goals text from Dropbox URL"""
    url = "https://www.dropbox.com/scl/fi/plsvrvgr5atea47bt7xng/big-goals-output.txt?rlkey=t5wos17t47xhc9yvejosespqr&e=1&dl=1"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text.strip()
    except Exception as e:
        print(f"Error downloading goals text: {e}")
        return "Error: Could not download goals text"

def draw_base(W, H, font):
    """Draw the base background with title"""
    img = Image.new("1", (W, H), 255)
    d = ImageDraw.Draw(img)
    
    # Title
    d.text((20, 16), "BIG GOALS THIS WEEK", font=font, fill=0)
    
    return img

def draw_goals_text(W, H, font, goals_text):
    """Draw the goals text on the display"""
    img = draw_base(W, H, font)
    d = ImageDraw.Draw(img)
    
    # Text settings
    start_x = 20
    start_y = 80
    line_height = 40
    margin = 20
    max_width = W - 2 * margin
    
    # Split text into lines and wrap long lines
    lines = []
    for line in goals_text.split('\n'):
        if not line.strip():
            lines.append("")
            continue
            
        # Wrap long lines
        words = line.split()
        current_line = ""
        
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            bbox = d.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]
            
            if text_width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                    current_line = word
                else:
                    # Single word is too long, add it anyway
                    lines.append(word)
        
        if current_line:
            lines.append(current_line)
    
    # Draw each line
    current_y = start_y
    for line in lines:
        if line.strip():  # Only draw non-empty lines
            d.text((start_x, current_y), line, font=font, fill=0)
        current_y += line_height
        
        # Stop if we run out of space
        if current_y > H - line_height:
            break
    
    return img

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
    font = load_font(28)  # Good size for text display
    
    print(f"Display size: {W}x{H}")
    print("Downloading goals text...")

    # Download goals text
    goals_text = download_goals_text()
    print(f"Downloaded text: {goals_text[:100]}...")

    # Create and display the goals image
    print("Creating goals display...")
    goals_img = draw_goals_text(W, H, font, goals_text)
    goals_buf = epd.getbuffer(goals_img)
    
    # Display the goals
    print("Displaying goals...")
    epd.display(goals_buf)
    
    # Keep display on for a moment before sleeping
    print("Keeping display on for 5 seconds...")
    time.sleep(5.0)
    
    # Put display to sleep
    print("Putting display to sleep...")
    epd.sleep()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
