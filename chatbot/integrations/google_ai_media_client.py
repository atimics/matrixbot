import asyncio
import base64
import io
import logging
import os
import time # Kept for Veo polling timeout
from typing import Dict, List, Optional, Union # Kept for type hints

import httpx # Kept for Veo video downloads if URI is returned by SDK
from google import genai
from google.genai import types
from PIL import Image # For handling image data

logger = logging.getLogger(__name__)


class GoogleAIMediaClient:
    """
    Enhanced Google AI Media client.
    Uses the google-genai SDK for Gemini image generation and Veo video generation.
    """

    def __init__(
        self,
        api_key: str,
        default_gemini_image_model: str = "gemini-1.5-flash-latest",
        default_veo_video_model: str = "veo-2.0-generate-001",
    ):
        """
        Initialize Google AI Media client.

        Args:
            api_key: Google AI API key (for Gemini Developer API).
            default_gemini_image_model: Default Gemini model for image generation.
                                       Ensure this model supports image generation via generate_content.
            default_veo_video_model: Default Veo model for video generation.
        """
        self.api_key = api_key
        try:
            # Initialize the google-genai client for Gemini Developer API
            self.client = genai.Client(api_key=self.api_key)
        except Exception as e:
            logger.error(f"Failed to initialize genai.Client: {e}. Ensure API key is valid or environment is configured.")
            raise

        self.default_gemini_image_model = default_gemini_image_model
        self.default_veo_video_model = default_veo_video_model

        self.browser_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "video/mp4,video/webm,video/*,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "video",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "cross-site",
        }
        
        self.gemini_safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            ),
        ]

    async def generate_image_gemini(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        temperature: float = 0.9,
    ) -> Optional[bytes]:
        """
        Generate an image using a Gemini model with image generation capabilities.
        Note: Ensure 'default_gemini_image_model' supports image generation.
              Models like "gemini-1.5-flash-latest" are suitable if enabled for image gen.

        Args:
            prompt: Text description for image generation.
            aspect_ratio: Desired aspect ratio (e.g., "1:1", "16:9"). Included in the prompt.
            temperature: Generation temperature (0.0-1.0).

        Returns:
            Image bytes or None if failed.
        """
        enhanced_prompt = (
            f"{prompt}\n\n"
            f"Generate an image with an aspect ratio of {aspect_ratio}. "
            f"Only respond with the image, no accompanying text or description."
        )

        generation_config_obj = types.GenerateContentConfig(
            temperature=temperature,
            safety_settings=self.gemini_safety_settings,
        )

        try:
            response = await self.client.aio.models.generate_content(
                model=self.default_gemini_image_model,
                contents=[enhanced_prompt],
                generation_config=generation_config_obj,
            )

            for part in response.parts:
                if hasattr(part, "inline_data") and part.inline_data and \
                   hasattr(part.inline_data, "data") and part.inline_data.data:
                    return part.inline_data.data
            
            warning_message = "GoogleAIMediaClient: No image data found in Gemini response."
            if response.text: # `.text` concatenates text from all parts
                warning_message += f" Response text: {response.text}"
            logger.warning(warning_message)

            if response.prompt_feedback and response.prompt_feedback.block_reason:
                block_reason_msg = str(response.prompt_feedback.block_reason)
                if hasattr(response.prompt_feedback, 'block_reason_message') and response.prompt_feedback.block_reason_message:
                     block_reason_msg = response.prompt_feedback.block_reason_message
                logger.warning(f"GoogleAIMediaClient: Image generation may have been blocked. Reason: {block_reason_msg}")
            
            if response.candidates:
                for candidate in response.candidates:
                    if candidate.finish_reason not in (None, types.FinishReason.STOP, types.FinishReason.FINISH_REASON_UNSPECIFIED):
                        logger.warning(f"GoogleAIMediaClient: Gemini generation candidate finished with reason: {candidate.finish_reason} ({candidate.finish_message or ''})")
            return None

        except genai.errors.BlockedPromptError as e:
            logger.error(f"GoogleAIMediaClient: Gemini image generation blocked: {e}")
            return None
        except genai.errors.APIError as e: # Catch specific API errors from the SDK
            logger.error(f"GoogleAIMediaClient: Gemini image generation failed with APIError: {e}")
            return None
        except Exception as e: # Catch any other unexpected errors
            logger.exception(f"GoogleAIMediaClient: Unexpected error in Gemini image generation: {e}")
            return None

    async def compose_image_with_references(
        self,
        prompt: str,
        reference_images: List[Dict[str, str]], 
        aspect_ratio: str = "1:1",
    ) -> Optional[bytes]:
        """
        Generate a composed image using reference images with a Gemini vision model.
        Requires a model capable of multimodal input and image generation output.

        Args:
            prompt: Text description for the composition.
            reference_images: List of {"data": base64_string, "mimeType": mime_type}.
            aspect_ratio: Desired aspect ratio for the output.

        Returns:
            Composed image bytes or None if failed.
        """
        # Gemini 1.5 Pro can handle more, but let's keep a reasonable default advice.
        if not (1 <= len(reference_images) <= 16): 
            logger.warning(
                "GoogleAIMediaClient: Number of reference images is outside the typical 1-16 range."
            )
            # Not returning None, allow model to decide if it can handle it.

        content_parts: list[Union[str, Image.Image]] = []
        for img_ref in reference_images:
            try:
                img_bytes = base64.b64decode(img_ref["data"])
                pil_image = Image.open(io.BytesIO(img_bytes))
                content_parts.append(pil_image)
            except Exception as e:
                logger.error(f"GoogleAIMediaClient: Failed to decode/load reference image: {e}")
                return None
        
        enhanced_prompt = (
            f"{prompt}\n\n"
            f"Using the provided image(s) as references, generate a new composite image. "
            f"The new image should have an aspect ratio of {aspect_ratio}. "
            f"Only respond with the newly generated image, no accompanying text."
        )
        content_parts.append(enhanced_prompt)
        
        generation_config_obj = types.GenerateContentConfig(
            temperature=0.7, 
            safety_settings=self.gemini_safety_settings,
        )

        try:
            response = await self.client.aio.models.generate_content(
                model=self.default_gemini_image_model,
                contents=content_parts, # List can contain PIL.Image objects and strings
                generation_config=generation_config_obj
            )
            
            for part in response.parts:
                if hasattr(part, "inline_data") and part.inline_data and \
                   hasattr(part.inline_data, "data") and part.inline_data.data:
                    return part.inline_data.data

            warning_message = "GoogleAIMediaClient: No composed image data found in Gemini response."
            if response.text:
                warning_message += f" Response text: {response.text}"
            logger.warning(warning_message)

            if response.prompt_feedback and response.prompt_feedback.block_reason:
                block_reason_msg = str(response.prompt_feedback.block_reason)
                if hasattr(response.prompt_feedback, 'block_reason_message') and response.prompt_feedback.block_reason_message:
                     block_reason_msg = response.prompt_feedback.block_reason_message
                logger.warning(f"GoogleAIMediaClient: Image composition may have been blocked. Reason: {block_reason_msg}")

            if response.candidates:
                for candidate in response.candidates:
                    if candidate.finish_reason not in (None, types.FinishReason.STOP, types.FinishReason.FINISH_REASON_UNSPECIFIED):
                        logger.warning(f"GoogleAIMediaClient: Gemini composition candidate finished with reason: {candidate.finish_reason} ({candidate.finish_message or ''})")
            return None

        except genai.errors.BlockedPromptError as e:
            logger.error(f"GoogleAIMediaClient: Gemini image composition blocked: {e}")
            return None
        except genai.errors.APIError as e:
            logger.error(f"GoogleAIMediaClient: Gemini image composition failed with APIError: {e}")
            return None
        except Exception as e:
            logger.exception(f"GoogleAIMediaClient: Unexpected error in Gemini image composition: {e}")
            return None

    async def generate_video_veo(
        self,
        prompt: str,
        input_image_bytes: Optional[bytes] = None,
        input_mime_type: Optional[str] = None,
        aspect_ratio: str = "16:9",
        num_videos: int = 1,
        person_generation: str = "allow_adult",
        duration_seconds: float = 5.0,
        fps: int = 24,
    ) -> List[bytes]:
        """
        Generate videos using Google's Veo model (via google-genai SDK).
        Note: input_image_bytes for image-to-video is not directly supported by
              types.GenerateVideosConfig in current SDK examples. This is text-to-video.
        """
        if input_image_bytes:
            logger.warning(
                "GoogleAIMediaClient: `input_image_bytes` for Veo image-to-video is not directly "
                "supported by the SDK's `generate_videos` method in this implementation. "
                "Proceeding with text-to-video."
            )

        pg_enum_map = {
            "allow_adult": types.PersonGeneration.ALLOW_ADULT,
            "allow_all": types.PersonGeneration.ALLOW_ALL,
            "dont_allow": types.PersonGeneration.DONT_ALLOW,
        }
        sdk_person_generation = pg_enum_map.get(person_generation.lower(), types.PersonGeneration.ALLOW_ADULT)

        video_gen_config = types.GenerateVideosConfig(
            number_of_videos=num_videos,
            person_generation=sdk_person_generation,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            fps=fps,
        )

        try:
            logger.info(f"GoogleAIMediaClient: Starting Veo video generation for prompt: '{prompt}' with model {self.default_veo_video_model}")
            
            # This returns an AsyncOperation object
            operation = await self.client.aio.models.generate_videos(
                model=self.default_veo_video_model,
                prompt=prompt,
                config=video_gen_config,
            )
            
            operation_name = str(operation.name) if hasattr(operation, 'name') else "unknown_veo_operation"
            logger.info(f"GoogleAIMediaClient: Veo video generation operation started: {operation_name}. Waiting for completion...")

            max_wait_seconds = 600  # 10 minutes timeout for the operation to complete
            op_result_payload = await asyncio.wait_for(operation.result(), timeout=max_wait_seconds)
            
            # operation.result() raises an exception if the operation failed.
            # If we reach here, the operation was successful.
            # op_result_payload is likely types.GenerateVideosResponse

            video_bytes_list = []
            if op_result_payload and hasattr(op_result_payload, 'generated_videos') and op_result_payload.generated_videos:
                for gen_video_info in op_result_payload.generated_videos: # types.GeneratedVideo
                    if hasattr(gen_video_info, 'video') and gen_video_info.video: # types.Video
                        video_detail = gen_video_info.video
                        if video_detail.video_bytes:
                            video_bytes_list.append(video_detail.video_bytes)
                            logger.info(f"GoogleAIMediaClient: Veo video generated ({len(video_detail.video_bytes)} bytes).")
                        elif video_detail.uri:
                            logger.info(f"GoogleAIMediaClient: Veo video generated, URI: {video_detail.uri}. Attempting download.")
                            async with httpx.AsyncClient(timeout=300.0) as http_client:
                                try:
                                    download_url = video_detail.uri
                                    # Minimal heuristic for adding API key, GCS URIs (gs://) or fully pre-signed URLs won't need this.
                                    # This might be unnecessary if SDK returns directly downloadable URIs.
                                    if "generativelanguage.googleapis.com" in download_url and "key=" not in download_url:
                                         download_url = f"{download_url}{'&' if '?' in download_url else '?'}key={self.api_key}"

                                    dl_response = await http_client.get(download_url, headers=self.browser_headers)
                                    dl_response.raise_for_status()
                                    video_bytes_list.append(dl_response.content)
                                    logger.info(f"GoogleAIMediaClient: Downloaded Veo video from {download_url} ({len(dl_response.content)} bytes).")
                                except httpx.HTTPStatusError as e_dl_http:
                                    logger.error(f"GoogleAIMediaClient: Failed to download Veo video from {video_detail.uri}. Status: {e_dl_http.response.status_code}, Response: {e_dl_http.response.text}")
                                except Exception as e_dl:
                                    logger.exception(f"GoogleAIMediaClient: Error downloading Veo video from {video_detail.uri}: {e_dl}")
                        else:
                            logger.warning("GoogleAIMediaClient: Generated Veo video info does not contain direct bytes or URI.")
                    else:
                        logger.warning("GoogleAIMediaClient: Generated video info object is missing 'video' attribute or it's empty.")
                return video_bytes_list
            else:
                logger.warning(f"GoogleAIMediaClient: Veo operation {operation_name} completed but no 'generated_videos' found in result.")
                return []

        except asyncio.TimeoutError:
            logger.error(f"GoogleAIMediaClient: Veo video generation timed out after {max_wait_seconds}s for operation {operation_name}")
            # Log final status if possible
            try:
                if not operation.done(): # Check if operation itself also thinks it's not done
                    logger.info(f"Attempting to get latest status for timed-out operation {operation_name}")
                    updated_op = await self.client.aio.operations.get(name=operation_name)
                    if updated_op.error:
                        error_message = updated_op.error.message if hasattr(updated_op.error, 'message') else str(updated_op.error)
                        logger.error(f"Timed-out Veo operation {operation_name} ended with error: {error_message}")
                    elif updated_op.done():
                         logger.info(f"Timed-out Veo operation {operation_name} was found to be completed after timeout check.")
            except Exception as final_status_e:
                logger.warning(f"Could not fetch final status for timed-out operation {operation_name}: {final_status_e}")
            return []
        except genai.errors.APIError as e: # Errors from operation.result() or initial call
            logger.error(f"GoogleAIMediaClient: Veo video generation failed for operation {operation_name} with APIError: {e}")
            return []
        except Exception as e:
            logger.exception(f"GoogleAIMediaClient: Unexpected error during Veo video generation (operation {operation_name}): {e}")
            return []

