"""One bounded d1-Omni screenshot decision; never calls LFM3 or Omni 2B.

The existing Vulkan d1 service must have its multimodal projector loaded.
Uses llama.cpp's documented /v1/systemone images[] data-URL input.
"""
from __future__ import annotations

import base64
from io import BytesIO
import json

from .recall import MAX_PNG_BYTES, PNG_MAGIC

PREVIEW_SIDE = 512


def preview_png(png: bytes) -> bytes:
    """Generate a small CPU-side preview; no source or preview file is written."""
    if (not isinstance(png, bytes) or len(png) > MAX_PNG_BYTES or
            not png.startswith(PNG_MAGIC)):
        raise ValueError("Invalid or oversized screenshot")
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        # Fail closed rather than send a full desktop frame to a tiny model.
        raise RuntimeError("Pillow is required for d1 image preview") from exc
    with Image.open(BytesIO(png)) as img:
        if img.width * img.height > 16_777_216:
            raise ValueError("Screenshot dimensions exceed limit")
        img = ImageOps.exif_transpose(img)
        img.thumbnail((PREVIEW_SIDE, PREVIEW_SIDE), Image.Resampling.BILINEAR)
        out = BytesIO()
        img.save(out, format="PNG", compress_level=2)
        preview = out.getvalue()
        if len(preview) > 1024 * 1024:
            raise ValueError("D1 preview exceeds limit")
        return preview


async def decide_visual(models, png: bytes, details: dict, *, threshold=0.68):
    if not isinstance(details, dict) or not 0 <= threshold <= 1:
        raise ValueError("Invalid d1 visual input")
    # No full URLs, queries, screenshots or OCR in textual metadata.
    safe = {}
    for key in ("event", "source", "app_id", "workspace_id"):
        item = details.get(key)
        if item is not None:
            if not isinstance(item, (str, int)):
                raise ValueError("Invalid d1 event field")
            safe[key] = str(item)[:75]
    thumb = preview_png(png)
    response = await models.call("decision", "/v1/systemone", {
        "state": json.dumps(safe, ensure_ascii=False)[:350],
        "images": ["data:image/png;base64," + base64.b64encode(thumb).decode("ascii")],
        "questions": {
            "visual_delta": {
                "type": "noul",
                "instructions": (
                    "Is this visible screen likely to contain meaningful new text, "
                    "a changed page, a dialog, an error or other useful scene "
                    "details worth indexing? Ignore cosmetic animation."
                ),
            }
        },
    })
    score = response.get("answers", {}).get("visual_delta", {}).get("noul")
    if type(score) not in (int, float) or not 0 <= score <= 1:
        raise ValueError("Malformed d1 visual answer")
    return {"capture_recommended":score >= threshold, "score":float(score),
            "threshold":threshold, "preview_bytes":len(thumb)}
