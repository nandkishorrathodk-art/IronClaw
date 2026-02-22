"""
Screenshot annotation for Ironclaw
Draw bounding boxes, labels, and highlights on images
"""
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import numpy as np

from src.utils.logging import get_logger
from src.vision.detection import DetectionResult

logger = get_logger(__name__)


class ScreenshotAnnotator:
    """Annotate screenshots with bounding boxes and labels."""
    
    def __init__(self, font_size: int = 16):
        """
        Initialize annotator.
        
        Args:
            font_size: Font size for labels
        """
        self.font_size = font_size
        try:
            self.font = ImageFont.truetype("arial.ttf", font_size)
        except:
            # Fallback to default font
            self.font = ImageFont.load_default()
        
        logger.info("Initialized screenshot annotator")
    
    def draw_bounding_box(
        self,
        img: Image.Image,
        bbox: dict,
        color: Tuple[int, int, int] = (255, 0, 0),
        thickness: int = 2
    ) -> Image.Image:
        """
        Draw bounding box on image.
        
        Args:
            img: PIL Image
            bbox: Bounding box dict {"x": int, "y": int, "width": int, "height": int}
            color: RGB color tuple
            thickness: Line thickness
        
        Returns:
            Annotated PIL Image
        """
        img_copy = img.copy()
        draw = ImageDraw.Draw(img_copy)
        
        x = bbox["x"]
        y = bbox["y"]
        w = bbox["width"]
        h = bbox["height"]
        
        # Draw rectangle
        for i in range(thickness):
            draw.rectangle(
                [x + i, y + i, x + w - i, y + h - i],
                outline=color
            )
        
        return img_copy
    
    def draw_label(
        self,
        img: Image.Image,
        text: str,
        position: Tuple[int, int],
        color: Tuple[int, int, int] = (255, 0, 0),
        background_color: Optional[Tuple[int, int, int]] = None
    ) -> Image.Image:
        """
        Draw text label on image.
        
        Args:
            img: PIL Image
            text: Label text
            position: (x, y) position
            color: Text color
            background_color: Optional background color for label
        
        Returns:
            Annotated PIL Image
        """
        img_copy = img.copy()
        draw = ImageDraw.Draw(img_copy)
        
        # Get text size
        bbox = draw.textbbox(position, text, font=self.font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Draw background if specified
        if background_color:
            draw.rectangle(
                [position[0], position[1], position[0] + text_width + 4, position[1] + text_height + 4],
                fill=background_color
            )
        
        # Draw text
        draw.text((position[0] + 2, position[1] + 2), text, fill=color, font=self.font)
        
        return img_copy
    
    def highlight_region(
        self,
        img: Image.Image,
        bbox: dict,
        color: Tuple[int, int, int] = (255, 255, 0),
        alpha: float = 0.3
    ) -> Image.Image:
        """
        Highlight region with semi-transparent overlay.
        
        Args:
            img: PIL Image
            bbox: Bounding box dict
            color: RGB color for highlight
            alpha: Transparency (0.0 to 1.0)
        
        Returns:
            Annotated PIL Image
        """
        # Create overlay
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        x = bbox["x"]
        y = bbox["y"]
        w = bbox["width"]
        h = bbox["height"]
        
        # Draw filled rectangle with alpha
        fill_color = (*color, int(255 * alpha))
        draw.rectangle([x, y, x + w, y + h], fill=fill_color)
        
        # Convert to RGB and blend
        img_rgba = img.convert('RGBA')
        combined = Image.alpha_composite(img_rgba, overlay)
        
        return combined.convert('RGB')
    
    def annotate_detections(
        self,
        img: Image.Image,
        detections: List[DetectionResult],
        show_labels: bool = True,
        show_confidence: bool = True,
        color: Tuple[int, int, int] = (0, 255, 0)
    ) -> Image.Image:
        """
        Annotate image with detection results.
        
        Args:
            img: PIL Image
            detections: List of DetectionResult objects
            show_labels: Whether to show labels
            show_confidence: Whether to show confidence scores
            color: Color for annotations
        
        Returns:
            Annotated PIL Image
        """
        result = img.copy()
        
        for detection in detections:
            # Draw bounding box
            result = self.draw_bounding_box(
                result,
                detection.bbox,
                color=color,
                thickness=2
            )
            
            # Draw label if requested
            if show_labels:
                label_text = detection.label
                if show_confidence:
                    label_text += f" {detection.confidence:.2f}"
                
                # Position label above bbox
                label_x = detection.bbox["x"]
                label_y = max(0, detection.bbox["y"] - 20)
                
                result = self.draw_label(
                    result,
                    label_text,
                    (label_x, label_y),
                    color=color,
                    background_color=(0, 0, 0)
                )
        
        logger.debug(f"Annotated {len(detections)} detections")
        return result
    
    def draw_crosshair(
        self,
        img: Image.Image,
        position: Tuple[int, int],
        size: int = 20,
        color: Tuple[int, int, int] = (255, 0, 0),
        thickness: int = 2
    ) -> Image.Image:
        """
        Draw crosshair at position.
        
        Args:
            img: PIL Image
            position: (x, y) center position
            size: Crosshair size
            color: RGB color
            thickness: Line thickness
        
        Returns:
            Annotated PIL Image
        """
        img_copy = img.copy()
        draw = ImageDraw.Draw(img_copy)
        
        x, y = position
        
        # Draw horizontal line
        draw.line([x - size, y, x + size, y], fill=color, width=thickness)
        
        # Draw vertical line
        draw.line([x, y - size, x, y + size], fill=color, width=thickness)
        
        return img_copy
    
    def draw_arrow(
        self,
        img: Image.Image,
        start: Tuple[int, int],
        end: Tuple[int, int],
        color: Tuple[int, int, int] = (255, 0, 0),
        thickness: int = 2,
        arrow_size: int = 10
    ) -> Image.Image:
        """
        Draw arrow from start to end point.
        
        Args:
            img: PIL Image
            start: (x, y) start position
            end: (x, y) end position
            color: RGB color
            thickness: Line thickness
            arrow_size: Size of arrowhead
        
        Returns:
            Annotated PIL Image
        """
        import math
        
        img_copy = img.copy()
        draw = ImageDraw.Draw(img_copy)
        
        # Draw line
        draw.line([start, end], fill=color, width=thickness)
        
        # Calculate arrow angle
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        angle = math.atan2(dy, dx)
        
        # Calculate arrowhead points
        arrow_angle = math.pi / 6  # 30 degrees
        
        # Left point
        x1 = end[0] - arrow_size * math.cos(angle + arrow_angle)
        y1 = end[1] - arrow_size * math.sin(angle + arrow_angle)
        
        # Right point
        x2 = end[0] - arrow_size * math.cos(angle - arrow_angle)
        y2 = end[1] - arrow_size * math.sin(angle - arrow_angle)
        
        # Draw arrowhead
        draw.polygon([end, (x1, y1), (x2, y2)], fill=color)
        
        return img_copy
    
    def create_comparison_view(
        self,
        img1: Image.Image,
        img2: Image.Image,
        layout: str = "horizontal"
    ) -> Image.Image:
        """
        Create side-by-side comparison view.
        
        Args:
            img1: First image
            img2: Second image
            layout: "horizontal" or "vertical"
        
        Returns:
            Combined comparison image
        """
        if layout == "horizontal":
            # Resize images to same height
            max_height = max(img1.height, img2.height)
            
            img1_resized = img1.resize(
                (int(img1.width * max_height / img1.height), max_height),
                Image.Resampling.LANCZOS
            )
            img2_resized = img2.resize(
                (int(img2.width * max_height / img2.height), max_height),
                Image.Resampling.LANCZOS
            )
            
            # Create combined image
            total_width = img1_resized.width + img2_resized.width
            combined = Image.new('RGB', (total_width, max_height))
            combined.paste(img1_resized, (0, 0))
            combined.paste(img2_resized, (img1_resized.width, 0))
        
        else:  # vertical
            # Resize images to same width
            max_width = max(img1.width, img2.width)
            
            img1_resized = img1.resize(
                (max_width, int(img1.height * max_width / img1.width)),
                Image.Resampling.LANCZOS
            )
            img2_resized = img2.resize(
                (max_width, int(img2.height * max_width / img2.width)),
                Image.Resampling.LANCZOS
            )
            
            # Create combined image
            total_height = img1_resized.height + img2_resized.height
            combined = Image.new('RGB', (max_width, total_height))
            combined.paste(img1_resized, (0, 0))
            combined.paste(img2_resized, (0, img1_resized.height))
        
        logger.debug(f"Created {layout} comparison view")
        return combined
