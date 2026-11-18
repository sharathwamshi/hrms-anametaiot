"""
Generates a branded, shareable job-post image (Section 4 of the Recruiter
Specification) using Pillow. No external template assets are required — two
built-in layouts ("classic-blue" and "bold-orange") are drawn programmatically
using the same brand palette as the rest of the app, so this works out of the
box. Real designed template PSDs/PNGs can be dropped in later and swapped in
without changing the calling code.
"""
import os
import textwrap
from PIL import Image, ImageDraw, ImageFont

BRAND_BLUE = (11, 79, 174)
BRAND_BLUE_DARK = (6, 36, 84)
BRAND_ORANGE = (242, 101, 10)
WHITE = (255, 255, 255)

_FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]
_FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
]


def _load_font(candidates, size):
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_job_post_image(
    output_path, job_title, department=None, location="Bengaluru, India",
    experience=None, apply_link=None, layout="classic-blue", size=(1200, 1200),
):
    """Renders the image to output_path and returns that path."""
    width, height = size
    img = Image.new("RGB", (width, height), BRAND_BLUE_DARK if layout == "classic-blue" else BRAND_ORANGE)
    draw = ImageDraw.Draw(img)

    # Gradient-ish background band
    accent = BRAND_ORANGE if layout == "classic-blue" else BRAND_BLUE
    draw.rectangle([0, height - 260, width, height], fill=accent)

    title_font = _load_font(_FONT_CANDIDATES_BOLD, 64)
    label_font = _load_font(_FONT_CANDIDATES_BOLD, 30)
    body_font = _load_font(_FONT_CANDIDATES_REGULAR, 34)
    footer_font = _load_font(_FONT_CANDIDATES_BOLD, 28)

    draw.text((70, 70), "WE'RE HIRING", font=label_font, fill=WHITE)

    wrapped_title = textwrap.wrap(job_title, width=18)
    y = 140
    for line in wrapped_title[:3]:
        draw.text((70, y), line, font=title_font, fill=WHITE)
        y += 76

    y += 20
    if department:
        draw.text((70, y), f"Department: {department}", font=body_font, fill=WHITE)
        y += 46
    if experience:
        draw.text((70, y), f"Experience: {experience}", font=body_font, fill=WHITE)
        y += 46
    draw.text((70, y), f"Location: {location}", font=body_font, fill=WHITE)

    footer_text = "Apply now" + (f" — {apply_link}" if apply_link else "")
    draw.text((70, height - 170), footer_text, font=footer_font, fill=WHITE)
    draw.text((70, height - 60), "Powered by +veGroww", font=body_font, fill=WHITE)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    return output_path
