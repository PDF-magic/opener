"""Remove active PDF features from an already rasterized Maximum copy.

Only decoded RGB pixel planes and bounded page dimensions cross into a fresh
PDF writer. No source PDF objects, actions, annotations, scripts, form fields,
attachments, metadata, or page content streams are cloned. This is NOT a
substitute for the upstream isolated renderer or mandatory scanner gate.
"""
from io import BytesIO
import math
import zlib

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, NumberObject, StreamObject
from PIL import Image

MAX_RASTER_INPUT_BYTES = 32 * 1024 * 1024
MAX_RASTER_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_RASTER_PAGES = 16
MAX_SIDE_PIXELS = 2048
MAX_TOTAL_PIXELS = 24_000_000


def remove_active_pdf_functionality(raster_pdf: bytes, expected_pages: int) -> bytes | None:
    """Rebuild trusted raster converter output from pixel bytes or fail closed.

    Require exactly one raster XObject per page. This is a post-conversion
    boundary, NOT a shortcut for editing an arbitrary interactive source PDF:
    the caller must render the source first. Only fresh PDF objects are written.
    On failure return None, never source bytes or an opening authorization.
    """
    if (type(raster_pdf) is not bytes or
            not 0 < len(raster_pdf) <= MAX_RASTER_INPUT_BYTES or
            type(expected_pages) is not int or
            not 1 <= expected_pages <= MAX_RASTER_PAGES or
            not raster_pdf.startswith(b"%PDF-")):
        return None

    try:
        reader = PdfReader(BytesIO(raster_pdf), strict=True)
        if reader.is_encrypted or len(reader.pages) != expected_pages:
            return None
        writer = PdfWriter()
        total_pixels = 0
        for source in reader.pages:
            width = float(source.mediabox.width)
            height = float(source.mediabox.height)
            if (not math.isfinite(width) or not math.isfinite(height) or
                    not 1 <= width <= 1440 or not 1 <= height <= 1440):
                return None
            if (int(source.get("/Rotate", 0)) != 0 or
                    source.cropbox != source.mediabox):
                return None
            resources = source.get("/Resources")
            if resources is None:
                return None
            xobjects = resources.get_object().get("/XObject")
            if xobjects is None:
                return None
            xobjects = xobjects.get_object()
            if len(xobjects) != 1:
                return None
            image_ref = next(iter(xobjects.values())).get_object()
            if image_ref.get("/Subtype") != "/Image":
                return None
            images = list(source.images)
            if len(images) != 1:
                return None
            with Image.open(BytesIO(images[0].data)) as loaded:
                pixel_width, pixel_height = loaded.size
                if (not 1 <= pixel_width <= MAX_SIDE_PIXELS or
                        not 1 <= pixel_height <= MAX_SIDE_PIXELS or
                        pixel_width * pixel_height > MAX_TOTAL_PIXELS - total_pixels):
                    return None
                # Decode pixels; never copy source image object dictionaries,
                # metadata, active dictionaries or PDF content streams.
                plane = loaded.convert("RGB").tobytes()
            total_pixels += pixel_width * pixel_height
            image = StreamObject()
            image._data = zlib.compress(plane, level=6)
            image.update({
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Image"),
                NameObject("/Width"): NumberObject(pixel_width),
                NameObject("/Height"): NumberObject(pixel_height),
                NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
                NameObject("/BitsPerComponent"): NumberObject(8),
                NameObject("/Filter"): NameObject("/FlateDecode"),
            })
            page = writer.add_blank_page(width=width, height=height)
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/XObject"): DictionaryObject({
                    NameObject("/Im0"): writer._add_object(image),
                }),
            })
            # Constant image-only drawing operators, no source /Contents.
            command = f"q {width:.4f} 0 0 {height:.4f} 0 0 cm /Im0 Do Q\n"
            content = StreamObject()
            content._data = command.encode("ascii")
            page[NameObject("/Contents")] = writer._add_object(content)

        output = BytesIO()
        writer.write(output)
        rewritten = output.getvalue()
        if (not 0 < len(rewritten) <= MAX_RASTER_OUTPUT_BYTES or
                rewritten == raster_pdf):
            return None
        from maximum_sanitized_copy import _passive_pages
        if not _passive_pages(rewritten, expected_pages):
            return None
        return rewritten
    except Exception:
        return None
