"""
Object and element detection for Ironclaw
YOLO v8 object detection and UI element detection
"""
import time
from typing import List, Dict, Optional, Tuple
import numpy as np
from PIL import Image
import cv2

from src.utils.logging import get_logger

logger = get_logger(__name__)


class DetectionResult:
    """Detection result with bounding box and confidence."""
    
    def __init__(
        self,
        label: str,
        confidence: float,
        bbox: Dict[str, int],
        class_id: Optional[int] = None
    ):
        self.label = label
        self.confidence = confidence
        self.bbox = bbox  # {"x": int, "y": int, "width": int, "height": int}
        self.class_id = class_id
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "label": self.label,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "class_id": self.class_id,
        }
    
    def get_center(self) -> Tuple[int, int]:
        """Get center point of bounding box."""
        x = self.bbox["x"] + self.bbox["width"] // 2
        y = self.bbox["y"] + self.bbox["height"] // 2
        return (x, y)


class ObjectDetector:
    """YOLO v8 object detector."""
    
    def __init__(self, model_size: str = "nano", device: str = "cpu"):
        """
        Initialize YOLO v8 object detector.
        
        Args:
            model_size: Model size (nano, small, medium, large, xlarge)
            device: Device to run on (cpu, cuda, npu)
        """
        self.model_size = model_size
        self.device = device
        self.model = None
        
        try:
            from ultralytics import YOLO
            
            # Model size mapping
            model_map = {
                "nano": "yolov8n.pt",
                "small": "yolov8s.pt",
                "medium": "yolov8m.pt",
                "large": "yolov8l.pt",
                "xlarge": "yolov8x.pt",
            }
            
            model_file = model_map.get(model_size, "yolov8n.pt")
            self.model = YOLO(model_file)
            
            logger.info(f"Initialized YOLO v8 ({model_size}) on {device}")
        except ImportError:
            logger.warning("ultralytics not installed, YOLO detection unavailable")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
    
    def detect_objects(
        self,
        img: Image.Image,
        confidence_threshold: float = 0.5,
        iou_threshold: float = 0.45
    ) -> List[DetectionResult]:
        """
        Detect objects in image.
        
        Args:
            img: PIL Image
            confidence_threshold: Minimum confidence for detection
            iou_threshold: IoU threshold for NMS
        
        Returns:
            List of DetectionResult objects
        """
        if not self.model:
            raise RuntimeError("YOLO model not available")
        
        start_time = time.time()
        
        # Run detection
        results = self.model.predict(
            img,
            conf=confidence_threshold,
            iou=iou_threshold,
            verbose=False
        )
        
        detections = []
        
        # Parse results
        if results and len(results) > 0:
            result = results[0]
            boxes = result.boxes
            
            for box in boxes:
                # Get box coordinates
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                
                # Get confidence and class
                conf = float(box.conf[0].cpu().numpy())
                cls_id = int(box.cls[0].cpu().numpy())
                label = result.names[cls_id]
                
                detection = DetectionResult(
                    label=label,
                    confidence=conf,
                    bbox={
                        "x": int(x1),
                        "y": int(y1),
                        "width": int(x2 - x1),
                        "height": int(y2 - y1),
                    },
                    class_id=cls_id
                )
                
                detections.append(detection)
        
        duration = (time.time() - start_time) * 1000
        logger.debug(f"YOLO detected {len(detections)} objects in {duration:.2f}ms")
        
        return detections
    
    def detect_objects_from_numpy(
        self,
        img_np: np.ndarray,
        confidence_threshold: float = 0.5
    ) -> List[DetectionResult]:
        """
        Detect objects from numpy array.
        
        Args:
            img_np: Numpy array (H, W, C)
            confidence_threshold: Minimum confidence
        
        Returns:
            List of DetectionResult objects
        """
        img = Image.fromarray(img_np.astype('uint8'))
        return self.detect_objects(img, confidence_threshold)


