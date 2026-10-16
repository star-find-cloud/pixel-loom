"""Read public release metadata without accessing artwork or client configuration."""
from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from . import __version__

REPOSITORY = "yangsir2077/pixel-loom"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=100"
MAX_RESPONSE_BYTES = 2_000_000
CHECK_INTERVAL = 24 * 60 * 60


class UpdateError(ValueError):
    pass


@total_ordering
@dataclass(frozen=True)
class Version:
    core: tuple[int, int, int]
    prerelease: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text):
        if not isinstance(text, str) or len(text) > 100:
            raise ValueError("Invalid release version")
        match = re.fullmatch(r"[vV]?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
                             r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
                             r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", text)
        if not match:
            raise ValueError("Invalid release version")
        identifiers = tuple(match[4].split(".")) if match[4] else ()
        if any(item.isdigit() and len(item) > 1 and item.startswith("0") for item in identifiers):
            raise ValueError("Invalid release version")
        return cls(tuple(int(match[i]) for i in (1, 2, 3)), identifiers)

    def __lt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        if self.core != other.core:
            return self.core < other.core
        if not self.prerelease or not other.prerelease:
            return bool(self.prerelease) and not other.prerelease
        for left, right in zip(self.prerelease, other.prerelease):
            if left == right:
                continue
            if left.isdigit() and right.isdigit():
                return int(left) < int(right)
            if left.isdigit() != right.isdigit():
                return left.isdigit()
            return left < right
        return len(self.prerelease) < len(other.prerelease)


def release_page(tag=None):
    if tag is None:
        return RELEASES_URL
    Version.parse(tag)
    return f"{RELEASES_URL}/tag/{quote(tag, safe='')}"


def expected_download_url(tag):
    Version.parse(tag)
    number = tag[1:] if tag[:1].lower() == "v" else tag
    filename = f"pixel-loom-{number}-windows-x64.zip"
    return f"{RELEASES_URL}/download/{quote(tag, safe='')}/{quote(filename, safe='')}"


def valid_download_url(url, tag):
    try:
        return isinstance(url, str) and url == expected_download_url(tag)
    except ValueError:
        return False


@dataclass(frozen=True)
class Release:
    tag: str
    version: Version
    name: str
    notes: str
    prerelease: bool
    download_url: str | None = None
    download_bytes: int | None = None

    @property
    def number(self):
        return self.tag[1:] if self.tag[:1].lower() == "v" else self.tag

    @property
    def page_url(self):
        return release_page(self.tag)


def select_release(data, include_prereleases=True):
    if not isinstance(data, list):
        raise UpdateError("版本服务返回了无法识别的数据，请打开发版页面查看。")
    releases = []
    for item in data:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        try:
            tag = item["tag_name"]
            version = Version.parse(tag)
        except (KeyError, ValueError):
            continue
        preview = bool(item.get("prerelease")) or bool(version.prerelease)
        if preview and not include_prereleases:
            continue
        download, size = None, None
        assets = item.get("assets", [])
        for asset in assets if isinstance(assets, list) else ():
            if not isinstance(asset, dict) or asset.get("state") != "uploaded":
                continue
            if valid_download_url(asset.get("browser_download_url"), tag):
                download = expected_download_url(tag)
                value = asset.get("size")
                size = value if type(value) is int and value > 0 else None
                break
        name, notes = item.get("name"), item.get("body")
        releases.append(Release(tag, version, name[:200] if isinstance(name, str) else tag,
                                notes[:20_000] if isinstance(notes, str) else "", preview, download, size))
    return max(releases, key=lambda item: item.version, default=None)


def fetch_latest(include_prereleases=True, opener=None):
    request = Request(API_URL, headers={"Accept": "application/vnd.github+json",
                                      "User-Agent": f"PixelLoom/{__version__}"})
    try:
        with (opener or urlopen)(request, timeout=8) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise UpdateError("版本信息过大，请打开发版页面查看。")
        return select_release(json.loads(payload), include_prereleases)
    except HTTPError as exc:
        if exc.code in (403, 429):
            raise UpdateError("版本服务暂时限制了查询，请稍后重试，或直接打开发版页面。") from exc
        raise UpdateError("暂时无法访问发布信息，请稍后重试，或直接打开发版页面。") from exc
    except (URLError, OSError) as exc:
        raise UpdateError("无法连接更新服务，请检查网络，或直接打开发版页面。") from exc
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError("版本信息暂时不可用，请稍后重试，或直接打开发版页面。") from exc
