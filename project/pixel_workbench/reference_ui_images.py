"""Image-only reference helpers; safe in headless MCP processes without Tk."""
from PIL import Image, ImageDraw


def checker(image):
    background = Image.new("RGBA", image.size, "#252d3b")
    draw = ImageDraw.Draw(background)
    for y in range(0, image.height, 8):
        for x in range(0, image.width, 8):
            if (x//8+y//8) % 2:
                draw.rectangle((x, y, x+7, y+7), fill="#30394b")
    return Image.alpha_composite(background, image.convert("RGBA"))
