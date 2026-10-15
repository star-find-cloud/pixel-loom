"""Windows image clipboard: PNG (metadata) plus CF_DIB (broad paste support)."""
from __future__ import annotations

import io
import sys
import time


def dib_bytes(image):
    output=io.BytesIO()
    image.convert("RGB").save(output,format="BMP")
    return output.getvalue()[14:]


def copy_image(image,png_data,owner_window):
    if sys.platform!="win32":
        raise OSError("自动复制图片目前支持 Windows；PNG 已保存在本地，可直接发送。")
    import ctypes
    from ctypes import wintypes
    user=ctypes.WinDLL("user32",use_last_error=True)
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    user.OpenClipboard.argtypes=[wintypes.HWND]
    user.OpenClipboard.restype=wintypes.BOOL
    user.EmptyClipboard.restype=wintypes.BOOL
    user.CloseClipboard.restype=wintypes.BOOL
    user.RegisterClipboardFormatW.argtypes=[wintypes.LPCWSTR]
    user.RegisterClipboardFormatW.restype=wintypes.UINT
    user.SetClipboardData.argtypes=[wintypes.UINT,wintypes.HANDLE]
    user.SetClipboardData.restype=wintypes.HANDLE
    kernel.GlobalAlloc.argtypes=[wintypes.UINT,ctypes.c_size_t]
    kernel.GlobalAlloc.restype=wintypes.HANDLE
    kernel.GlobalLock.argtypes=[wintypes.HANDLE]
    kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[wintypes.HANDLE]
    kernel.GlobalUnlock.restype=wintypes.BOOL
    kernel.GlobalFree.argtypes=[wintypes.HANDLE]
    kernel.GlobalFree.restype=wintypes.HANDLE
    handles=[]
    opened=False
    formats=[]
    try:
        png_format=user.RegisterClipboardFormatW("PNG")
        payloads=[(8,dib_bytes(image),"CF_DIB")]
        if png_format:payloads.append((png_format,png_data,"PNG"))
        for number,raw,name in payloads:
            handle=kernel.GlobalAlloc(0x0002,len(raw))
            if not handle:raise OSError("无法为剪贴板分配图片内存。")
            handles.append([number,handle,name])
            memory=kernel.GlobalLock(handle)
            if not memory:raise OSError("无法写入剪贴板图片内存。")
            ctypes.memmove(memory,raw,len(raw))
            kernel.GlobalUnlock(handle)
        for _ in range(12):
            if user.OpenClipboard(owner_window):
                opened=True
                break
            time.sleep(.025)
        if not opened:raise OSError("剪贴板正被其他程序占用；截图已保存，请稍后重试复制。")
        if not user.EmptyClipboard():raise OSError("无法打开图片剪贴板。截图已保存。")
        for entry in handles:
            if user.SetClipboardData(entry[0],entry[1]):
                formats.append(entry[2])
                entry[1]=None  # Windows now owns this allocation.
            elif entry[2]=="CF_DIB":
                raise OSError("图片未能复制到剪贴板，截图已保存在本地。")
        return {"copied":True,"formats":formats,"png_metadata_available":"PNG" in formats}
    finally:
        if opened:user.CloseClipboard()
        for _,handle,_ in handles:
            if handle:kernel.GlobalFree(handle)