class ElementDetector:
    """UI element detector for buttons, text fields, etc."""
    
    def __init__(self):
        """Initialize element detector."""
        logger.info("Initialized element detector")
    
    def detect_buttons(
        self,
        img: Image.Image,
        confidence_threshold: float = 0.6
    ) -> List[DetectionResult]:
        """
        Detect buttons using template matching and edge detection.
        
        Args:
            img: PIL Image
            confidence_threshold: Minimum confidence
        
        Returns:
            List of DetectionResult objects for detected buttons
        """
        start_time = time.time()
        
        # Convert to opencv format
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        
        # Edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        buttons = []
        
        for contour in contours:
            # Get bounding box
            x, y, w, h = cv2.boundingRect(contour)
            
            # Filter by size (buttons are typically rectangular and medium-sized)
            aspect_ratio = w / h if h > 0 else 0
            area = w * h
            
            if (0.5 < aspect_ratio < 5.0 and  # Reasonable aspect ratio
                100 < area < 50000 and  # Reasonable size
                w > 20 and h > 10):  # Minimum dimensions
                
                # Calculate confidence based on rectangularity
                rect_area = w * h
                contour_area = cv2.contourArea(contour)
                rectangularity = contour_area / rect_area if rect_area > 0 else 0
                
                if rectangularity > confidence_threshold:
                    button = DetectionResult(
                        label="button",
                        confidence=rectangularity,
                        bbox={"x": x, "y": y, "width": w, "height": h}
                    )
                    buttons.append(button)
        
        duration = (time.time() - start_time) * 1000
        logger.debug(f"Detected {len(buttons)} buttons in {duration:.2f}ms")
        
        return buttons
    
    def detect_text_fields(
        self,
        img: Image.Image,
        confidence_threshold: float = 0.6
    ) -> List[DetectionResult]:
        """
        Detect text input fields.
        
        Args:
            img: PIL Image
            confidence_threshold: Minimum confidence
        
        Returns:
            List of DetectionResult objects for text fields
        """
        # Convert to opencv format
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        
        # Detect edges
        edges = cv2.Canny(gray, 30, 100)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        text_fields = []
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            
            # Text fields are typically wide and short
            aspect_ratio = w / h if h > 0 else 0
            area = w * h
            
            if (2.0 < aspect_ratio < 20.0 and  # Wide and short
                500 < area < 100000 and  # Medium to large size
                w > 50 and 10 < h < 60):  # Appropriate dimensions
                
                # Calculate confidence
                rect_area = w * h
                contour_area = cv2.contourArea(contour)
                rectangularity = contour_area / rect_area if rect_area > 0 else 0
                
                if rectangularity > confidence_threshold:
                    text_field = DetectionResult(
                        label="text_field",
                        confidence=rectangularity,
                        bbox={"x": x, "y": y, "width": w, "height": h}
                    )
                    text_fields.append(text_field)
        
        logger.debug(f"Detected {len(text_fields)} text fields")
        
        return text_fields
    
    def detect_by_color(
        self,
        img: Image.Image,
        target_color: Tuple[int, int, int],
        color_tolerance: int = 30
    ) -> List[DetectionResult]:
        """
        Detect elements by color.
        
        Args:
            img: PIL Image
            target_color: Target RGB color tuple
            color_tolerance: Tolerance for color matching
        
        Returns:
            List of DetectionResult objects
        """
        # Convert to opencv format
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        
        # Create color mask
        target_bgr = np.array([target_color[2], target_color[1], target_color[0]])
        lower = np.clip(target_bgr - color_tolerance, 0, 255)
        upper = np.clip(target_bgr + color_tolerance, 0, 255)
        
        mask = cv2.inRange(img_cv, lower, upper)
        
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        elements = []
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 100:  # Filter small noise
                x, y, w, h = cv2.boundingRect(contour)
                
                element = DetectionResult(
                    label="color_match",
                    confidence=0.9,
                    bbox={"x": x, "y": y, "width": w, "height": h}
                )
                elements.append(element)
        
        logger.debug(f"Detected {len(elements)} elements by color")
        
        return elements
    
    def find_element_by_text(
        self,
        img: Image.Image,
        text: str,
        ocr_results: List[Dict]
    ) -> Optional[DetectionResult]:
        """
        Find element containing specific text.
        
        Args:
            img: PIL Image
            text: Text to find
            ocr_results: OCR results with bounding boxes
        
        Returns:
            DetectionResult if found, None otherwise
        """
        text_lower = text.lower()
        
        for ocr_result in ocr_results:
            if text_lower in ocr_result.get("text", "").lower():
                bbox = ocr_result.get("bbox", {})
                if bbox:
                    return DetectionResult(
                        label=f"text:{text}",
                        confidence=ocr_result.get("confidence", 0.9),
                        bbox=bbox
                    )
        
        return None
