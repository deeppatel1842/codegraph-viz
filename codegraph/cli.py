"""CLI interface for codegraph.

Commands:
    codegraph scan [path]      Scan project, generate graph, open in browser
    codegraph serve [path]     Start HTTP server with live-reload
    codegraph info [path]      Show project summary (files, lines, modules, security)
    codegraph export [path]    Export token-efficient JSON index for LLM consumption

All commands default to the current directory. Output goes to .codegraph/
unless overridden with -o/--output.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from codegraph import __version__


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="codegraph",
        description="Visualize any Python codebase as an interactive dependency graph",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")

    # scan
    scan_p = sub.add_parser("scan", help="Scan project and open interactive graph")
    scan_p.add_argument("path", nargs="?", default=".", help="Project root directory")
    scan_p.add_argument("-o", "--output", default=".codegraph",
                        help="Output directory for generated files")
    scan_p.add_argument("--no-open", action="store_true", help="Don't open browser")

    # serve
    serve_p = sub.add_parser("serve", help="Start HTTP server with live-reload")
    serve_p.add_argument("path", nargs="?", default=".", help="Project root directory")
    serve_p.add_argument("-o", "--output", default=".codegraph",
                         help="Output directory")
    serve_p.add_argument("-p", "--port", type=int, default=7788, help="Server port")
    serve_p.add_argument("--interval", type=float, default=5.0,
                         help="Watch interval in seconds")

    # info
    info_p = sub.add_parser("info", help="Show project summary")
    info_p.add_argument("path", nargs="?", default=".", help="Project root directory")

    # export
    export_p = sub.add_parser("export", help="Export file index JSON")
    export_p.add_argument("path", nargs="?", default=".", help="Project root directory")
    export_p.add_argument("--compact", action="store_true", help="Compact JSON output")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "export":
        cmd_export(args)


def cmd_scan(args):
    from codegraph.scanner import scan_project
    from codegraph.server import _write_outputs

    project_root = Path(args.path).resolve()
    output_dir = project_root / args.output

    print(f"Scanning {project_root}...")
    graph = scan_project(project_root)
    _write_outputs(output_dir, graph)

    stats = graph["stats"]
    print(f"Generated: {stats['total_files']} files, {stats['total_lines']} lines, "
          f"{stats['total_edges']} edges")
    print(f"Modules: {', '.join(sorted(stats['modules'].keys()))}")
    print(f"Output: {output_dir}")

    html_path = output_dir / "graph.html"
    if not args.no_open and html_path.exists():
        webbrowser.open(str(html_path))
        print(f"Opened {html_path} in browser")


def cmd_serve(args):
    from codegraph.server import serve_with_watch

    project_root = Path(args.path).resolve()
    output_dir = project_root / args.output

    serve_with_watch(
        project_root=project_root,
        output_dir=output_dir,
        port=args.port,
        interval=args.interval,
    )


def cmd_info(args):
    from codegraph.scanner import scan_project

    project_root = Path(args.path).resolve()
    print(f"Scanning {project_root}...")
    graph = scan_project(project_root)
    stats = graph["stats"]

    print(f"\n{'=' * 50}")
    print(f"Project: {project_root.name}")
    print(f"{'=' * 50}")
    print(f"Files:   {stats['total_files']}")
    print(f"Lines:   {stats['total_lines']:,}")
    print(f"Edges:   {stats['total_edges']}")
    print(f"{'=' * 50}")
    print("\nModules:")
    for mod in sorted(stats["modules"]):
        m = stats["modules"][mod]
        bar = "#" * min(40, m["lines"] // 100)
        print(f"  {mod:20s} {m['files']:3d} files  {m['lines']:6,} lines  {bar}")

    # Security summary
    print("\nSecurity Signals:")
    for node in graph["nodes"]:
        path = node["path"]
        src = node.get("source", "")
        if "eval(" in src or "exec(" in src:
            print(f"  WARNING: {path} — contains eval/exec")
        if "os.system(" in src or "subprocess.call(" in src:
            print(f"  WARNING: {path} — shell command execution")
        if "SECRET" in src or "PASSWORD" in src or "API_KEY" in src:
            if "test" not in path.lower() and "settings" not in path.lower():
                print(f"  WARNING: {path} — possible hardcoded secret")


def cmd_export(args):
    from codegraph.scanner import scan_project, build_file_index

    project_root = Path(args.path).resolve()
    graph = scan_project(project_root)
    index = build_file_index(graph)

    indent = None if args.compact else 2
    json.dump(index, sys.stdout, indent=indent)
    print()  # trailing newline


if __name__ == "__main__":
    main()
