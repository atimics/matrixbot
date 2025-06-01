"""
Replicate API Integration Client

This module provides integration with Replicate's API for AI-powered image generation.
Supports SDXL models and LoRA fine-tuning for custom art styles.
"""

import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class ReplicateClient:
    """Client for interacting with Replicate's image generation API."""
    
    def __init__(
        self, 
        api_token: str, 
        default_model: str = "stability-ai/sdxl", 
        default_lora_weights_url: Optional[str] = None,
        default_lora_scale: Optional[float] = None
    ):
        """
        Initialize Replicate client.
        
        Args:
            api_token: Replicate API token
            default_model: Default model to use for generation
            default_lora_weights_url: Default LoRA weights URL
            default_lora_scale: Default LoRA scale factor
        """
        self.api_token = api_token
        self.default_model = default_model
        self.default_lora_weights_url = default_lora_weights_url
        self.default_lora_scale = default_lora_scale
        self.base_url = "https://api.replicate.com/v1"
        
    async def generate_image(
        self, 
        prompt: str, 
        image_url: Optional[str] = None,
        aspect_ratio: str = "1:1",
        model_version: Optional[str] = None,
        lora_weights_url: Optional[str] = None,
        lora_scale: Optional[float] = None
    ) -> Optional[str]:
        """
        Generate an image using Replicate API.
        
        Args:
            prompt: Text description for image generation
            image_url: Optional input image URL for img2img
            aspect_ratio: Aspect ratio for the generated image
            model_version: Specific model version to use
            lora_weights_url: LoRA weights URL for style fine-tuning
            lora_scale: LoRA scale factor (0.0 to 1.0)
            
        Returns:
            URL of the generated image or None if failed
        """
        try:
            # Use defaults if not specified
            if lora_weights_url is None:
                lora_weights_url = self.default_lora_weights_url
            if lora_scale is None:
                lora_scale = self.default_lora_scale
                
            # Prepare input parameters
            input_data = {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "output_format": "png",
                "output_quality": 90
            }
            
            # Add optional parameters
            if image_url:
                input_data["image"] = image_url
            if lora_weights_url:
                input_data["lora_weights"] = lora_weights_url
            if lora_scale is not None:
                input_data["lora_scale"] = lora_scale
                
            # Create prediction
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {
                    "Authorization": f"Token {self.api_token}",
                    "Content-Type": "application/json"
                }
                
                prediction_data = {
                    "version": model_version or self.default_model,
                    "input": input_data
                }
                
                response = await client.post(
                    f"{self.base_url}/predictions",
                    headers=headers,
                    json=prediction_data
                )
                response.raise_for_status()
                prediction = response.json()
                prediction_id = prediction["id"]
                
                logger.info(f"ReplicateClient: Started prediction {prediction_id}")
                
                # Poll for completion
                return await self._wait_for_prediction(client, headers, prediction_id)
                
        except Exception as e:
            logger.error(f"ReplicateClient: Image generation failed: {e}")
            return None
    
    async def _wait_for_prediction(
        self, 
        client: httpx.AsyncClient, 
        headers: dict, 
        prediction_id: str,
        max_wait_time: int = 300  # 5 minutes
    ) -> Optional[str]:
        """
        Wait for a prediction to complete and return the result URL.
        
        Args:
            client: HTTP client instance
            headers: Request headers
            prediction_id: Prediction ID to check
            max_wait_time: Maximum time to wait in seconds
            
        Returns:
            URL of generated image or None if failed/timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            try:
                response = await client.get(
                    f"{self.base_url}/predictions/{prediction_id}",
                    headers=headers
                )
                response.raise_for_status()
                prediction = response.json()
                
                status = prediction["status"]
                
                if status == "succeeded":
                    output = prediction.get("output")
                    if output and isinstance(output, list) and len(output) > 0:
                        image_url = output[0]
                        logger.info(f"ReplicateClient: Prediction {prediction_id} completed: {image_url}")
                        return image_url
                    else:
                        logger.error(f"ReplicateClient: Prediction {prediction_id} succeeded but no output")
                        return None
                        
                elif status == "failed":
                    error = prediction.get("error", "Unknown error")
                    logger.error(f"ReplicateClient: Prediction {prediction_id} failed: {error}")
                    return None
                    
                elif status in ["starting", "processing"]:
                    logger.debug(f"ReplicateClient: Prediction {prediction_id} status: {status}")
                    await asyncio.sleep(2)  # Poll every 2 seconds
                    
                else:
                    logger.warning(f"ReplicateClient: Unknown status {status} for prediction {prediction_id}")
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"ReplicateClient: Error checking prediction {prediction_id}: {e}")
                await asyncio.sleep(5)
                
        logger.error(f"ReplicateClient: Prediction {prediction_id} timed out after {max_wait_time}s")
        return None
