"""Agent interface: python -m pixel_workbench.cli --help."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .paths import SESSION


class RemoteError(RuntimeError):
    def __init__(self, data):
        super().__init__(data.get("error", "Request failed"))
        self.code = data.get("code", "REMOTE_ERROR")
        self.recovery = data.get("recovery")
        self.details = data.get("details")


class Client:
    def __init__(self, session_path=SESSION):
        try:
            session = json.loads(Path(session_path).read_text(encoding="utf-8"))
            self.url, self.token = session["url"], session["token"]
            parsed = urllib.parse.urlparse(self.url)
            if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
                raise ValueError("Session bridge must be a local loopback URL")
            self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        except (OSError, ValueError, KeyError) as exc:
            raise RuntimeError("Pixel Loom is not running. Start pixel-loom, or connect with pixel-loom-mcp for automatic startup.") from exc

    def request(self, endpoint, payload=None, query=None, timeout=25):
        url = self.url + endpoint
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        request = urllib.request.Request(url, headers={"X-Pixel-Loom-Token": self.token})
        if payload is not None:
            request.data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(request, timeout=timeout) as response:
                body = response.read()
                return body if "image/png" in response.headers.get("Content-Type", "") else json.loads(body)
        except urllib.error.HTTPError as exc:
            result = json.loads(exc.read())
            raise RemoteError(result) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Cannot reach Pixel Loom; start the editor and try again.") from exc

    def mutate(self, endpoint, payload=None, revision=None, document_id=None):
        state = self.request("/state")
        payload = dict(payload or {})
        # Explicit stale revisions are retained so saved plans fail safely.
        payload.setdefault("expected_revision", state["revision"] if revision is None else revision)
        payload.setdefault("expected_document_id", state["document_id"] if document_id is None else document_id)
        return self.request(endpoint, payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pixel Loom — precise agent control for the live editor")
    parser.add_argument("--session", type=Path, default=SESSION, help="Path to local bridge session file")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Read layers, frames, palette, semantic regions and revision")
    commands.add_parser("schema", help="Read command examples and coordinate rules")
    apply = commands.add_parser("apply", help="Apply an atomic batch from JSON; '-' reads stdin")
    apply.add_argument("file")
    apply.add_argument("--label", default="AI 绘图")
    apply.add_argument("--revision", type=int)
    apply.add_argument("--document-id")
    inspect = commands.add_parser("inspect", help="Read exact pixels as a color legend and text grid")
    inspect.add_argument("--rect", nargs=4, type=int, metavar=("X", "Y", "W", "H"))
    inspect.add_argument("--region")
    inspect.add_argument("--layer")
    inspect.add_argument("--frame", type=int)
    preview = commands.add_parser("preview", help="Save an enlarged nearest-neighbor preview for visual inspection")
    preview.add_argument("output", type=Path)
    preview.add_argument("--scale", type=int, default=8)
    preview.add_argument("--frame", type=int)
    preview.add_argument("--rect", nargs=4, type=int)
    preview.add_argument("--transparent", action="store_true")
    export = commands.add_parser("export")
    export.add_argument("output", type=Path)
    export.add_argument("--kind", choices=("png", "sheet", "gif"), default="png")
    export.add_argument("--scale", type=int, default=1)
    export.add_argument("--columns", type=int)
    export.add_argument('--sheet-format',choices=('native','aseprite_hash','aseprite_array','godot'),default='native')
    export.add_argument('--tag',help='Export one named animation action')
    export.add_argument('--overwrite',action='store_true',help='Replace all files belonging to this export bundle')
    export.add_argument("--draft",action="store_true",help="Export an explicitly unreviewed intermediate")
    for name in ("save", "open", "import"):
        action = commands.add_parser(name)
        action.add_argument("path", type=Path)
    new = commands.add_parser("new")
    new.add_argument("width", type=int)
    new.add_argument("height", type=int)
    new.add_argument("--name", default="未命名作品")
    commands.add_parser("undo")
    commands.add_parser("redo")
    args = parser.parse_args(argv)
    try:
        client = Client(args.session)
        if args.command == "status":
            result = client.request("/state")
        elif args.command == "schema":
            result = client.request("/schema")
        elif args.command == "apply":
            raw = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8-sig")
            data = json.loads(raw)
            payload = {"ops": data, "label": args.label} if isinstance(data, list) else data
            payload.setdefault("label", args.label)
            result = client.mutate("/command", payload, args.revision, args.document_id)
        elif args.command == "inspect":
            result = client.request("/inspect", query={"rect": ",".join(map(str, args.rect)) if args.rect else None,
                                                       "region": args.region, "layer": args.layer, "frame": args.frame})
        elif args.command == "preview":
            data = client.request("/preview.png", query={"scale": args.scale, "frame": args.frame,
                                                          "rect": ",".join(map(str, args.rect)) if args.rect else None,
                                                          "checker": 0 if args.transparent else 1})
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
            result = {"ok": True, "path": str(args.output.resolve())}
        elif args.command == "export":
            result = client.mutate("/export", {"path": str(args.output.resolve()), "kind": args.kind,
                                                "scale": args.scale, "columns": args.columns, "draft":args.draft,
                                                'sheet_format':args.sheet_format,'tag':args.tag,'overwrite':args.overwrite})
        elif args.command in ("save", "open", "import"):
            result = client.mutate("/" + args.command, {"path": str(args.path.resolve())})
        elif args.command == "new":
            result = client.mutate("/new", {"width": args.width, "height": args.height, "name": args.name})
        else:
            result = client.mutate("/" + args.command)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RuntimeError, ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
