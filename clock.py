import pygame
import math
import time
import json
import base64
import requests
import threading
import random
from io import BytesIO
from PIL import Image
import numpy as np
from datetime import datetime

# Initialize Pygame
pygame.init()

# Constants
WIDTH = 640
HEIGHT = 360
CENTER = (WIDTH // 2, HEIGHT // 2)
CLOCK_RADIUS = min(WIDTH, HEIGHT) // 3
API_URL = "http://orinputer.local:7860/sdapi/v1/txt2img"
BACKGROUND_COLOR = (0, 0, 0)  # Pure black

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
OVERLAY_COLOR = (0, 0, 0, 153)  # 40% transparent black (0.4 * 255 = 102)

# Set up display
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Analog Clock with AI Background")

# Create surfaces for drawing
api_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)  # For sending to API
overlay_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)  # For display overlay

def generate_random_prompt():
    settings = [
        "at dawn", "at dusk", "under moonlight", "in twilight", "at midnight",
        "in a mystical realm", "in a dream dimension", "in an ethereal space"
    ]
    main_elements = [
        "a grand clockwork mechanism", "an ancient timekeeper's sanctuary",
        "a cosmic observatory", "a temporal dimension", "a time-bending realm",
        "a celestial chronometer", "an ethereal timescape"
    ]
    details = [
        "intricate gears floating in space", "swirling time spirals",
        "floating numerical constellations", "temporal energy streams",
        "crystalline chronographs", "orbiting time fragments"
    ]
    atmospheres = [
        "serene and mysterious", "enigmatic and profound",
        "timeless and ethereal", "cosmic and surreal"
    ]
    qualities = [
        "ultra-detailed", "hyper-realistic", "HDR", "8k",
        "cinematic lighting", "dramatic atmosphere"
    ]

    prompt = f"{random.choice(main_elements)} {random.choice(settings)}, {random.choice(details)}, {random.choice(details)}, {random.choice(atmospheres)}, {random.choice(qualities)}, {random.choice(qualities)}, trending on ArtStation"
    print(f"\nGenerated prompt: {prompt}")
    return prompt

def draw_tapered_line(surface, color, start_pos, end_pos, start_width, end_width):
    """Draw a line that is wider at the start and narrower at the end"""
    angle = math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])
    length = math.sqrt((end_pos[0] - start_pos[0])**2 + (end_pos[1] - start_pos[1])**2)
    
    # Create points for a polygon
    points = []
    for t in range(0, 101, 5):  # More points = smoother taper
        t = t / 100
        # Current width at this point
        width = start_width * (1 - t) + end_width * t
        # Position along the line
        x = start_pos[0] + (end_pos[0] - start_pos[0]) * t
        y = start_pos[1] + (end_pos[1] - start_pos[1]) * t
        # Add points perpendicular to the line
        points.append((
            x + math.cos(angle + math.pi/2) * width/2,
            y + math.sin(angle + math.pi/2) * width/2
        ))
    
    # Add points in reverse for the other side
    for t in range(100, -1, -5):
        t = t / 100
        width = start_width * (1 - t) + end_width * t
        x = start_pos[0] + (end_pos[0] - start_pos[0]) * t
        y = start_pos[1] + (end_pos[1] - start_pos[1]) * t
        points.append((
            x + math.cos(angle - math.pi/2) * width/2,
            y + math.sin(angle - math.pi/2) * width/2
        ))
    
    pygame.draw.polygon(surface, color, points)

def draw_clock_hands(hours, minutes):
    """Draw clock hands for API only"""
    api_surface.fill((0, 0, 0, 0))  # Clear with transparent
    overlay_surface.fill(OVERLAY_COLOR)  # Fill with semi-transparent black
    
    # Hour hand
    hour_angle = math.radians((hours % 12 + minutes / 60) * 360 / 12 - 90)
    hour_length = CLOCK_RADIUS * 0.5
    hour_end = (
        CENTER[0] + hour_length * math.cos(hour_angle),
        CENTER[1] + hour_length * math.sin(hour_angle)
    )
    draw_tapered_line(api_surface, WHITE, CENTER, hour_end, 20, 4)
    
    # Minute hand
    minute_angle = math.radians(minutes * 360 / 60 - 90)
    minute_length = CLOCK_RADIUS * 0.7
    minute_end = (
        CENTER[0] + minute_length * math.cos(minute_angle),
        CENTER[1] + minute_length * math.sin(minute_angle)
    )
    draw_tapered_line(api_surface, WHITE, CENTER, minute_end, 12, 2)
    
    save_debug_image(api_surface, "clockface")
    
    return api_surface

