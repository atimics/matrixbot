"""
Replicate API Integration Client

Enhanced with JavaScript best practices including random image selection,
robust error handling, LoRA trigger words, and improved polling logic.
"""

import asyncio
import logging
import random
import time
from typing import List, Optional, Union

import httpx

logger = logging.getLogger(__name__)


class ReplicateClient:
    """
    Enhanced Replicate client with JavaScript best practices.

    Features:
    - Random image selection from arrays
    - LoRA trigger word enhancement
    - Robust polling with exponential backoff
    - Comprehensive error handling
    - Flexible model version support
    """

    def __init__(
        self,
        api_token: str,
        default_model: str = "black-forest-labs/flux-dev-lora",
        default_lora_weights_url: Optional[str] = None,
        default_lora_scale: Optional[float] = None,
        lora_trigger_word: Optional[str] = None,
        style: str = "",
    ):
        """
        Initialize Replicate client.

        Args:
            api_token: Replicate API token
            default_model: Default model to use for generation
            default_lora_weights_url: Default LoRA weights URL
            default_lora_scale: Default LoRA scale factor
            lora_trigger_word: Trigger word for LoRA models
            style: Default style to apply
        """
        self.api_token = api_token
        self.default_model = default_model
        self.default_lora_weights_url = default_lora_weights_url
        self.default_lora_scale = default_lora_scale
        self.lora_trigger_word = lora_trigger_word
        self.style = style
        self.base_url = "https://api.replicate.com/v1"

    async def generate_image(
        self,
        prompt: str,
        images: Optional[Union[List[str], str]] = None,
        aspect_ratio: str = "1:1",
        model_version: Optional[str] = None,
        lora_weights_url: Optional[str] = None,
        lora_scale: Optional[float] = None,
        num_outputs: int = 1,
        go_fast: bool = True,
        output_format: str = "png",
    ) -> Optional[str]:
        """
        Generate an image using Replicate API with JavaScript best practices.

        Args:
            prompt: Text description for image generation
            images: Image URL(s) - single string or list (one will be randomly selected if multiple)
            aspect_ratio: Desired aspect ratio (e.g., "1:1", "16:9", "4:3")
            model_version: Model version override
            lora_weights_url: LoRA weights URL override
            lora_scale: LoRA scale factor override
            num_outputs: Number of outputs to generate
            go_fast: Enable fast mode
            output_format: Output format (webp, png, jpg)

        Returns:
            URL of the generated image, or None if failed
        """
        if not self.api_token:
            logger.error("ReplicateClient: Missing API token")
            return None

        try:
            # Handle image selection (random from array like JavaScript version)
            selected_image = None
            if images:
                if isinstance(images, str):
                    selected_image = images
                elif isinstance(images, list) and len(images) > 0:
                    selected_image = random.choice(images)
                    logger.debug(
                        f"ReplicateClient: Randomly selected image from {len(images)} options"
                    )

            # Enhance prompt with LoRA trigger word (JavaScript pattern)
            enhanced_prompt = prompt
            if self.lora_trigger_word:
                enhanced_prompt = f"{self.lora_trigger_word} {prompt}"
                logger.debug(
                    f"ReplicateClient: Enhanced prompt with trigger word: {self.lora_trigger_word}"
                )

            # Prepare payload with full configuration
            payload = {
                "version": model_version or self.default_model,
                "input": {
                    "prompt": enhanced_prompt,
                    "aspect_ratio": aspect_ratio,
                    "num_outputs": num_outputs,
                    "go_fast": go_fast,
                    "output_format": output_format,
                },
            }

            # Add image if provided
            if selected_image:
                payload["input"]["image"] = selected_image

            # Add LoRA configuration
            if lora_weights_url or self.default_lora_weights_url:
                payload["input"]["lora_weights"] = (
                    lora_weights_url or self.default_lora_weights_url
                )

            if lora_scale is not None or self.default_lora_scale is not None:
                payload["input"]["lora_scale"] = lora_scale or self.default_lora_scale

            # Add style if configured
            if self.style:
                payload["input"]["style"] = self.style

            logger.debug(
                f"ReplicateClient: Starting generation with model {payload['version']}"
            )

            async with httpx.AsyncClient(timeout=300.0) as client:
                # Start prediction
                response = await client.post(
                    f"{self.base_url}/predictions",
                    json=payload,
                    headers={
                        "Authorization": f"Token {self.api_token}",
                        "Content-Type": "application/json",
                    },
                )

                if not response.is_success:
                    error_text = response.text
                    logger.error(
                        f"ReplicateClient: API error: {response.status_code} {error_text}"
                    )
                    return None

                prediction_data = response.json()
                prediction_id = prediction_data.get("id")

                if not prediction_id:
                    logger.error("ReplicateClient: No prediction ID returned")
                    return None

                logger.debug(f"ReplicateClient: Started prediction {prediction_id}")

                # Enhanced polling with exponential backoff (JavaScript style)
                prediction = prediction_data
                max_poll_time = 300  # 5 minutes
                initial_interval = 1.5  # Start with 1.5 seconds
                max_interval = 10.0  # Cap at 10 seconds
                backoff_factor = 1.2  # Gradual increase
                start_time = time.time()
                poll_interval = initial_interval

                while (
                    prediction.get("status") in ["starting", "processing"]
                    and time.time() - start_time < max_poll_time
                ):
                    await asyncio.sleep(poll_interval)

                    poll_response = await client.get(
                        f"{self.base_url}/predictions/{prediction_id}",
                        headers={"Authorization": f"Token {self.api_token}"},
                    )

                    if poll_response.is_success:
                        prediction = poll_response.json()
                        logger.debug(
                            f"ReplicateClient: Status {prediction.get('status')} after {time.time() - start_time:.1f}s"
                        )

                        # Gradually increase poll interval (JavaScript pattern)
                        poll_interval = min(
                            poll_interval * backoff_factor, max_interval
                        )
                    else:
                        logger.warning(
                            f"ReplicateClient: Poll request failed: {poll_response.status_code}"
                        )
                        break

                # Check final result
                if prediction.get("status") == "succeeded":
                    output = prediction.get("output")
                    if isinstance(output, list) and len(output) > 0:
                        result_url = output[0]
                        logger.debug(
                            f"ReplicateClient: Generation succeeded: {result_url}"
                        )
                        return result_url
                    else:
                        logger.error(
                            "ReplicateClient: No output in successful prediction"
                        )
                        return None
                else:
                    status = prediction.get("status", "unknown")
                    error_msg = prediction.get("error", "No error details")
                    logger.error(
                        f"ReplicateClient: Generation failed with status '{status}': {error_msg}"
                    )
                    return None

        except Exception as e:
            logger.error(f"ReplicateClient: Unexpected error: {e}")
            return None

    async def get_prediction_status(self, prediction_id: str) -> Optional[dict]:
        """
        Get the status of a specific prediction.

        Args:
            prediction_id: The prediction ID to check

        Returns:
            Prediction status dict or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/predictions/{prediction_id}",
                    headers={"Authorization": f"Token {self.api_token}"},
                )

                if response.is_success:
                    return response.json()
                else:
                    logger.error(
                        f"ReplicateClient: Failed to get prediction status: {response.status_code}"
                    )
                    return None

        except Exception as e:
            logger.error(f"ReplicateClient: Error getting prediction status: {e}")
            return None
