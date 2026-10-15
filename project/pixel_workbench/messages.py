"""Actionable desktop messages; MCP retains its structured diagnostic details."""
from __future__ import annotations


def user_error(error):
    messages = {
        "UNSAVED_CHANGES": "当前作品有未保存修改，请先保存；需要替换时，请重新选择是否保留当前作品。",
        "REVISION_CONFLICT": "作品刚刚被更新，请查看当前画面后重试。",
        "DOCUMENT_CONFLICT": "当前工程已切换，请在目标工程中重新操作。",
        "REFERENCE_CONFLICT": "参考图或参数已更新，请刷新参考窗口后重试。",
        "EDITOR_BUSY": "请先完成当前笔画或路径，再执行此操作。",
        "LAYER_LOCKED": "当前图层已锁定，请先解锁或选择其他图层。",
        "FILE_EXISTS": "目标文件已存在，请换一个文件名，或确认覆盖。",
        "PROJECT_FILE_CHANGED": "工程文件已被其他程序修改，请另存为新文件，或重新打开后继续。",
        "REFERENCE_REQUIRED": "请先导入普通原图，再生成像素底稿。",
        "REVIEW_REQUIRED": "此范围尚未通过成品检查，请先复查，或选择直接导出当前版本。",
        "REVIEW_STALE": "作品已修改，原检查结果已过期，请重新检查。",
    }
    code = getattr(error, "code", None)
    if code in messages:
        return messages[code]
    detail = str(error)
    if "Palette already has 256 colors" in detail:
        return "调色板已满（最多 256 色）。请减少颜色，或关闭颜色约束后粘贴原始像素。"
    if "outside the palette" in detail or "outside the new palette" in detail:
        return "所选颜色不在调色板内，请先添加颜色，或选择重新映射颜色。"
    if "16M" in detail:
        return "输出超过 16M 像素，请降低导出倍数，或缩小动作范围。"
    if "capacity exceeded" in detail:
        return "工程容量已达上限，请减少图层、帧数或画布尺寸后重试。"
    if "No layer exists below" in detail:
        return "当前已是最下层，无法继续向下合并。"
    if "Cannot delete the final" in detail:
        return "工程至少需要保留一个图层和一帧。"
    if isinstance(error, PermissionError):
        return "文件无法写入，请关闭占用它的程序，或选择其他保存目录。"
    return detail
