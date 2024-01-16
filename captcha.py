import base64
import random
import string
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


def generate_captcha_image():
    captcha_length = 7
    captcha_chars = string.ascii_uppercase + string.digits
    captcha_code = ''.join(random.choice(captcha_chars) for _ in range(captcha_length))

    # Create a larger image with the captcha code
    original_width, original_height = 150, 100
    zoom_factor = 0.3  # Increase this value to zoom in further
    zoomed_width, zoomed_height = int(original_width * zoom_factor), int(original_height * zoom_factor)

    image = Image.new('RGB', (zoomed_width, zoomed_height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # Use the default font
    font = ImageFont.load_default()

    # Get the size of the text to be drawn
    text_width, text_height = draw.textsize(captcha_code, font=font)

    # Center the text in the larger image
    text_position = ((zoomed_width - text_width) // 2, (zoomed_height - text_height) // 2)

    draw.text(text_position, captcha_code, font=font, fill=(0, 0, 0))

    # Resize the image to the original dimensions
    image = image.resize((original_width, original_height), Image.ANTIALIAS)

    # Save the image to a BytesIO object
    image_io = BytesIO()
    image.save(image_io, 'PNG')
    image_io.seek(0)

    # Convert the image data to base64 encoding
    base64_image = base64.b64encode(image_io.getvalue()).decode('utf-8')

    return captcha_code, base64_image
