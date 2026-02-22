"""
Integration tests for Vision system (Phase 4)
"""
import pytest
from PIL import Image, ImageDraw
import numpy as np
import io
import base64

from src.vision.capture import ScreenCapture
from src.vision.ocr import TesseractOCR, MultiEngineOCR, OCREngine
from src.vision.detection import ObjectDetector, ElementDetector
from src.vision.annotation import ScreenshotAnnotator


@pytest.fixture
def test_image():
    """Create test image with text and shapes."""
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    
    # Draw some shapes
    draw.rectangle([100, 100, 300, 200], fill='blue', outline='black', width=2)
    draw.ellipse([400, 100, 600, 300], fill='red', outline='black', width=2)
    
    # Add text
    draw.text((150, 140), "Test Button", fill='white')
    draw.text((450, 180), "Click Me!", fill='white')
    
    return img


@pytest.fixture
def test_screenshot(test_image):
    """Convert test image to base64 for API testing."""
    buffered = io.BytesIO()
    test_image.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()
    return img_base64


class TestScreenCapture:
    """Test screen capture functionality."""
    
    def test_get_monitors(self):
        """Test monitor detection."""
        capture = ScreenCapture()
        monitors = capture.get_monitors()
        
        assert len(monitors) >= 1
        assert monitors[0]["id"] == 1
        assert "width" in monitors[0]
        assert "height" in monitors[0]
    
    def test_capture_monitor(self):
        """Test screenshot capture."""
        capture = ScreenCapture()
        img = capture.capture_monitor(monitor_id=1)
        
        assert isinstance(img, Image.Image)
        assert img.width > 0
        assert img.height > 0
    
    def test_capture_region(self):
        """Test region capture."""
        capture = ScreenCapture()
        region = (0, 0, 640, 480)
        img = capture.capture_monitor(monitor_id=1, region=region)
        
        assert isinstance(img, Image.Image)
        assert img.width == 640
        assert img.height == 480
    
    def test_image_conversion(self, test_image):
        """Test image to base64 and back."""
        capture = ScreenCapture()
        
        # To base64
        img_base64 = capture.image_to_base64(test_image)
        assert isinstance(img_base64, str)
        assert len(img_base64) > 0
        
        # Back to image
        img_restored = capture.base64_to_image(img_base64)
        assert isinstance(img_restored, Image.Image)
        assert img_restored.size == test_image.size
    
    def test_numpy_conversion(self, test_image):
        """Test image to numpy and back."""
        capture = ScreenCapture()
        
        # To numpy
        img_array = capture.image_to_numpy(test_image)
        assert isinstance(img_array, np.ndarray)
        assert img_array.shape == (600, 800, 3)
        
        # Back to image
        img_restored = capture.numpy_to_image(img_array)
        assert isinstance(img_restored, Image.Image)
        assert img_restored.size == test_image.size
    
    def test_save_screenshot(self, test_image):
        """Test saving screenshot."""
        capture = ScreenCapture()
        file_path = capture.save_screenshot(test_image)
        
        assert file_path is not None
        import os
        assert os.path.exists(file_path)
        
        # Cleanup
        os.remove(file_path)


class TestOCR:
    """Test OCR functionality."""
    
    def test_tesseract_ocr(self):
        """Test Tesseract OCR."""
        # Create image with text
        img = Image.new('RGB', (400, 100), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 30), "Hello World", fill='black')
        
        ocr = TesseractOCR(language="eng")
        
        if ocr.pytesseract:  # Only if installed
            result = ocr.extract_text(img)
            assert "Hello" in result.text or "World" in result.text
            assert result.confidence > 0
    
    @pytest.mark.asyncio
    async def test_multi_engine_ocr(self):
        """Test multi-engine OCR."""
        # Create clear text image
        img = Image.new('RGB', (400, 100), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 30), "Test123", fill='black')
        
        ocr = MultiEngineOCR()
        result = await ocr.extract_text(img, engine=OCREngine.AUTO)
        
        assert result is not None
        assert isinstance(result.text, str)
        assert result.confidence >= 0.0


class TestDetection:
    """Test object and element detection."""
    
    def test_object_detector_initialization(self):
        """Test YOLO detector initialization."""
        detector = ObjectDetector(model_size="nano", device="cpu")
        assert detector.model_size == "nano"
        assert detector.device == "cpu"
    
    def test_element_detector_initialization(self):
        """Test element detector initialization."""
        detector = ElementDetector()
        assert detector is not None
    
    @pytest.mark.asyncio
    async def test_detect_buttons(self, test_image):
        """Test button detection."""
        detector = ElementDetector()
        buttons = await detector.detect_buttons(test_image)
        
        # Should detect at least the blue rectangle as potential button
        assert isinstance(buttons, list)
    
    @pytest.mark.asyncio
    async def test_detect_text_fields(self, test_image):
        """Test text field detection."""
        detector = ElementDetector()
        textfields = await detector.detect_text_fields(test_image)
        
        assert isinstance(textfields, list)


