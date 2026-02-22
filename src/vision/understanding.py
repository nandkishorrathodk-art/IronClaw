"""
Visual understanding with AI for Ironclaw
GPT-4 Vision for scene understanding and visual question answering
"""
from typing import Dict, Optional, List
from PIL import Image

from src.utils.logging import get_logger
from src.vision.capture import ScreenCapture

logger = get_logger(__name__)


class VisualUnderstanding:
    """Visual understanding using GPT-4 Vision."""
    
    def __init__(self):
        """Initialize visual understanding."""
        from src.cognitive.llm.openai_client import OpenAIClient
        self.client = OpenAIClient()
        self.capture = ScreenCapture()
        logger.info("Initialized visual understanding")
    
    async def describe_image(
        self,
        img: Image.Image,
        detail_level: str = "medium"
    ) -> str:
        """
        Generate description of image.
        
        Args:
            img: PIL Image
            detail_level: Detail level (low, medium, high)
        
        Returns:
            Text description of the image
        """
        img_base64 = self.capture.image_to_base64(img)
        
        prompt = """Describe what you see in this image in detail. 
        Include information about:
        - Main objects and subjects
        - Scene setting and environment
        - Text visible in the image
        - Colors and visual style
        - Any notable details or context"""
        
        response = await self.client.vision_completion(
            prompt=prompt,
            image_base64=img_base64,
            detail_level=detail_level
        )
        
        description = response.get("content", "")
        logger.debug(f"Generated image description: {description[:100]}...")
        
        return description
    
    async def answer_question(
        self,
        img: Image.Image,
        question: str
    ) -> str:
        """
        Answer question about image.
        
        Args:
            img: PIL Image
            question: Question to answer
        
        Returns:
            Answer to the question
        """
        img_base64 = self.capture.image_to_base64(img)
        
        response = await self.client.vision_completion(
            prompt=question,
            image_base64=img_base64
        )
        
        answer = response.get("content", "")
        logger.debug(f"Answered question: {question[:50]}... -> {answer[:100]}...")
        
        return answer
    
    async def extract_structured_data(
        self,
        img: Image.Image,
        schema: Dict
    ) -> Dict:
        """
        Extract structured data from image based on schema.
        
        Args:
            img: PIL Image
            schema: Dictionary defining the structure to extract
        
        Returns:
            Extracted data as dictionary
        """
        import json
        
        img_base64 = self.capture.image_to_base64(img)
        
        schema_str = json.dumps(schema, indent=2)
        
        prompt = f"""Extract information from this image according to the following schema:

{schema_str}

Return a valid JSON object matching this schema. Only include fields that are visible in the image.
If a field is not visible, omit it from the response."""
        
        response = await self.client.vision_completion(
            prompt=prompt,
            image_base64=img_base64
        )
        
        content = response.get("content", "{}")
        
        # Try to parse as JSON
        try:
            # Remove markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            logger.debug(f"Extracted structured data: {data}")
            return data
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON response: {content}")
            return {"raw_response": content}
    
    async def identify_ui_elements(
        self,
        img: Image.Image
    ) -> List[Dict]:
        """
        Identify UI elements in screenshot.
        
        Args:
            img: PIL Image (screenshot)
        
        Returns:
            List of identified UI elements
        """
        img_base64 = self.capture.image_to_base64(img)
        
        prompt = """Analyze this user interface screenshot and identify all visible UI elements.
        For each element, provide:
        - type: (button, textfield, label, checkbox, dropdown, etc.)
        - text: visible text on or near the element
        - approximate_location: rough position (top-left, center, bottom-right, etc.)
        - purpose: what the element appears to do
        
        Return as a JSON array of objects."""
        
        response = await self.client.vision_completion(
            prompt=prompt,
            image_base64=img_base64
        )
        
        content = response.get("content", "[]")
        
        # Try to parse as JSON
        try:
            import json
            
            # Remove markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            elements = json.loads(content)
            logger.debug(f"Identified {len(elements)} UI elements")
            return elements if isinstance(elements, list) else []
        except Exception as e:
            logger.warning(f"Failed to parse UI elements: {e}")
            return []
    
    async def detect_anomalies(
        self,
        img: Image.Image,
        reference_img: Optional[Image.Image] = None
    ) -> List[str]:
        """
        Detect visual anomalies or issues in image.
        
        Args:
            img: PIL Image to analyze
            reference_img: Optional reference image for comparison
        
        Returns:
            List of detected anomalies
        """
        img_base64 = self.capture.image_to_base64(img)
        
        if reference_img:
            ref_base64 = self.capture.image_to_base64(reference_img)
            prompt = """Compare these two images and identify any differences, anomalies, or issues.
            Report any visual bugs, misalignments, missing elements, or unexpected changes."""
            
            response = await self.client.vision_completion(
                prompt=prompt,
                image_base64=img_base64,
                additional_images=[ref_base64]
            )
        else:
            prompt = """Analyze this image for any visual anomalies, bugs, or issues.
            Look for:
            - UI elements that appear broken or misaligned
            - Text that is cut off or overlapping
            - Missing images or placeholders
            - Error messages or warnings
            - Unusual colors or artifacts
            
            List each anomaly you find."""
            
            response = await self.client.vision_completion(
                prompt=prompt,
                image_base64=img_base64
            )
        
        content = response.get("content", "")
        
        # Split into list of anomalies
        anomalies = [
            line.strip() 
            for line in content.split('\n') 
            if line.strip() and not line.strip().startswith('#')
        ]
        
        logger.debug(f"Detected {len(anomalies)} anomalies")
        return anomalies
    
    async def find_element_by_description(
        self,
        img: Image.Image,
        description: str
    ) -> Optional[Dict]:
        """
        Find UI element by natural language description.
        
        Args:
            img: PIL Image (screenshot)
            description: Natural language description of element
        
        Returns:
            Element information if found
        """
        img_base64 = self.capture.image_to_base64(img)
        
        prompt = f"""Find the UI element matching this description: "{description}"
        
        If found, return a JSON object with:
        - found: true
        - type: element type
        - text: visible text
        - approximate_position: rough position description
        - how_to_click: instructions on how to interact with it
        
        If not found, return: {{"found": false}}"""
        
        response = await self.client.vision_completion(
            prompt=prompt,
            image_base64=img_base64
        )
        
        content = response.get("content", "{}")
        
        try:
            import json
            
            # Remove markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
            
            if result.get("found"):
                logger.debug(f"Found element: {result}")
                return result
            else:
                logger.debug(f"Element not found: {description}")
                return None
        except Exception as e:
            logger.warning(f"Failed to parse element search result: {e}")
            return None
