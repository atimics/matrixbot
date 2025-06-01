"""
Google AI Media Generation Client

This module provides integration with Google AI services for image and video generation,
including Gemini for image generation and Veo for video generation. Enhanced with 
JavaScript best practices including browser headers, retry logic, and robust polling.
"""

import asyncio
import base64
import io
import logging
import os
import random
import tempfile
import time
from typing import Dict, List, Optional, Tuple, Union

import httpx

logger = logging.getLogger(__name__)


class GoogleAIMediaClient:
    """
    Enhanced Google AI Media client with JavaScript best practices.
    
    Features:
    - Browser headers for downloads
    - Exponential backoff retry logic
    - Robust polling for long operations
    - Enhanced error handling
    - Rate limiting protection
    """
    
    def __init__(
        self, 
        api_key: str, 
        default_gemini_image_model: str = "gemini-2.0-flash-exp-image-generation",
        default_veo_video_model: str = "veo-2.0-generate-001"
    ):
        """
        Initialize Google AI Media client.
        
        Args:
            api_key: Google AI API key
            default_gemini_image_model: Default Gemini model for image generation
            default_veo_video_model: Default Veo model for video generation
        """
        self.api_key = api_key
        self.default_gemini_image_model = default_gemini_image_model
        self.default_veo_video_model = default_veo_video_model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        
        # Rate limiting tracking
        self.recent_requests = []
        self.rate_limit_per_minute = 10  # Conservative default
        self.rate_limit_per_day = 100    # Conservative default
        
        # Browser headers for downloads
        self.browser_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site'
        }
        
    async def _retry_with_backoff(
        self,
        operation_func,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        jitter: bool = True
    ):
        """
        Execute operation with exponential backoff retry logic.
        
        Args:
            operation_func: Async function to retry
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay between retries
            backoff_factor: Exponential backoff multiplier
            jitter: Add random jitter to delays
            
        Returns:
            Result from operation_func or None if all retries failed
        """
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return await operation_func(attempt)
            except Exception as e:
                last_exception = e
                logger.warning(f"GoogleAIMediaClient: Attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries - 1:
                    delay = initial_delay * (backoff_factor ** attempt)
                    if jitter:
                        delay *= (0.5 + random.random() * 0.5)  # Add 0-50% jitter
                    
                    logger.info(f"GoogleAIMediaClient: Retrying in {delay:.2f} seconds...")
                    await asyncio.sleep(delay)
        
        logger.error(f"GoogleAIMediaClient: Operation failed after {max_retries} attempts. Last error: {last_exception}")
        return None
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = time.time()
        
        # Filter recent requests within the last minute
        recent_requests = [req for req in self.recent_requests if now - req < 60]
        if len(recent_requests) >= self.rate_limit_per_minute:
            return False
        
        # Filter recent requests within the last day
        daily_requests = [req for req in self.recent_requests if now - req < 24 * 60 * 60]
        if len(daily_requests) >= self.rate_limit_per_day:
            return False
            
        return True
    
    def _record_request(self):
        """Record a new request for rate limiting."""
        self.recent_requests.append(time.time())
        # Keep only last day's requests
        cutoff = time.time() - 24 * 60 * 60
        self.recent_requests = [req for req in self.recent_requests if req > cutoff]
    
    async def generate_image_gemini(
        self, 
        prompt: str, 
        aspect_ratio: str = "1:1",
        temperature: float = 0.9,
        max_retries: int = 3
    ) -> Optional[bytes]:
        """
        Generate an image using Gemini's image generation model with enhanced retry logic.
        
        Args:
            prompt: Text description for image generation
            aspect_ratio: Desired aspect ratio (e.g., "1:1", "16:9", "4:3")
            temperature: Generation temperature (0.0-1.0)
            max_retries: Maximum retry attempts
            
        Returns:
            Image bytes or None if failed
        """
        if not self._check_rate_limit():
            logger.warning("GoogleAIMediaClient: Rate limit exceeded for image generation")
            return None
            
        # Enhance prompt with aspect ratio
        enhanced_prompt = f"{prompt}\nDesired aspect ratio: {aspect_ratio}\nOnly respond with an image."
        
        async def _generate_attempt(attempt: int) -> Optional[bytes]:
            self._record_request()
            
            # Add retry-specific enhancements to prompt
            retry_prompt = enhanced_prompt
            if attempt > 0:
                retry_prompt += f"\nDo not include any text. If you cannot generate an image, try again."
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "contents": [{
                        "role": "user",
                        "parts": [{"text": retry_prompt}]
                    }],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": 1000,
                        "topP": 0.95,
                        "topK": 40,
                        "responseModalities": ["text", "image"]
                    }
                }
                
                response = await client.post(
                    f"{self.base_url}/models/{self.default_gemini_image_model}:generateContent",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Look for image in response
                    for candidate in result.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            if "inlineData" in part:
                                image_data = part["inlineData"]["data"]
                                return base64.b64decode(image_data)
                    
                    raise Exception("No image found in response")
                else:
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
        
        return await self._retry_with_backoff(_generate_attempt, max_retries)
    
    async def compose_image_with_references(
        self,
        prompt: str,
        reference_images: List[Dict[str, str]],
        aspect_ratio: str = "1:1"
    ) -> Optional[bytes]:
        """
        Generate a composed image using reference images (avatar, location, items).
        
        Args:
            prompt: Text description for the composition
            reference_images: List of {"data": base64_string, "mimeType": mime_type, "label": description}
            aspect_ratio: Desired aspect ratio
            
        Returns:
            Composed image bytes or None if failed
        """
        if not self._check_rate_limit():
            logger.warning("GoogleAIMediaClient: Rate limit exceeded for image composition")
            return None
            
        if not reference_images or len(reference_images) > 3:
            logger.warning("GoogleAIMediaClient: Need 1-3 reference images for composition")
            return None
            
        try:
            self._record_request()
            
            # Build parts array with reference images and prompt
            parts = []
            
            # Add reference images
            for img in reference_images:
                parts.append({
                    "inline_data": {
                        "mime_type": img.get("mimeType", "image/png"),
                        "data": img["data"]
                    }
                })
            
            # Add enhanced text prompt
            enhanced_prompt = f"{prompt}\nCompose these elements together in aspect ratio {aspect_ratio}. Only respond with an image."
            parts.append({"text": enhanced_prompt})
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "contents": [{
                        "role": "user", 
                        "parts": parts
                    }],
                    "generationConfig": {
                        "temperature": 0.9,
                        "maxOutputTokens": 1000,
                        "topP": 0.95,
                        "topK": 40,
                        "responseModalities": ["text", "image"]
                    }
                }
                
                response = await client.post(
                    f"{self.base_url}/models/{self.default_gemini_image_model}:generateContent",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Extract image from response
                    for candidate in result.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            if "inlineData" in part:
                                image_data = part["inlineData"]["data"]
                                return base64.b64decode(image_data)
                                
                logger.warning("GoogleAIMediaClient: No composed image found in response")
                return None
                
        except Exception as e:
            logger.error(f"GoogleAIMediaClient: Image composition failed: {e}")
            return None
    
    async def generate_video_veo(
        self, 
        prompt: str, 
        input_image_bytes: Optional[bytes] = None,
        input_mime_type: Optional[str] = None,
        aspect_ratio: str = "16:9",
        num_videos: int = 1,
        person_generation: str = "allow_adult"
    ) -> List[bytes]:
        """
        Generate videos using Google's Veo model with polling for completion.
        
        Args:
            prompt: Text description for video generation
            input_image_bytes: Optional input image bytes as first frame
            input_mime_type: MIME type of input image (e.g., "image/png")
            aspect_ratio: Video aspect ratio
            num_videos: Number of videos to generate
            person_generation: Person generation policy
            
        Returns:
            List of video bytes (empty list if failed)
        """
        if not self._check_rate_limit():
            logger.warning("GoogleAIMediaClient: Rate limit exceeded for video generation")
            return []
            
        try:
            self._record_request()
            
            # Prepare generation config
            config = {
                "numberOfVideos": num_videos,
                "personGeneration": person_generation,
                "aspectRatio": aspect_ratio
            }
            
            # Prepare image parameter if provided
            image_param = None
            if input_image_bytes:
                image_base64 = base64.b64encode(input_image_bytes).decode('utf-8')
                image_param = {
                    "imageBytes": image_base64,
                    "mimeType": input_mime_type or "image/png"
                }
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                # Start video generation operation
                payload = {
                    "model": self.default_veo_video_model,
                    "prompt": prompt,
                    "config": config
                }
                
                if image_param:
                    payload["image"] = image_param
                
                response = await client.post(
                    f"{self.base_url}/models:generateVideos",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"GoogleAIMediaClient: Video generation start failed: {response.status_code} - {response.text}")
                    return []
                
                operation = response.json()
                operation_name = operation.get("name")
                
                if not operation_name:
                    logger.error("GoogleAIMediaClient: No operation name returned")
                    return []
                
                logger.info(f"GoogleAIMediaClient: Video generation started, polling operation: {operation_name}")
                
                # Poll for completion
                max_poll_time = 300  # 5 minutes
                poll_interval = 10   # 10 seconds
                start_time = time.time()
                
                while time.time() - start_time < max_poll_time:
                    await asyncio.sleep(poll_interval)
                    
                    poll_response = await client.get(
                        f"{self.base_url}/operations/{operation_name}",
                        headers={"Authorization": f"Bearer {self.api_key}"}
                    )
                    
                    if poll_response.status_code == 200:
                        operation_status = poll_response.json()
                        
                        if operation_status.get("done"):
                            # Operation completed
                            if "error" in operation_status:
                                logger.error(f"GoogleAIMediaClient: Video generation error: {operation_status['error']}")
                                return []
                            
                            response_data = operation_status.get("response", {})
                            generated_videos = response_data.get("generatedVideos", [])
                            
                            # Download videos
                            video_bytes_list = []
                            for video_info in generated_videos:
                                video_uri = video_info.get("video", {}).get("uri")
                                if video_uri:
                                    # Add API key to URI
                                    video_url = f"{video_uri}&key={self.api_key}"
                                    
                                    # Download video with browser headers
                                    download_response = await client.get(video_url, headers=self.browser_headers)
                                    if download_response.status_code == 200:
                                        video_bytes_list.append(download_response.content)
                                        logger.info(f"GoogleAIMediaClient: Downloaded video ({len(download_response.content)} bytes)")
                                    else:
                                        logger.warning(f"GoogleAIMediaClient: Failed to download video: {download_response.status_code}")
                            
                            return video_bytes_list
                        else:
                            logger.info(f"GoogleAIMediaClient: Video generation in progress... ({time.time() - start_time:.1f}s)")
                    else:
                        logger.warning(f"GoogleAIMediaClient: Poll failed: {poll_response.status_code}")
                
                logger.error("GoogleAIMediaClient: Video generation timed out")
                return []
                
        except Exception as e:
            logger.error(f"GoogleAIMediaClient: Video generation failed: {e}")
            return []
