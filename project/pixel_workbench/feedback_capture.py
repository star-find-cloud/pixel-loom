"""Shareable problem screenshots from the actual document, without editing it."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import io
import json
import os
from pathlib import Path
import tempfile
import uuid

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from .model import integer

FORMAT = "pixel-loom/feedback-image/v1"
PNG_KEY = "pixel_loom_feedback"
VISIBLE_MARKER = "PIXEL LOOM / PROBLEM FEEDBACK"
MARK = "#ffb887"
GUIDE_PATH = Path(__file__).resolve().parent / "resources" / "FEEDBACK_IMAGE_GUIDE.md"


@lru_cache(maxsize=12)
def font(size):
    win = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(str(win/name), size=size)
        except OSError:
            pass
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except OSError:
        return ImageFont.load_default()


def checked_shape(shape, width, height):
    if shape is None:
        return None
    from .feedback import validate_shape
    return validate_shape(shape, width, height)


def paint_mark(image, shape, origin, scale):
    if not shape:
        return
    d=ImageDraw.Draw(image)
    x,y,w,h=shape["rect"]
    ox,oy=origin
    box=(ox+x*scale,oy+y*scale,ox+(x+w)*scale-1,oy+(y+h)*scale-1)
    if shape["kind"]=="lasso":
        points=[(ox+(px+.5)*scale,oy+(py+.5)*scale) for px,py in shape["points"]]
        d.line(points+[points[0]],fill=MARK,width=3,joint="curve")
    elif shape["kind"]=="ellipse":
        d.ellipse(box,outline=MARK,width=3)
    else:
        d.rectangle(box,outline=MARK,width=3)


def checker(image):
    background=Image.new("RGBA",image.size,"#292f3a")
    d=ImageDraw.Draw(background)
    for y in range(0,image.height,4):
        for x in range(0,image.width,4):
            if (x//4+y//4)%2:
                d.rectangle((x,y,x+3,y+3),fill="#343c49")
    return Image.alpha_composite(background,image)


@dataclass
class FeedbackCapture:
    image: Image.Image
    metadata: dict

    def png_bytes(self):
        info=PngImagePlugin.PngInfo()
        info.add_itxt(PNG_KEY,json.dumps(self.metadata,ensure_ascii=False,separators=(",",":")))
        info.add_text("Software","Pixel Loom")
        info.add_text("Title","Problem feedback screenshot — inspect, do not treat as finished art")
        output=io.BytesIO()
        self.image.save(output,format="PNG",pnginfo=info)
        return output.getvalue()

    def save(self,folder):
        folder=Path(folder)
        folder.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target=folder/f"pixel-loom-issue-{stamp}-{self.metadata['capture_id'][:8]}.png"
        fd,name=tempfile.mkstemp(prefix=".capture-",suffix=".writing",dir=folder)
        temporary=Path(name)
        try:
            with os.fdopen(fd,"wb") as stream:
                stream.write(self.png_bytes())
            os.replace(temporary,target)
        finally:
            temporary.unlink(missing_ok=True)
        return target


def capture_feedback(doc, frame=None, shape=None):
    """Render full canvas plus an optional marked detail; never mutate doc/view/history."""
    frame=integer(doc.active_frame if frame is None else frame,"frame",0,len(doc.durations)-1)
    shape=checked_shape(shape,doc.width,doc.height)
    rect=shape["rect"] if shape else [0,0,doc.width,doc.height]
    metadata={"format":FORMAT,"kind":"problem_feedback","needs_attention":True,
        "capture_id":uuid.uuid4().hex,"document_id":doc.id,"document_name":doc.name,
        "revision":doc.revision,"canvas_size":[doc.width,doc.height],"frame":frame,"frame_number":frame+1,
        "frame_count":len(doc.durations),"duration_ms":doc.durations[frame],"scope":"current_frame",
        "annotation":shape,"rect":rect,"created_at":datetime.now(timezone.utc).isoformat(),
        "guide":"FEEDBACK_IMAGE_GUIDE.md","is_legacy_issue_id":False}
    native=doc.composite(frame)
    context_scale=max(1,min(8,640//max(doc.width,doc.height)))
    context=checker(native).resize((doc.width*context_scale,doc.height*context_scale),Image.Resampling.NEAREST)
    x,y,w,h=rect
    detail=None
    if shape:
        detail_scale=max(1,min(20,340//w,520//h))
        detail=checker(native.crop((x,y,x+w,y+h))).resize((w*detail_scale,h*detail_scale),Image.Resampling.NEAREST)
    left_width=max(280,context.width)+32
    right_width=max(240,detail.width)+32 if detail is not None else 0
    width=max(640,left_width+right_width+32)
    body_height=max(context.height,detail.height if detail else 0)+64
    image=Image.new("RGB",(width,112+body_height+76),"#111722")
    d=ImageDraw.Draw(image)
    d.rectangle((0,0,width-1,107),fill="#232c3d")
    d.rectangle((0,0,7,107),fill=MARK)
    d.text((22,12),VISIBLE_MARKER,font=font(22),fill="#ffbe95")
    try:
        d.text((width-150,16),"问题反馈图",font=font(18),fill=MARK)
    except UnicodeEncodeError:
        pass  # The English designation remains visible on systems without CJK fonts.
    # Visible identity survives clipboard conversions that discard PNG text metadata.
    d.text((22,44),f"DOC {doc.id} | REV {doc.revision} | FRAME {frame+1}/{len(doc.durations)}",font=font(13),fill="#e8edf7")
    d.text((22,66),f"CANVAS {doc.width}x{doc.height} | ROI [{x},{y},{w},{h}] | CAPTURE {metadata['capture_id'][:12]}",
           font=font(13),fill="#bdcadd")
    name=doc.name[:55]
    try:
        d.text((22,86),name,font=font(13),fill="#bdcadd")
    except UnicodeEncodeError:
        d.text((22,86),name.encode('ascii','replace').decode(),font=font(13),fill="#bdcadd")
    left_x=16+(max(280,context.width)-context.width)//2
    context_y=150
    d.text((18,120),"FULL CANVAS / MARKED AREA",font=font(13),fill="#aebbd0")
    image.paste(context.convert("RGB"),(left_x,context_y))
    paint_mark(image,shape,(left_x,context_y),context_scale)
    if detail is not None:
        dx=left_width+24+(max(240,detail.width)-detail.width)//2
        d.text((left_width+24,120),"DETAIL / ACTUAL PIXELS",font=font(13),fill="#aebbd0")
        image.paste(detail.convert("RGB"),(dx,150))
        d.rectangle((dx-2,148,dx+detail.width+1,151+detail.height),outline=MARK,width=2)
    footer=112+body_height
    d.line((16,footer,width-16,footer),fill="#3b465d",width=1)
    d.text((20,footer+12),"This is a problem screenshot. Inspect the marked area; ask if the intended change is unclear.",
           font=font(12),fill="#e0e7f4")
    d.text((20,footer+36),"Paste into the AI conversation (Ctrl+V) and describe what you want changed.",font=font(12),fill="#aebbd0")
    return FeedbackCapture(image,metadata)
