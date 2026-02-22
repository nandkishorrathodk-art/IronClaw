"""
Vision API endpoints for Ironclaw
Screen capture, OCR, object detection, and visual understanding
"""
from fastapi import APIRouter, HTTPException, File, UploadFile
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from PIL import Image
import io
import base64

from src.utils.logging import get_logger
from src.vision.capture import ScreenCapture
from src.vision.ocr import MultiEngineOCR, OCREngine
from src.vision.detection import ObjectDetector, ElementDetector
from src.vision.understanding import VisualUnderstanding
from src.vision.annotation import ScreenshotAnnotator
from src.utils.metrics import (
    api_requests_total,
    api_request_duration_seconds,
    api_requests_in_progress
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/vision", tags=["vision"])

# Initialize vision components
capture = ScreenCapture()
ocr = MultiEngineOCR()
object_detector = ObjectDetector(model_size="nano", device="cpu")
element_detector = ElementDetector()
understanding = VisualUnderstanding()
annotator = ScreenshotAnnotator()


# Request/Response Models
class CaptureRequest(BaseModel):
    monitor_id: int = Field(1, description="Monitor ID (1-indexed)")
    region: Optional[List[int]] = Field(None, description="Region [x, y, width, height]")
    save: bool = Field(False, description="Save screenshot to disk")


class CaptureResponse(BaseModel):
    success: bool
    image_base64: str
    width: int
    height: int
    file_path: Optional[str] = None


class OCRRequest(BaseModel):
    image_base64: Optional[str] = None
    monitor_id: Optional[int] = None
    engine: str = Field("auto", description="OCR engine: tesseract, paddle, gpt4v, auto")
    language: str = Field("eng", description="Language code")


class OCRResponse(BaseModel):
    success: bool
    text: str
    confidence: float
    engine: str
    bounding_boxes: List[Dict]
    language: str


class DetectObjectsRequest(BaseModel):
    image_base64: Optional[str] = None
    monitor_id: Optional[int] = None
    confidence_threshold: float = Field(0.5, ge=0.0, le=1.0)


class DetectElementsRequest(BaseModel):
    image_base64: Optional[str] = None
    monitor_id: Optional[int] = None
    element_type: str = Field("all", description="button, textfield, all")


class DetectionResponse(BaseModel):
    success: bool
    detections: List[Dict]
    count: int


class UnderstandRequest(BaseModel):
    image_base64: Optional[str] = None
    monitor_id: Optional[int] = None
    question: Optional[str] = None
    task: str = Field("describe", description="describe, question, extract, identify_ui")
    schema: Optional[Dict] = None


class UnderstandResponse(BaseModel):
    success: bool
    result: str | Dict | List


class AnnotateRequest(BaseModel):
    image_base64: str
    detections: List[Dict]
    show_labels: bool = True
    show_confidence: bool = True


class AnnotateResponse(BaseModel):
    success: bool
    annotated_image_base64: str


# Endpoints

@router.get("/monitors")
def get_monitors():
    """Get list of available monitors."""
    api_requests_total.labels(endpoint="/api/v1/vision/monitors", method="GET", status="200").inc()
    
    with api_requests_in_progress.labels(endpoint="/api/v1/vision/monitors").track_inprogress():
        with api_request_duration_seconds.labels(endpoint="/api/v1/vision/monitors").time():
            monitors = capture.get_monitors()
            
            return {
                "success": True,
                "monitors": monitors,
                "count": len(monitors)
            }


@router.post("/capture", response_model=CaptureResponse)
def capture_screenshot(request: CaptureRequest):
    """Capture screenshot from monitor or region."""
    api_requests_total.labels(endpoint="/api/v1/vision/capture", method="POST", status="200").inc()
    
    with api_requests_in_progress.labels(endpoint="/api/v1/vision/capture").track_inprogress():
        with api_request_duration_seconds.labels(endpoint="/api/v1/vision/capture").time():
            try:
                # Capture image
                region_tuple = tuple(request.region) if request.region else None
                img = capture.capture_monitor(request.monitor_id, region_tuple)
                
                # Convert to base64
                img_base64 = capture.image_to_base64(img)
                
                # Save if requested
                file_path = None
                if request.save:
                    file_path = capture.save_screenshot(img)
                
                return CaptureResponse(
                    success=True,
                    image_base64=img_base64,
                    width=img.width,
                    height=img.height,
                    file_path=file_path
                )
            
            except Exception as e:
                logger.error(f"Screenshot capture failed: {e}")
                api_requests_total.labels(endpoint="/api/v1/vision/capture", method="POST", status="500").inc()
                raise HTTPException(status_code=500, detail=str(e))


@router.post("/ocr", response_model=OCRResponse)
async def perform_ocr(request: OCRRequest):
    """Perform OCR on image."""
    api_requests_total.labels(endpoint="/api/v1/vision/ocr", method="POST", status="200").inc()
    
    with api_requests_in_progress.labels(endpoint="/api/v1/vision/ocr").track_inprogress():
        with api_request_duration_seconds.labels(endpoint="/api/v1/vision/ocr").time():
            try:
                # Get image
                if request.image_base64:
                    img = capture.base64_to_image(request.image_base64)
                elif request.monitor_id:
                    img = capture.capture_monitor(request.monitor_id)
                else:
                    raise HTTPException(status_code=400, detail="Provide image_base64 or monitor_id")
                
                # Select engine
                engine = OCREngine[request.engine.upper()] if request.engine.upper() in OCREngine.__members__ else OCREngine.AUTO
                
                # Perform OCR
                result = await ocr.extract_text(img, engine=engine, language=request.language)
                
                return OCRResponse(
                    success=True,
                    text=result.text,
                    confidence=result.confidence,
                    engine=result.engine,
                    bounding_boxes=result.bounding_boxes,
                    language=result.language
                )
            
            except Exception as e:
                logger.error(f"OCR failed: {e}")
                api_requests_total.labels(endpoint="/api/v1/vision/ocr", method="POST", status="500").inc()
                raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect/objects", response_model=DetectionResponse)
def detect_objects(request: DetectObjectsRequest):
    """Detect objects in image using YOLO."""
    api_requests_total.labels(endpoint="/api/v1/vision/detect/objects", method="POST", status="200").inc()
    
    with api_requests_in_progress.labels(endpoint="/api/v1/vision/detect/objects").track_inprogress():
        with api_request_duration_seconds.labels(endpoint="/api/v1/vision/detect/objects").time():
            try:
                # Get image
                if request.image_base64:
                    img = capture.base64_to_image(request.image_base64)
                elif request.monitor_id:
                    img = capture.capture_monitor(request.monitor_id)
                else:
                    raise HTTPException(status_code=400, detail="Provide image_base64 or monitor_id")
                
                # Detect objects
                detections = object_detector.detect_objects(
                    img,
                    confidence_threshold=request.confidence_threshold
                )
                
                return DetectionResponse(
                    success=True,
                    detections=[d.to_dict() for d in detections],
                    count=len(detections)
                )
            
            except Exception as e:
                logger.error(f"Object detection failed: {e}")
                api_requests_total.labels(endpoint="/api/v1/vision/detect/objects", method="POST", status="500").inc()
                raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect/elements", response_model=DetectionResponse)
async def detect_elements(request: DetectElementsRequest):
    """Detect UI elements in screenshot."""
    api_requests_total.labels(endpoint="/api/v1/vision/detect/elements", method="POST", status="200").inc()
    
    with api_requests_in_progress.labels(endpoint="/api/v1/vision/detect/elements").track_inprogress():
        with api_request_duration_seconds.labels(endpoint="/api/v1/vision/detect/elements").time():
            try:
                # Get image
                if request.image_base64:
                    img = capture.base64_to_image(request.image_base64)
                elif request.monitor_id:
                    img = capture.capture_monitor(request.monitor_id)
                else:
                    raise HTTPException(status_code=400, detail="Provide image_base64 or monitor_id")
                
                # Detect elements based on type
                if request.element_type == "button":
                    detections = await element_detector.detect_buttons(img)
                elif request.element_type == "textfield":
                    detections = await element_detector.detect_text_fields(img)
                else:  # all
                    buttons = await element_detector.detect_buttons(img)
                    textfields = await element_detector.detect_text_fields(img)
                    detections = buttons + textfields
                
                return DetectionResponse(
                    success=True,
                    detections=[d.to_dict() for d in detections],
                    count=len(detections)
                )
            
            except Exception as e:
                logger.error(f"Element detection failed: {e}")
                api_requests_total.labels(endpoint="/api/v1/vision/detect/elements", method="POST", status="500").inc()
                raise HTTPException(status_code=500, detail=str(e))


@router.post("/understand", response_model=UnderstandResponse)
async def understand_image(request: UnderstandRequest):
    """Understand image using AI."""
    api_requests_total.labels(endpoint="/api/v1/vision/understand", method="POST", status="200").inc()
    
    with api_requests_in_progress.labels(endpoint="/api/v1/vision/understand").track_inprogress():
        with api_request_duration_seconds.labels(endpoint="/api/v1/vision/understand").time():
            try:
                # Get image
                if request.image_base64:
                    img = capture.base64_to_image(request.image_base64)
                elif request.monitor_id:
                    img = capture.capture_monitor(request.monitor_id)
                else:
                    raise HTTPException(status_code=400, detail="Provide image_base64 or monitor_id")
                
                # Perform requested task
                if request.task == "describe":
                    result = await understanding.describe_image(img)
                elif request.task == "question":
                    if not request.question:
                        raise HTTPException(status_code=400, detail="Question required for task=question")
                    result = await understanding.answer_question(img, request.question)
                elif request.task == "extract":
                    if not request.schema:
                        raise HTTPException(status_code=400, detail="Schema required for task=extract")
                    result = await understanding.extract_structured_data(img, request.schema)
                elif request.task == "identify_ui":
                    result = await understanding.identify_ui_elements(img)
                else:
                    raise HTTPException(status_code=400, detail=f"Unknown task: {request.task}")
                
                return UnderstandResponse(
                    success=True,
                    result=result
                )
            
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Visual understanding failed: {e}")
                api_requests_total.labels(endpoint="/api/v1/vision/understand", method="POST", status="500").inc()
                raise HTTPException(status_code=500, detail=str(e))


@router.post("/annotate", response_model=AnnotateResponse)
def annotate_image(request: AnnotateRequest):
    """Annotate image with detection results."""
    api_requests_total.labels(endpoint="/api/v1/vision/annotate", method="POST", status="200").inc()
    
    with api_requests_in_progress.labels(endpoint="/api/v1/vision/annotate").track_inprogress():
        with api_request_duration_seconds.labels(endpoint="/api/v1/vision/annotate").time():
            try:
                # Decode image
                img = capture.base64_to_image(request.image_base64)
                
                # Convert detection dicts to DetectionResult objects
                from src.vision.detection import DetectionResult
                detections = [
                    DetectionResult(
                        label=d.get("label", ""),
                        confidence=d.get("confidence", 0.0),
                        bbox=d.get("bbox", {}),
                        class_id=d.get("class_id")
                    )
                    for d in request.detections
                ]
                
                # Annotate image
                annotated = annotator.annotate_detections(
                    img,
                    detections,
                    show_labels=request.show_labels,
                    show_confidence=request.show_confidence
                )
                
                # Convert to base64
                annotated_base64 = capture.image_to_base64(annotated)
                
                return AnnotateResponse(
                    success=True,
                    annotated_image_base64=annotated_base64
                )
            
            except Exception as e:
                logger.error(f"Image annotation failed: {e}")
                api_requests_total.labels(endpoint="/api/v1/vision/annotate", method="POST", status="500").inc()
                raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    """Upload image for processing."""
    api_requests_total.labels(endpoint="/api/v1/vision/upload", method="POST", status="200").inc()
    
    try:
        # Read image file
        contents = await file.read()
        img = Image.open(io.BytesIO(contents))
        
        # Convert to base64
        img_base64 = capture.image_to_base64(img)
        
        return {
            "success": True,
            "image_base64": img_base64,
            "width": img.width,
            "height": img.height,
            "format": img.format
        }
    
    except Exception as e:
        logger.error(f"Image upload failed: {e}")
        api_requests_total.labels(endpoint="/api/v1/vision/upload", method="POST", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))