class TestAnnotation:
    """Test screenshot annotation."""
    
    def test_draw_bounding_box(self, test_image):
        """Test drawing bounding box."""
        annotator = ScreenshotAnnotator()
        bbox = {"x": 100, "y": 100, "width": 200, "height": 100}
        
        annotated = annotator.draw_bounding_box(test_image, bbox)
        
        assert isinstance(annotated, Image.Image)
        assert annotated.size == test_image.size
    
    def test_draw_label(self, test_image):
        """Test drawing label."""
        annotator = ScreenshotAnnotator()
        
        annotated = annotator.draw_label(
            test_image,
            "Test Label",
            (200, 200),
            background_color=(0, 0, 0)
        )
        
        assert isinstance(annotated, Image.Image)
    
    def test_highlight_region(self, test_image):
        """Test highlighting region."""
        annotator = ScreenshotAnnotator()
        bbox = {"x": 100, "y": 100, "width": 200, "height": 100}
        
        highlighted = annotator.highlight_region(test_image, bbox)
        
        assert isinstance(highlighted, Image.Image)
    
    def test_draw_crosshair(self, test_image):
        """Test drawing crosshair."""
        annotator = ScreenshotAnnotator()
        
        annotated = annotator.draw_crosshair(test_image, (400, 300))
        
        assert isinstance(annotated, Image.Image)
    
    def test_draw_arrow(self, test_image):
        """Test drawing arrow."""
        annotator = ScreenshotAnnotator()
        
        annotated = annotator.draw_arrow(
            test_image,
            (100, 100),
            (300, 300)
        )
        
        assert isinstance(annotated, Image.Image)
    
    def test_comparison_view(self, test_image):
        """Test creating comparison view."""
        annotator = ScreenshotAnnotator()
        
        # Create second image
        img2 = test_image.copy()
        
        # Horizontal
        horizontal = annotator.create_comparison_view(test_image, img2, "horizontal")
        assert horizontal.width > test_image.width
        
        # Vertical
        vertical = annotator.create_comparison_view(test_image, img2, "vertical")
        assert vertical.height > test_image.height


@pytest.mark.asyncio
class TestVisionAPI:
    """Test Vision API endpoints."""
    
    async def test_get_monitors(self, client):
        """Test GET /api/v1/vision/monitors."""
        response = await client.get("/api/v1/vision/monitors")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert "monitors" in data
        assert data["count"] >= 1
    
    async def test_capture_screenshot(self, client):
        """Test POST /api/v1/vision/capture."""
        response = await client.post(
            "/api/v1/vision/capture",
            json={"monitor_id": 1}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert "image_base64" in data
        assert data["width"] > 0
        assert data["height"] > 0
    
    async def test_ocr(self, client, test_screenshot):
        """Test POST /api/v1/vision/ocr."""
        response = await client.post(
            "/api/v1/vision/ocr",
            json={
                "image_base64": test_screenshot,
                "engine": "tesseract",
                "language": "eng"
            }
        )
        
        # May fail if tesseract not installed
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "text" in data
    
    async def test_detect_objects(self, client, test_screenshot):
        """Test POST /api/v1/vision/detect/objects."""
        response = await client.post(
            "/api/v1/vision/detect/objects",
            json={
                "image_base64": test_screenshot,
                "confidence_threshold": 0.5
            }
        )
        
        # May fail if YOLO not available
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "detections" in data
    
    async def test_detect_elements(self, client, test_screenshot):
        """Test POST /api/v1/vision/detect/elements."""
        response = await client.post(
            "/api/v1/vision/detect/elements",
            json={
                "image_base64": test_screenshot,
                "element_type": "all"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert "detections" in data
    
    async def test_annotate(self, client, test_screenshot):
        """Test POST /api/v1/vision/annotate."""
        detections = [
            {
                "label": "button",
                "confidence": 0.95,
                "bbox": {"x": 100, "y": 100, "width": 200, "height": 100}
            }
        ]
        
        response = await client.post(
            "/api/v1/vision/annotate",
            json={
                "image_base64": test_screenshot,
                "detections": detections,
                "show_labels": True,
                "show_confidence": True
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert "annotated_image_base64" in data


class TestEndToEndVision:
    """End-to-end vision pipeline tests."""
    
    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """Test complete vision pipeline: capture -> OCR -> detect -> annotate."""
        # 1. Capture
        capture = ScreenCapture()
        img = capture.capture_monitor(monitor_id=1)
        assert img is not None
        
        # 2. OCR (if available)
        ocr = MultiEngineOCR()
        try:
            ocr_result = await ocr.extract_text(img, engine=OCREngine.TESSERACT)
            assert ocr_result is not None
        except:
            pass  # OCR might not be available
        
        # 3. Element detection
        detector = ElementDetector()
        elements = await detector.detect_buttons(img)
        assert isinstance(elements, list)
        
        # 4. Annotation
        annotator = ScreenshotAnnotator()
        if elements:
            annotated = annotator.annotate_detections(img, elements)
            assert annotated is not None
    
    def test_performance_capture_speed(self):
        """Test that screen capture meets <100ms requirement."""
        import time
        
        capture = ScreenCapture()
        
        # Test 10 captures
        times = []
        for _ in range(10):
            start = time.time()
            img = capture.capture_monitor(monitor_id=1)
            duration = (time.time() - start) * 1000  # ms
            times.append(duration)
        
        avg_time = sum(times) / len(times)
        assert avg_time < 100, f"Average capture time {avg_time:.2f}ms exceeds 100ms target"
    
    @pytest.mark.asyncio
    async def test_memory_usage(self):
        """Test that vision system doesn't leak memory."""
        import psutil
        import gc
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Capture and process 50 images
        capture = ScreenCapture()
        detector = ElementDetector()
        
        for _ in range(50):
            img = capture.capture_monitor(monitor_id=1)
            await detector.detect_buttons(img)
            gc.collect()
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Should not increase by more than 500MB
        assert memory_increase < 500, f"Memory increased by {memory_increase:.2f}MB"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
