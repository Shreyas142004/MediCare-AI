import cv2
import numpy as np
from PIL import Image
import io
from typing import Dict, Union, Tuple

def load_image_from_bytes(image_bytes: bytes) -> np.ndarray:
    """Decodes raw image bytes into an OpenCV BGR numpy array."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        # Fallback using PIL
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return img

def enhance_contrast_clahe(gray: np.ndarray, clip_limit: float = 2.5, tile_grid_size: Tuple[int, int] = (8, 8)) -> np.ndarray:
    """Applies Contrast Limited Adaptive Histogram Equalization (CLAHE).
    Especially effective for foil strips with metallic reflections and uneven lighting."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    return clahe.apply(gray)

def remove_noise(gray: np.ndarray) -> np.ndarray:
    """Applies bilateral filtering to suppress foil texture while preserving text edges."""
    return cv2.bilateralFilter(gray, d=7, sigmaColor=75, sigmaSpace=75)

def adaptive_binarize(gray: np.ndarray) -> np.ndarray:
    """Applies Otsu's thresholding after Gaussian blur to produce clean binary text."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh

def preprocess_medicine_image(image_input: Union[bytes, str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Generates multiple preprocessed variations of a medicine strip image.
    Returns:
        dict containing 'original', 'grayscale', 'enhanced_contrast', and 'thresholded'
    """
    if isinstance(image_input, bytes):
        img = load_image_from_bytes(image_input)
    elif isinstance(image_input, str):
        img = cv2.imread(image_input)
        if img is None:
            raise FileNotFoundError(f"Could not load image at path: {image_input}")
    elif isinstance(image_input, np.ndarray):
        img = image_input
    else:
        raise ValueError("Unsupported image input type.")

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

    # Apply bilateral noise reduction
    denoised = remove_noise(gray)

    # Enhance contrast with CLAHE
    enhanced = enhance_contrast_clahe(denoised)

    # Binarize
    binarized = adaptive_binarize(enhanced)

    return {
        "original": img,
        "grayscale": gray,
        "enhanced_contrast": enhanced,
        "thresholded": binarized
    }

