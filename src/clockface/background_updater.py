import time
import json
import base64
import torch
from io import BytesIO
from PIL import Image
from datetime import datetime
import threading
from diffusers import AutoencoderKL, ControlNetModel, StableDiffusionControlNetPipeline, DPMSolverMultistepScheduler
from diffusers.utils import load_image
from .prompt_generator import PromptGenerator
from ..utils import save_debug_image
from ..config import Config

class BackgroundUpdater:
    def __init__(self, debug=False):
        self.config = Config()
        self.debug = debug
        self.surface_manager = None
        self.current_color = (255, 255, 255, self.config.clock['overlay_opacity'])  # Default color
        self.previous_color = None
        self.transition_start = 0
        self.transition_duration = self.config.animation['transition_duration']
        self.update_interval = self.config.animation['background_update_interval']
        self.lock = threading.Lock()
        self.last_attempt = 0
        self.is_updating = False
        self.update_thread = None
        self.prompt_generator = PromptGenerator()
        
        # Initialize Diffusers pipeline
        self._initialize_pipeline()
    
    def _initialize_pipeline(self):
        """Initialize the Stable Diffusion pipeline with ControlNet"""
        if self.debug:
            print("Initializing Stable Diffusion pipeline...")
        
        # Load VAE
        vae = AutoencoderKL.from_single_file(
            self.config.api['models']['vae'],
            torch_dtype=torch.float16
        ).to('cuda')
        
        # Load ControlNet
        controlnet = ControlNetModel.from_single_file(
            self.config.api['models']['controlnet'],
            torch_dtype=torch.float16
        ).to('cuda')
        
        # Load main model
        self.pipe = StableDiffusionControlNetPipeline.from_single_file(
            self.config.api['models']['base'],
            controlnet=controlnet,
            torch_dtype=torch.float16,
            safety_checker=None,
            vae=vae
        ).to('cuda')
        
        # Set up scheduler
        scheduler = DPMSolverMultistepScheduler.from_config(
            self.pipe.scheduler.config,
            use_karras_sigmas=True
        )
        self.pipe.scheduler = scheduler
        
        if self.debug:
            print("Pipeline initialized successfully")
    
    def set_surface_manager(self, surface_manager):
        """Set the surface manager instance"""
        self.surface_manager = surface_manager
    
    def _extract_dominant_color(self, pil_image):
        """Extract the brightest color from the image (likely the clock hands/markers)"""
        # Convert to RGB if not already
        rgb_image = pil_image.convert('RGB')
        # Resize to speed up processing
        rgb_image.thumbnail((100, 100))
        
        # Get pixel data
        pixels = list(rgb_image.getdata())
        
        # Calculate brightness for each pixel and find the brightest one
        brightest_pixel = max(pixels, key=lambda p: sum(p))
        
        # Make it transparent according to config
        return (*brightest_pixel, self.config.clock['overlay_opacity'])
    
    def _get_background_image(self, clock_image_base64):
        """Generate a new background image using Stable Diffusion with ControlNet"""
        try:
            # Convert base64 to PIL Image
            image_data = base64.b64decode(clock_image_base64)
            source_image = Image.open(BytesIO(image_data))
            
            # Generate prompt
            prompt = self.prompt_generator.generate()
            
            if self.debug:
                print(f"\nGenerating image with prompt: {prompt}")
            
            # Get generation settings from config
            gen_config = self.config.api['generation']
            
            # Generate image
            image = self.pipe(
                prompt,
                image=source_image,
                height=self.config.api['height'],
                width=self.config.api['width'],
                negative_prompt="asian, (worst quality, low quality:1.4), watermark, signature, flower, facial marking, (women:1.2), (female:1.2), blue jeans, 3d, render, doll, plastic, blur, haze, monochrome, b&w, text, (ugly:1.2), unclear eyes, no arms, bad anatomy, cropped, censoring, asymmetric eyes, bad anatomy, bad proportions, cropped, cross-eyed, deformed, extra arms, extra fingers, extra limbs, fused fingers, jpeg artifacts, malformed, mangled hands, misshapen body, missing arms, missing fingers, missing hands, missing legs, poorly drawn, tentacle finger, too many arms, too many fingers, (worst quality, low quality:1.4), watermark, signature,illustration,painting, anime,cartoon",
                controlnet_conditioning_scale=gen_config['controlnet_conditioning_scale'],
                num_inference_steps=gen_config['num_inference_steps'],
                guidance_scale=gen_config['guidance_scale'],
                control_guidance_start=gen_config['control_guidance_start'],
                control_guidance_end=gen_config['control_guidance_end'],
            ).images[0]
            
            if self.debug:
                save_debug_image(image, "background")
                print("Image generated successfully")
            
            return image
            
        except Exception as e:
            print(f"Error: Failed to generate image: {e}")
            return None
    
    def _do_update(self, clock_image_base64):
        """Internal method that runs in a separate thread to update the background"""
        try:
            new_bg = self._get_background_image(clock_image_base64)
            if new_bg:
                with self.lock:
                    # Store the current color as previous for transition
                    self.previous_color = self.current_color
                    self.current_color = self._extract_dominant_color(new_bg)
                    
                    # Update background in surface manager
                    if self.surface_manager:
                        self.surface_manager.update_background(new_bg, self.transition_duration)
                    
                    if self.debug:
                        print(f"Background updated at {datetime.now().strftime('%H:%M:%S')}")
                        print(f"New brightest color: RGB{self.current_color[:3]} (15% opacity)")
        finally:
            with self.lock:
                self.is_updating = False
                self.update_thread = None
    
    def _interpolate_color(self, color1, color2, progress):
        """Interpolate between two colors"""
        if not color1 or not color2:
            return color2 or color1
        return tuple(
            int(c1 + (c2 - c1) * progress)
            for c1, c2 in zip(color1, color2)
        )
    
    def get_dominant_color(self):
        """Get the current dominant color with transition"""
        with self.lock:
            if not self.previous_color:
                return self.current_color
            
            # Calculate transition progress
            progress = min(1.0, (time.time() - self.transition_start) / self.transition_duration)
            
            # Interpolate between previous and current color
            return self._interpolate_color(self.previous_color, self.current_color, progress)
    
    def update_background(self, clock_image_base64):
        """Start a background update if conditions are met"""
        current_time = time.time()
        with self.lock:
            if self.is_updating or (current_time - self.last_attempt) < self.update_interval:
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
    
    def should_update(self):
        """Check if it's time for a background update"""
        return time.time() - self.last_attempt >= self.update_interval 