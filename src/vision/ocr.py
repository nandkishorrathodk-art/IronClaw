"""
OCR engines for Ironclaw
Multi-engine OCR with Tesseract, PaddleOCR, and GPT-4V fallback
"""
import time
from typing import List, Dict, Optional, Tuple
from enum import Enum
import numpy as np
from PIL import Image
import cv2

from src.utils.logging import get_logger
from src.config import settings

logger = get_logger(__name__)


class OCREngine(Enum):
    """Available OCR engines."""
    TESSERACT = "tesseract"
    PADDLE = "paddle"
    GPT4V = "gpt4v"
    AUTO = "auto"  # Automatic selection based on confidence


class OCRResult:
    """OCR result with text and confidence."""
    
    def __init__(
        self,
        text: str,
        confidence: float,
        engine: str,
        bounding_boxes: Optional[List[Dict]] = None,
        language: str = "eng"
    ):
        self.text = text
        self.confidence = confidence
        self.engine = engine
        self.bounding_boxes = bounding_boxes or []
        self.language = language
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "text": self.text,
            "confidence": self.confidence,
            "engine": self.engine,
            "bounding_boxes": self.bounding_boxes,
            "language": self.language,
        }


class TesseractOCR:
    """Tesseract OCR engine."""
    
    def __init__(self, language: str = "eng"):
        """
        Initialize Tesseract OCR.
        
        Args:
            language: Language code (eng, spa, fra, deu, etc.)
        """
        self.language = language
        try:
            import pytesseract
            self.pytesseract = pytesseract
            logger.info(f"Initialized Tesseract OCR with language: {language}")
        except ImportError:
            logger.warning("pytesseract not installed, Tesseract OCR unavailable")
            self.pytesseract = None
    
    def preprocess_image(self, img: Image.Image) -> Image.Image:
        """
        Preprocess image for better OCR accuracy.
        
        Args:
            img: PIL Image
        
        Returns:
            Preprocessed PIL Image
        """
        # Convert to grayscale
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        
        # Denoise
        img_cv = cv2.fastNlMeansDenoising(img_cv)
        
        # Binarize (Otsu's thresholding)
        _, img_cv = cv2.threshold(img_cv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Deskew (if needed)
        # coords = np.column_stack(np.where(img_cv > 0))
        # angle = cv2.minAreaRect(coords)[-1]
        # if angle < -45:
        #     angle = -(90 + angle)
        # else:
        #     angle = -angle
        # if abs(angle) > 0.5:
        #     (h, w) = img_cv.shape[:2]
        #     center = (w // 2, h // 2)
        #     M = cv2.getRotationMatrix2D(center, angle, 1.0)
        #     img_cv = cv2.warpAffine(img_cv, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        
        return Image.fromarray(img_cv)
    
    def extract_text(
        self,
        img: Image.Image,
        preprocess: bool = True
    ) -> OCRResult:
        """
        Extract text from image using Tesseract.
        
        Args:
            img: PIL Image
            preprocess: Whether to preprocess image
        
        Returns:
            OCRResult with extracted text and confidence
        """
        if not self.pytesseract:
            raise RuntimeError("Tesseract not available")
        
        start_time = time.time()
        
        # Preprocess if requested
        if preprocess:
            img = self.preprocess_image(img)
        
        # Extract text with confidence
        data = self.pytesseract.image_to_data(
            img,
            lang=self.language,
            output_type=self.pytesseract.Output.DICT
        )
        
        # Filter out low-confidence results
        text_parts = []
        bboxes = []
        confidences = []
        
        for i in range(len(data['text'])):
            conf = int(data['conf'][i])
            text = data['text'][i].strip()
            
            if conf > 0 and text:
                text_parts.append(text)
                confidences.append(conf)
                
                bboxes.append({
                    "text": text,
                    "confidence": conf / 100.0,
                    "bbox": {
                        "x": data['left'][i],
                        "y": data['top'][i],
                        "width": data['width'][i],
                        "height": data['height'][i],
                    }
                })
        
        # Calculate average confidence
        avg_confidence = sum(confidences) / len(confidences) / 100.0 if confidences else 0.0
        
        # Combine text
        full_text = " ".join(text_parts)
        
        duration = (time.time() - start_time) * 1000
        logger.debug(f"Tesseract OCR completed in {duration:.2f}ms, confidence: {avg_confidence:.2f}")
        
        return OCRResult(
            text=full_text,
            confidence=avg_confidence,
            engine="tesseract",
            bounding_boxes=bboxes,
            language=self.language
        )


class PaddleOCR:
    """PaddleOCR engine (better for handwriting and CJK)."""
    
    def __init__(self, language: str = "en"):
        """
        Initialize PaddleOCR.
        
        Args:
            language: Language code (en, ch, korean, japan, etc.)
        """
        self.language = language
        try:
            from paddleocr import PaddleOCR as POcr
            self.paddle = POcr(
                use_angle_cls=True,
                lang=language,
                show_log=False
            )
            logger.info(f"Initialized PaddleOCR with language: {language}")
        except ImportError:
            logger.warning("paddleocr not installed, PaddleOCR unavailable")
            self.paddle = None
    
    def extract_text(self, img: Image.Image) -> OCRResult:
        """
        Extract text from image using PaddleOCR.
        
        Args:
            img: PIL Image
        
        Returns:
            OCRResult with extracted text and confidence
        """
        if not self.paddle:
            raise RuntimeError("PaddleOCR not available")
        
        start_time = time.time()
        
        # Convert to numpy array
        img_np = np.array(img)
        
        # Run OCR
        result = self.paddle.ocr(img_np, cls=True)
        
        # Parse results
        text_parts = []
        bboxes = []
        confidences = []
        
        if result and result[0]:
            for line in result[0]:
                bbox, (text, conf) = line
                text_parts.append(text)
                confidences.append(conf)
                
                # Convert bbox to our format
                x_coords = [p[0] for p in bbox]
                y_coords = [p[1] for p in bbox]
                bboxes.append({
                    "text": text,
                    "confidence": conf,
                    "bbox": {
                        "x": int(min(x_coords)),
                        "y": int(min(y_coords)),
                        "width": int(max(x_coords) - min(x_coords)),
                        "height": int(max(y_coords) - min(y_coords)),
                    }
                })
        
        # Calculate average confidence
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        # Combine text
        full_text = " ".join(text_parts)
        
        duration = (time.time() - start_time) * 1000
        logger.debug(f"PaddleOCR completed in {duration:.2f}ms, confidence: {avg_confidence:.2f}")
        
        return OCRResult(
            text=full_text,
            confidence=avg_confidence,
            engine="paddle",
            bounding_boxes=bboxes,
            language=self.language
        )


class GPT4VisionOCR:
    """GPT-4 Vision OCR (fallback for hard-to-read text)."""
    
    def __init__(self):
        """Initialize GPT-4 Vision OCR."""
        from src.cognitive.llm.openai_client import OpenAIClient
        self.client = OpenAIClient()
        logger.info("Initialized GPT-4 Vision OCR")
    
    async def extract_text(self, img: Image.Image) -> OCRResult:
        """
        Extract text from image using GPT-4 Vision.
        
        Args:
            img: PIL Image
        
        Returns:
            OCRResult with extracted text
        """
        from src.vision.capture import ScreenCapture
        
        start_time = time.time()
        
        # Convert image to base64
        capture = ScreenCapture()
        img_base64 = capture.image_to_base64(img)
        
        # Create prompt for OCR
        prompt = """Extract all visible text from this image. 
        Return ONLY the text, preserving line breaks and formatting as much as possible.
        If no text is visible, return an empty string."""
        
        # Call GPT-4V
        response = await self.client.vision_completion(
            prompt=prompt,
            image_base64=img_base64
        )
        
        text = response.get("content", "")
        
        duration = (time.time() - start_time) * 1000
        logger.debug(f"GPT-4V OCR completed in {duration:.2f}ms")
        
        return OCRResult(
            text=text,
            confidence=0.95,  # GPT-4V is generally very accurate
            engine="gpt4v",
            language="auto"
        )


class MultiEngineOCR:
    """Multi-engine OCR with confidence-based selection."""
    
    def __init__(self, language: str = "eng"):
        """
        Initialize multi-engine OCR.
        
        Args:
            language: Language code
        """
        self.language = language
        self.tesseract = TesseractOCR(language=language)
        
        # Map language codes
        paddle_lang = "en" if language == "eng" else language
        self.paddle = PaddleOCR(language=paddle_lang)
        
        self.gpt4v = GPT4VisionOCR()
        logger.info(f"Initialized multi-engine OCR with language: {language}")
    
    async def extract_text(
        self,
        img: Image.Image,
        engine: OCREngine = OCREngine.AUTO,
        min_confidence: float = 0.7
    ) -> OCRResult:
        """
        Extract text using specified or best engine.
        
        Args:
            img: PIL Image
            engine: OCR engine to use (or AUTO for automatic selection)
            min_confidence: Minimum confidence threshold for fallback
        
        Returns:
            OCRResult with best text extraction
        """
        if engine == OCREngine.TESSERACT:
            return self.tesseract.extract_text(img)
        elif engine == OCREngine.PADDLE:
            return self.paddle.extract_text(img)
        elif engine == OCREngine.GPT4V:
            return await self.gpt4v.extract_text(img)
        
        # AUTO mode: try engines in order, use best result
        results = []
        
        # Try Tesseract first (fastest)
        try:
            result = self.tesseract.extract_text(img)
            results.append(result)
            
            if result.confidence >= min_confidence:
                return result
        except Exception as e:
            logger.warning(f"Tesseract OCR failed: {e}")
        
        # Try PaddleOCR if Tesseract confidence is low
        try:
            result = self.paddle.extract_text(img)
            results.append(result)
            
            if result.confidence >= min_confidence:
                return result
        except Exception as e:
            logger.warning(f"PaddleOCR failed: {e}")
        
        # Fallback to GPT-4V if both failed or low confidence
        try:
            result = await self.gpt4v.extract_text(img)
            results.append(result)
            return result
        except Exception as e:
            logger.error(f"GPT-4V OCR failed: {e}")
        
        # Return best result from what we have
        if results:
            return max(results, key=lambda r: r.confidence)
        
        # No results
        return OCRResult(
            text="",
            confidence=0.0,
            engine="none",
            language=self.language
        )