def surface_to_base64(surface):
    """Convert a pygame surface to base64 string.
    The surface should be in RGBA format with a black background and white clock hands."""
    # First ensure we're working with RGBA
    if surface.get_bitsize() != 32:
        temp = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        temp.blit(surface, (0, 0))
        surface = temp

    # Convert to PIL Image
    string_image = pygame.image.tostring(surface, 'RGBA')
    pil_image = Image.frombytes('RGBA', (WIDTH, HEIGHT), string_image)
    
    # Convert to RGB with white on black background
    # This ensures the API gets a clean black and white image
    rgb_image = Image.new('RGB', pil_image.size, (0, 0, 0))
    rgb_image.paste(pil_image, mask=pil_image.split()[3])  # Use alpha as mask
    
    # Save the pre-API image for debugging
    timestamp = datetime.now().strftime("%H%M%S")
    debug_filename = f"debug_preapi_{timestamp}.png"
    rgb_image.save(debug_filename)
    print(f"Saved pre-API image to {debug_filename}")
    
    # Convert to base64
    buffered = BytesIO()
    rgb_image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    # Print the first and last few characters of base64 string
    print(f"Base64 string length: {len(img_str)}")
    print(f"Base64 string starts with: {img_str[:50]}...")
    print(f"Base64 string ends with: ...{img_str[-50:]}")
    
    return img_str

def get_background_image(clock_image_base64):
    with open('api_payload.json', 'r') as f:
        payload = json.load(f)
    
    payload["prompt"] = generate_random_prompt()
    payload["alwayson_scripts"]["controlnet"]["args"][0]["image"] = clock_image_base64
    
    print("\nSending request to Stable Diffusion API...")
    try:
        response = requests.post(API_URL, json=payload, timeout=30)
        if response.status_code == 200:
            print("Received response from API")
            image_data = base64.b64decode(response.json()['images'][0])
            image = Image.open(BytesIO(image_data))
            
            save_debug_image(image, "background")
            
            return image
        print(f"Error: API request failed with status code {response.status_code}")
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        print(f"Error: Could not connect to API server: {e}")
    except Exception as e:
        print(f"Error: Unexpected error during API request: {e}")
    return None

class BackgroundUpdater:
    def __init__(self):
        self.background = None
        self.lock = threading.Lock()
        self.last_attempt = 0
        self.is_updating = False
        self.update_thread = None
    
    def _do_update(self, clock_image_base64):
        """Internal method that runs in a separate thread to update the background"""
        try:
            new_bg = get_background_image(clock_image_base64)
            if new_bg:
                with self.lock:
                    self.background = new_bg
                    print(f"Background updated at {datetime.now().strftime('%H:%M:%S')}")
        finally:
            with self.lock:
                self.is_updating = False
                self.update_thread = None
    
    def update_background(self, clock_image_base64):
        current_time = time.time()
        with self.lock:
            if self.is_updating or (current_time - self.last_attempt) < 15:
                return
            self.is_updating = True
            self.last_attempt = current_time
            
            # Create and start a new thread for the update
            self.update_thread = threading.Thread(
                target=self._do_update,
                args=(clock_image_base64,)
            )
            self.update_thread.daemon = True  # Thread will be killed when main program exits
            self.update_thread.start()
    
    def get_background(self):
        with self.lock:
            return self.background
    
    def should_update(self):
        return time.time() - self.last_attempt >= 15

background_updater = BackgroundUpdater()

def save_debug_image(image, prefix):
    """Save a debug image with timestamp.
    
    Args:
        image: Either a pygame Surface or PIL Image
        prefix: String prefix for the filename (e.g., 'clockface' or 'background')
    """
    timestamp = datetime.now().strftime("%H%M%S")
    debug_filename = f"debug_{prefix}_{timestamp}.png"
    
    if isinstance(image, pygame.Surface):
        pygame.image.save(image, debug_filename)
    else:  # PIL Image
        image.save(debug_filename)
    
    print(f"Saved {prefix} to {debug_filename}")

def main():
    print("Starting clock application...")
    print(f"Will refresh background every 15 seconds")
    print(f"API endpoint: {API_URL}")
    
    clock = pygame.time.Clock()
    running = True
    
    # Force initial update
    now = datetime.now()
    hands_surface = draw_clock_hands(now.hour, now.minute)
    hands_base64 = surface_to_base64(hands_surface)
    background_updater.update_background(hands_base64)
    
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        
        # Get current time
        now = datetime.now()
        hours, minutes, seconds = now.hour, now.minute, now.second
        
        # Draw clock hands (for API only)
        if background_updater.should_update():
            hands_surface = draw_clock_hands(hours, minutes)
            hands_base64 = surface_to_base64(hands_surface)
            background_updater.update_background(hands_base64)
        
        # Clear screen with pure black
        screen.fill(BACKGROUND_COLOR)
        
        # Draw background if available
        background = background_updater.get_background()
        if background:
            mode = background.mode
            size = background.size
            data = background.tobytes()
            bg_surface = pygame.image.fromstring(data, size, mode)
            screen.blit(bg_surface, (0, 0))
        
        # Draw semi-transparent black overlay
        screen.blit(overlay_surface, (0, 0))
        
        # Draw seconds hand
        seconds_angle = math.radians(seconds * 360 / 60 - 90)
        seconds_length = CLOCK_RADIUS * 0.8
        seconds_end = (
            CENTER[0] + seconds_length * math.cos(seconds_angle),
            CENTER[1] + seconds_length * math.sin(seconds_angle)
        )
        pygame.draw.line(screen, RED, CENTER, seconds_end, 2)
        
        pygame.display.flip()
        clock.tick(30)

    pygame.quit()

if __name__ == "__main__":
    main() 