#!/usr/bin/env python3
# Goals Display for Waveshare 7.5" mono V2
# Downloads and displays goals text from Dropbox
# Now includes local caching to avoid unnecessary screen refreshes

import sys, time, requests, hashlib, logging
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1] / "lib"))

from PIL import Image, ImageDraw, ImageFont
from waveshare_epd import epd7in5_V2 as driver

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
LOCAL_GOALS_FILE = Path(__file__).parent / "goals_cache.txt"
LOG_FILE = Path(__file__).parent / "goals_display.log"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

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
        logging.error(f"Error downloading goals text: {e}")
        return "Error: Could not download goals text"

def get_text_hash(text):
    """Generate a hash of the text for comparison"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def load_local_goals():
    """Load the locally cached goals text"""
    try:
        if LOCAL_GOALS_FILE.exists():
            with open(LOCAL_GOALS_FILE, 'r', encoding='utf-8') as f:
                return f.read().strip()
        return None
    except Exception as e:
        logging.warning(f"Error loading local goals: {e}")
        return None

def save_local_goals(text):
    """Save goals text to local cache"""
    try:
        with open(LOCAL_GOALS_FILE, 'w', encoding='utf-8') as f:
            f.write(text)
        logging.info("Goals text saved to local cache")
    except Exception as e:
        logging.error(f"Error saving local goals: {e}")

def has_goals_changed(new_text):
    """Check if the goals text has changed compared to local version"""
    local_text = load_local_goals()
    if local_text is None:
        logging.info("No local cache found, treating as changed")
        return True
    
    new_hash = get_text_hash(new_text)
    local_hash = get_text_hash(local_text)
    
    if new_hash != local_hash:
        logging.info("Goals text has changed")
        return True
    else:
        logging.info("Goals text unchanged, skipping display refresh")
        return False

def draw_base(W, H, font):
    """Draw the base background with title"""
    img = Image.new("1", (W, H), 255)
    d = ImageDraw.Draw(img)
    
    # Calculate padding as 10% of screen width
    padding = int(W * 0.1)
    
    # Title
    d.text((padding, padding), "BIG GOALS THIS WEEK", font=font, fill=0)
    
    return img

def draw_goals_text(W, H, font, goals_text):
    """Draw the goals text on the display"""
    img = draw_base(W, H, font)
    d = ImageDraw.Draw(img)
    
    # Calculate padding as 10% of screen width
    padding = int(W * 0.1)
    
    # Text settings
    start_x = padding
    start_y = padding + 64  # Title height + some spacing
    line_height = 40
    max_width = W - 2 * padding
    
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
    logging.info("Starting goals display script")
    
    # Download goals text first to check for changes
    logging.info("Downloading goals text...")
    goals_text = download_goals_text()
    logging.info(f"Downloaded text: {goals_text[:100]}...")

    # Check if goals have changed
    if not has_goals_changed(goals_text):
        logging.info("No changes detected, exiting without refreshing display")
        return

    # Initialize display only if we need to refresh
    logging.info("Initializing e-paper display...")
    epd = driver.EPD()
    
    if hasattr(epd, "init_fast"):
        epd.init_fast()
    else:
        epd.init()

    # Clear display
    if hasattr(epd, "Clear"):
        epd.Clear()

    W, H = epd.width, epd.height
    font = load_font(28)  # Good size for text display
    
    logging.info(f"Display size: {W}x{H}")

    # Create and display the goals image
    logging.info("Creating goals display...")
    goals_img = draw_goals_text(W, H, font, goals_text)
    goals_buf = epd.getbuffer(goals_img)
    
    # Display the goals
    logging.info("Displaying goals...")
    epd.display(goals_buf)
    
    # Save the new goals text to local cache
    save_local_goals(goals_text)
    
    # Keep display on for a moment before sleeping
    logging.info("Keeping display on for 5 seconds...")
    time.sleep(5.0)
    
    # Put display to sleep
    logging.info("Putting display to sleep...")
    epd.sleep()
    logging.info("Script completed successfully")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Script interrupted by user")
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
