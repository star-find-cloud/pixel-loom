"""Evidence-based finish/review/repair workflow. Numeric checks never certify aesthetics."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import uuid
from typing import Literal

from PIL import Image, ImageChops, ImageDraw
from typing_extensions import TypedDict

from .model import Document, PixelError, integer, pixels

DEFAULT_POLICY = {"brief": "", "expected_width": None, "expected_height": None, "expected_frames": None,
                  "max_colors": None, "transparent_background": None, "fixed_regions": [], "detail_regions": [],
                  "uniform_timing": False, "loop": True, "criteria": [], "max_rounds": 3}


class QualitySettings(TypedDict, total=False):
    brief: str
    expected_width: int | None
    expected_height: int | None
    expected_frames: int | None
    max_colors: int | None
    transparent_background: bool | None
    fixed_regions: list[str]
    detail_regions: list[str]
    uniform_timing: bool
    loop: bool
    criteria: list[str]
    max_rounds: int


class VisualCheck(TypedDict):
    criterion_id: str
    verdict: Literal["pass", "fail", "uncertain"]
    reason: str


class WarningResolution(TypedDict):
    warning_id: str
    verdict: Literal["acceptable", "needs_fix", "uncertain"]
    reason: str


def validate_policy(value):
    if not isinstance(value, dict) or set(value)-set(DEFAULT_POLICY):
        raise PixelError("Unknown quality settings")
    policy = {**deepcopy(DEFAULT_POLICY), **deepcopy(value)}
    for key, maximum in (("expected_width", 512), ("expected_height", 512), ("expected_frames", 256), ("max_colors", 65536)):
        if policy[key] is not None:
            integer(policy[key], key, 1, maximum)
    for key in ("uniform_timing", "loop"):
        if not isinstance(policy[key], bool):
            raise PixelError(f"{key} must be boolean")
    if policy["transparent_background"] is not None and not isinstance(policy["transparent_background"], bool):
        raise PixelError("transparent_background must be boolean or null")
    if not isinstance(policy["brief"], str) or len(policy["brief"]) > 2000:
        raise PixelError("Quality brief must contain at most 2000 characters")
    for key, limit, length in (("fixed_regions", 16, 120), ("detail_regions",8,120), ("criteria", 12, 300)):
        values = policy[key]
        if not isinstance(values, list) or len(values)>limit or any(not isinstance(v, str) or not v.strip() or len(v)>length for v in values):
            raise PixelError(f"Invalid quality {key}")
        policy[key] = list(dict.fromkeys(v.strip() for v in values))
    integer(policy["max_rounds"], "max_rounds", 1, 20)
    return policy


def validate_records(records):
    if not isinstance(records, list) or len(records)>16:
        raise PixelError("At most 16 quality records are stored in a project")
    for record in records:
        if not isinstance(record, dict) or len(json.dumps(record, ensure_ascii=False))>100_000:
            raise PixelError("Invalid quality review record")
        if record.get("status") not in ("passed", "needs_changes", "uncertain"):
            raise PixelError("Invalid quality review status")
        if not isinstance(record.get("content_digest"), str) or len(record["content_digest"])!=64:
            raise PixelError("Invalid quality content digest")
        if not isinstance(record.get("scope"), dict) or not isinstance(record.get("visual_checks"), list):
            raise PixelError("Invalid quality review scope/checks")
        scope=record["scope"]
        if not isinstance(scope.get("layers"),list) or any(not isinstance(v,str) for v in scope["layers"]) or not isinstance(scope.get("frames"),list):
            raise PixelError("Invalid quality scope fields")
        for frame in scope["frames"]:
            integer(frame,"review frame",0,255)
        if record.get("method") not in ("frames_and_timing","playback_and_frames") or not isinstance(record.get("summary"),str):
            raise PixelError("Invalid quality method/summary")
    return deepcopy(records)


def content_digest(doc):
    data = doc.to_dict()
    for key in ("revision", "active_layer", "active_frame", "selection", "quality_reviews", "feedback"):
        data.pop(key, None)
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def scoped_document(doc, tag=None, layers=None):
    clone = Document.from_dict(doc.to_dict())
    if layers is not None:
        included = {clone.layer(item).id for item in layers}
        if not included:
            raise PixelError("Select at least one layer for review")
        for layer in clone.layers:
            layer.visible = layer.id in included
    included = [l.id for l in clone.layers if l.visible and l.opacity>0]
    frames = clone.frame_indices(tag)
    return clone, {"tag": tag, "layers": sorted(included), "frames": frames}


def required_criteria(doc, policy, frames):
    criteria = [{"id": "requirements", "label": "是否满足任务要求与交付规格"},
                {"id": "silhouette", "label": "轮廓、辨识度与像素边缘是否清楚"},
                {"id": "color_detail", "label": "配色、明暗与局部细节是否协调"}]
    if doc.reference and doc.reference.get("subject"):
        criteria.append({"id": "reference_match", "label": "主体特征与要求的参考画风是否吻合"})
    if len(frames)>1:
        criteria += [{"id": "motion", "label": "动作是否自然，衣物是否出现贴片平移、断接或抖动"},
                     {"id": "timing", "label": "按真实帧时长观察，节奏和循环过渡是否合适"}]
    for i, label in enumerate(policy["criteria"]):
        criteria.append({"id": f"custom_{i+1}", "label": label})
    return criteria


def changed_pixels(a, b):
    diff = ImageChops.difference(a, b)
    box = diff.getbbox(alpha_only=False)
    return sum(any(c) for c in pixels(diff.crop(box))) if box else 0


def analyze(doc, scope, policy):
    frames = scope["frames"]
    images = [doc.composite(f) for f in frames]
    checks, warnings = [], []
    def check(key, label, passed, details):
        checks.append({"id": key, "label": label, "passed": bool(passed), "details": details})
    for key, actual in (("expected_width", doc.width), ("expected_height", doc.height), ("expected_frames", len(frames))):
        target = policy[key]
        check(key, {"expected_width": "画布宽度", "expected_height": "画布高度", "expected_frames": "动画帧数"}[key],
              target is None or actual==target, {"actual": actual, "required": target})
    blank = [f for f, image in zip(frames, images) if not image.getbbox()]
    check("nonempty", "画面不是空白", not blank, {"blank_frames": blank})
    colors = set()
    color_overflow = False
    for image in images:
        entries=image.getcolors(65536)
        if entries is None:
            color_overflow=True
            break
        colors.update(c for _, c in entries if c[3])
        if len(colors)>65536:
            color_overflow=True
            break
    check("palette", "色数限制", policy["max_colors"] is None or not color_overflow and len(colors)<=policy["max_colors"],
          {"opaque_colors": ">65536" if color_overflow else len(colors), "required_maximum": policy["max_colors"]})
    transparent = all(image.getchannel("A").getextrema()[0]==0 for image in images)
    check("transparency", "透明背景要求", policy["transparent_background"] is not True or transparent,
          {"has_transparent_pixels_in_every_frame": transparent, "required": policy["transparent_background"]})
    durations = [doc.durations[f] for f in frames]
    check("uniform_timing", "帧时长要求", not policy["uniform_timing"] or len(set(durations))==1, {"durations_ms": durations})
    for name in policy["fixed_regions"]:
        if name not in doc.regions:
            check("fixed_"+name, "固定部位 · "+name, False, {"error": "Named region is missing"})
            continue
        x, y, w, h = doc.regions[name]
        first = images[0].crop((x,y,x+w,y+h)).tobytes()
        moved = [f for f, image in zip(frames, images) if image.crop((x,y,x+w,y+h)).tobytes()!=first]
        check("fixed_"+name, "固定部位 · "+name, not moved, {"rect": [x,y,w,h], "changed_frames": moved})
    blocked=pending_feedback(doc,frames)
    if getattr(doc,"feedback",[]):
        check("feedback_resolved","用户标记的问题已处理",not blocked,
              {"pending_issue_ids":[i["id"] for i in blocked],"count":len(blocked)})
    playback_frames=doc.frame_indices(scope["tag"],playback=True)
    by_frame=dict(zip(frames,images))
    playback_images=[by_frame[f] for f in playback_frames]
    changes = [changed_pixels(a,b) for a,b in zip(playback_images, playback_images[1:])]
    seam = changed_pixels(playback_images[-1], playback_images[0]) if len(playback_images)>1 else 0
    if len(images)>1:
        if len({image.tobytes() for image in images})==1:
            warnings.append({"id": "static_animation", "message": "全部动画帧画面相同；请确认是否真的完成了动作。"})
        ratio = max(durations)/min(durations)
        if ratio>=4:
            warnings.append({"id": "uneven_timing", "message": f"最长/最短帧时长相差 {ratio:.1f} 倍；请按真实节奏检查停顿与突跳。"})
        if policy["loop"] and seam>max(4, max(changes, default=0)*1.75):
            warnings.append({"id": "loop_jump", "message": "循环首尾的像素变化明显大于内部转场，请检查回跳。"})
        rigid = []
        for layer in doc.layers:
            if not layer.visible or layer.opacity==0:
                continue
            cels = [layer.cels[f] for f in frames]
            boxes = [image.getbbox() for image in cels]
            valid = [(im, box) for im, box in zip(cels, boxes) if box]
            if len(valid)<2:
                continue
            shapes = {im.crop(box).tobytes() for im, box in valid}
            sizes = {(box[2]-box[0], box[3]-box[1]) for _, box in valid}
            points = {(box[0],box[1]) for _, box in valid}
            if len(shapes)==1 and len(sizes)==1 and len(points)>1 and (valid[0][1][2]-valid[0][1][0])*(valid[0][1][3]-valid[0][1][1])>=16:
                rigid.append(layer.name)
        if rigid:
            warnings.append({"id": "rigid_translation", "message": "这些图层只有整块平移："+"、".join(rigid)+"。物体位移可能合理；衣物需检查固定点和局部弯曲。"})
    return {"technical_passed": all(c["passed"] for c in checks), "technical_checks": checks, "warnings": warnings,
            "metrics": {"frames": frames, "playback_frames":playback_frames,
                        "duration_ms": sum(doc.durations[f] for f in playback_frames), "durations_ms": durations,
                        "changed_pixels_between_frames": changes, "loop_seam_changed_pixels": seam,
                        "distinct_poses": len({image.tobytes() for image in images})},
            "criteria": required_criteria(doc, policy, frames), "automatic_verdict": "程序检查不代表画风和动作自然度合格。"}


def tiled_evidence(doc, frames, labels, columns=8, tile=100, rect=None):
    columns = min(columns, len(frames))
    rows = math.ceil(len(frames)/columns)
    out = Image.new("RGBA", (columns*(tile+8), rows*(tile+30)), "#171d28")
    draw = ImageDraw.Draw(out)
    for index, (frame, label) in enumerate(zip(frames, labels)):
        im = doc.preview(frame, scale=1,rect=rect)
        ratio = min(tile/im.width, tile/im.height)
        size = max(1,round(im.width*ratio)),max(1,round(im.height*ratio))
        im = im.resize(size, Image.Resampling.NEAREST)
        x, y = index%columns*(tile+8), index//columns*(tile+30)
        out.paste(im,(x+(tile+8-size[0])//2,y+5+(tile-size[1])//2))
        draw.text((x+4,y+tile+10), label, fill="#dce7f5")
    return out


def criteria_verdicts(values, expected, key="criterion_id", allowed=("pass","fail","uncertain")):
    if not isinstance(values,list) or len(values)!=len(expected):
        raise PixelError("Every required visual check/warning needs a conclusion", code="REVIEW_INCOMPLETE")
    found = {}
    for value in values:
        if not isinstance(value,dict) or set(value)!={key,"verdict","reason"} or value[key] in found or value[key] not in expected:
            raise PixelError("Unknown or repeated review item", code="REVIEW_INCOMPLETE")
        if value["verdict"] not in allowed or not isinstance(value["reason"],str) or not 1<=len(value["reason"].strip())<=2000:
            raise PixelError("Each conclusion needs a verdict and concrete visual evidence", code="REVIEW_INCOMPLETE")
        found[value[key]] = deepcopy(value)
    return list(found.values())


def pending_feedback(doc, frames=None):
    from .feedback import summary
    needed=set(frames) if frames is not None else None
    return [i for i in summary(doc)["issues"] if i["status"] not in ("resolved","dismissed") and
            (needed is None or needed.intersection(i["frames"]))]


class QualityManager:
    def __init__(self, runtime):
        self.runtime = Path(runtime)/"review-cache"
        self.tickets = OrderedDict()
        self._digest_cache = None

    def digest(self, doc):
        key = id(doc),doc.id,doc.content_serial
        if not self._digest_cache or self._digest_cache[0]!=key:
            self._digest_cache = key, content_digest(doc)
        return self._digest_cache[1]

    def matching_record(self, doc, tag=None, layers=None, frame=None):
        if not doc.quality_reviews:
            return None
        _, scope = scoped_document(doc, tag, layers)
        needed = {frame} if frame is not None else set(scope["frames"])
        digest = self.digest(doc)
        for record in reversed(doc.quality_reviews):
            reviewed = record.get("scope",{})
            if record["content_digest"]==digest and reviewed.get("layers")==scope["layers"] and needed.issubset(set(reviewed.get("frames",[]))):
                return record
        return None

    def summary(self, doc):
        blocked=pending_feedback(doc)
        if blocked:
            asking=sum(i["status"]=="needs_clarification" for i in blocked)
            return {"status":"needs_changes","summary":f"还有 {len(blocked)} 条用户问题待处理"+
                    (f"，其中 {asking} 条等待用户回复" if asking else ""),
                    "pending_issue_ids":[i["id"] for i in blocked],"next_action":"pixel_feedback",
                    "final_export_requires_review":True}
        if not doc.quality_reviews:
            return {"status":"pending","summary":"待程序检查与 AI 看图复核","next_action":"pixel_review","final_export_requires_review":True}
        digest = self.digest(doc)
        for record in reversed(doc.quality_reviews):
            if record["content_digest"]==digest:
                return {"status": record["status"], "scope": record["scope"], "summary": record["summary"],
                        "method": record["method"], "round": record["round"], "next_action": record["next_action"]}
        return {"status": "stale" if doc.quality_reviews else "pending", "summary": "作品已修改，请重新自检" if doc.quality_reviews else "待程序检查与 AI 看图复核",
                "next_action": "pixel_review", "final_export_requires_review": True}

    def start(self, doc, tag=None, layers=None):
        snapshot, scope = scoped_document(doc, tag, layers)
        policy = validate_policy(doc.quality_policy or {})
        analysis = analyze(snapshot, scope, policy)
        review_id = uuid.uuid4().hex
        folder = self.runtime/review_id
        folder.mkdir(parents=True,exist_ok=True)
        playback_frames = snapshot.frame_indices(tag, playback=True)
        playback_images = [snapshot.composite(f) for f in playback_frames]
        alpha_binary = all(im.getchannel("A").getextrema() in ((0,255),(255,255),(0,0)) and
                           all(a in (0,255) for a in pixels(im.getchannel("A"))) for im in playback_images)
        color_set = set()
        color_overflow=False
        for im in playback_images:
            entries=im.getcolors(256)
            if entries is None:
                color_overflow=True
                break
            color_set.update(c for _,c in entries if c[3])
            if len(color_set)>255:
                color_overflow=True
                break
        if not color_overflow and alpha_binary:
            asset = folder/"playback.gif"
            snapshot.export(asset,"gif",scale=1,tag=tag)
        else:
            asset = folder/"playback.png"
            playback_images[0].save(asset,format="PNG",save_all=True,append_images=playback_images[1:],
                duration=[snapshot.durations[f] for f in playback_frames],loop=0,disposal=2)
        ticket = {"id": review_id, "doc": snapshot, "scope": scope, "policy": policy, "analysis": analysis,
                  "content_digest": self.digest(doc), "pages": math.ceil(len(scope["frames"])/32), "seen": set(),
                  "folder": folder, "asset": asset, "submitted": None,
                  "stored_record": self.matching_record(doc,tag,layers)}
        self.tickets[review_id] = ticket
        while len(self.tickets)>4:
            self.tickets.popitem(last=False)
        return ticket

    def ticket(self, review_id, doc):
        if review_id not in self.tickets:
            raise PixelError("Review evidence expired; call pixel_review for a fresh snapshot",code="REVIEW_EXPIRED")
        ticket = self.tickets[review_id]
        if ticket["doc"].id!=doc.id or ticket["content_digest"]!=self.digest(doc):
            raise PixelError("Artwork or requirements changed after this evidence. Re-run pixel_review.",code="REVIEW_STALE")
        return ticket

    def evidence(self, ticket, page=0, mark_seen=True):
        integer(page,"page",0,ticket["pages"]-1)
        doc, scope = ticket["doc"],ticket["scope"]
        frames = scope["frames"][page*32:(page+1)*32]
        sheets = [("frame_contact",tiled_evidence(doc,frames,[f"#{f+1} {doc.durations[f]}ms" for f in frames]))]
        playback = doc.frame_indices(scope["tag"],playback=True)
        total = sum(doc.durations[f] for f in playback)
        count = min(24,max(8,len(playback)*2))
        sampled = []
        for i in range(count):
            elapsed = (i*total*2//count)%total
            cursor = 0
            for frame in playback:
                cursor += doc.durations[frame]
                if elapsed<cursor:
                    sampled.append(frame)
                    break
        if len(playback)>1:
            sheets.append(("two_loop_timing",tiled_evidence(doc,sampled,[f"{i*total*2//count}ms #{f+1}" for i,f in enumerate(sampled)])))
            edge = playback[-2:]+playback[:2]
            sheets.append(("loop_seam",tiled_evidence(doc,edge,[f"#{f+1} {doc.durations[f]}ms" for f in edge],columns=4,tile=144)))
        details=ticket["policy"]["detail_regions"]
        if not details:
            details=[name for name in doc.regions if any(key in name.lower() for key in ("cloth","face","eyes","blink","裙","衣","脸","眼"))][:2]
        for name in details[:8]:
            if name in doc.regions:
                sheets.append(("detail:"+name,tiled_evidence(doc,frames,[f"#{f+1} {doc.durations[f]}ms" for f in frames],rect=doc.regions[name])))
        if page==0 and doc.reference:
            from .reference import decoded_asset
            for key in ("subject","style"):
                if doc.reference.get(key):
                    sheets.append((key+"_reference",decoded_asset(doc.reference[key]["png"])))
        if mark_seen:
            ticket["seen"].add(page)
        data = {"ok":True,"review_id":ticket["id"],"document_id":doc.id,"revision":doc.revision,
                "page":page,"pages":ticket["pages"],"seen_pages":sorted(ticket["seen"]),"scope":scope,
                "policy":ticket["policy"],**ticket["analysis"],"image_roles":[role for role,_ in sheets],
                "playback_asset":{"path":str(ticket["asset"]),"duration_ms":total,"loop":True},
                "review_status":"visual_review_required","next_action":"Inspect all evidence pages and real timing; fix via pixel_edit, then recheck; submit conclusions with pixel_review_submit.",
                "honesty":"Frames/timing evidence is not direct playback. Report the method actually used. Numeric success alone is not an artistic pass."}
        data["sampling_notice"]="Timing sheets sample equal elapsed intervals and can miss short poses; inspect the complete contact sheets and playable loop too."
        data["existing_review_status"]=ticket["stored_record"]["status"] if ticket["stored_record"] else None
        data["previous_reviews"]=[{"status":r["status"],"summary":r["summary"],"round":r["round"],
            "remaining_findings":[c for c in r["visual_checks"] if c["verdict"]!="pass"]} for r in doc.quality_reviews[-3:]]
        return data,[im for _,im in sheets]

    def submit(self, doc, review_id, visual_checks, warning_resolutions, method, summary):
        ticket = self.ticket(review_id,doc)
        if ticket["submitted"]:
            raise PixelError("This review was already submitted; start another review after changes",code="REVIEW_ALREADY_SUBMITTED")
        if ticket["seen"]!=set(range(ticket["pages"])):
            raise PixelError("Inspect every evidence page before submitting",code="REVIEW_INCOMPLETE")
        if method not in ("frames_and_timing","playback_and_frames") or not isinstance(summary,str) or not 1<=len(summary.strip())<=2000:
            raise PixelError("State the actual viewing method and a concise conclusion",code="REVIEW_INCOMPLETE")
        analysis = ticket["analysis"]
        checks = criteria_verdicts(visual_checks,{c["id"] for c in analysis["criteria"]})
        warnings = criteria_verdicts(warning_resolutions,{w["id"] for w in analysis["warnings"]},"warning_id",("acceptable","needs_fix","uncertain"))
        status = "passed"
        if not analysis["technical_passed"] or any(c["verdict"]=="fail" for c in checks) or any(w["verdict"]=="needs_fix" for w in warnings):
            status = "needs_changes"
        elif any(c["verdict"]=="uncertain" for c in checks+warnings):
            status = "uncertain"
        policy_digest=hashlib.sha256(json.dumps(ticket["policy"],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        round_number=1
        for previous in reversed(doc.quality_reviews):
            if previous["status"]=="passed" or previous.get("policy_digest")!=policy_digest:
                break
            round_number+=1
        budget_reached=status!="passed" and round_number>=ticket["policy"]["max_rounds"]
        record = {"review_id":review_id,"content_digest":ticket["content_digest"],"scope":ticket["scope"],"status":status,
                  "method":method,"summary":summary.strip(),"visual_checks":checks,"warning_resolutions":warnings,
                  "technical_checks":analysis["technical_checks"],"metrics":analysis["metrics"],"round":round_number,"policy_digest":policy_digest,
                  "reviewed_at":datetime.now(timezone.utc).isoformat(),
                  "next_action":"save_and_export" if status=="passed" else "report_remaining_issues" if budget_reached else "edit_then_recheck",
                  "round_budget_reached":budget_reached,
                  "evidence":{"pages":ticket["pages"],"source":"actual_document_pixels_and_timing"}}
        doc.record_quality_review(record)
        ticket["submitted"] = record
        return record

    def require_pass(self, doc, tag=None, layers=None, frame=None):
        needed=[frame] if frame is not None else doc.frame_indices(tag)
        blocked=pending_feedback(doc,needed)
        if blocked:
            raise PixelError("User feedback is still open or needs rechecking after artwork changes.",code="FEEDBACK_PENDING",
                recovery="Use pixel_feedback to inspect all reported frames, ask if unclear, repair and resolve. "
                         "A human can export the current version with draft=true without claiming AI acceptance.")
        record = self.matching_record(doc,tag,layers,frame)
        if not record or record["status"]!="passed":
            raise PixelError("Final export requires a CURRENT visual self-review for these frames/layers. Numeric checks alone do not certify quality.",
                             code="REVIEW_REQUIRED",recovery="Call pixel_review, inspect all images/timing, repair via pixel_edit and recheck. Submit concrete conclusions with pixel_review_submit. Use draft=true only for clearly labeled intermediate previews.")
        return record