async def main():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Please set the GOOGLE_API_KEY environment variable.")
        return

    try:
        client = GoogleAIMediaClient(
            api_key=api_key,
            default_gemini_image_model="gemini-1.5-flash-latest",
            default_veo_video_model="veo-2.0-generate-001" # Verify this model name
        )
    except Exception as e:
        print(f"Failed to create GoogleAIMediaClient: {e}")
        return

    # --- Gemini Image Generation Example ---
    print("\n--- Testing Gemini Image Generation ---")
    image_prompt = "A vibrant coral reef teeming with alien marine life, underwater fantasy."
    generated_image_bytes = await client.generate_image_gemini(prompt=image_prompt, aspect_ratio="16:9")
    if generated_image_bytes:
        try:
            with open("generated_gemini_image.png", "wb") as f: f.write(generated_image_bytes)
            print("Image generated by Gemini and saved to generated_gemini_image.png")
        except IOError as e: print(f"Error saving Gemini image: {e}")
    else:
        print("Failed to generate image with Gemini.")

    # --- Gemini Image Composition Example ---
    print("\n--- Testing Gemini Image Composition ---")
    def create_dummy_base64_image(width, height, color="grey") -> str:
        img = Image.new("RGB", (width, height), color=color)
        buffered = io.BytesIO(); img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    reference_images_data = [
        {"data": create_dummy_base64_image(100, 100, "cyan"), "mimeType": "image/png"},
        {"data": create_dummy_base64_image(120, 150, "magenta"), "mimeType": "image/png"},
    ]
    composition_prompt = "Create an abstract artwork blending these two colored shapes, perhaps with a futuristic geometric feel."
    composed_image_bytes = await client.compose_image_with_references(
        prompt=composition_prompt, reference_images=reference_images_data, aspect_ratio="1:1"
    )
    if composed_image_bytes:
        try:
            with open("composed_gemini_image.png", "wb") as f: f.write(composed_image_bytes)
            print("Image composed by Gemini and saved to composed_gemini_image.png")
        except IOError as e: print(f"Error saving composed Gemini image: {e}")
    else:
        print("Failed to compose image with Gemini.")

    # --- Veo Video Generation Example ---
    print("\n--- Testing Veo Video Generation ---")
    video_prompt = "A humorous animation of a robot trying to bake a cake and failing spectacularly."
    generated_videos = await client.generate_video_veo(
        prompt=video_prompt, aspect_ratio="16:9", num_videos=1, duration_seconds=4, fps=24
    )
    if generated_videos:
        for i, video_bytes in enumerate(generated_videos):
            try:
                with open(f"generated_veo_video_{i}.mp4", "wb") as f: f.write(video_bytes)
                print(f"Video generated by Veo and saved to generated_veo_video_{i}.mp4")
            except IOError as e: print(f"Error saving Veo video: {e}")
    else:
        print("Failed to generate video with Veo.")
    print("\nNote: Veo generation is highly dependent on API access, correct model names, and quotas.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    print("Running Google AI Media Client examples...")
    print("Ensure GOOGLE_API_KEY is set and required libraries (google-genai, Pillow, httpx) are installed.")
    print("You can install them with: pip install google-genai Pillow httpx\n")
    asyncio.run(main())