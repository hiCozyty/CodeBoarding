"""CLI command to display the component hierarchy from an existing analysis."""

import argparse
import logging
from pathlib import Path

from diagram_analysis.io_utils import load_full_analysis, load_analysis_metadata
from utils import CODEBOARDING_DIR_NAME

logger = logging.getLogger(__name__)


def add_arguments(subparsers: argparse._SubParsersAction, parents: list[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "tree",
        parents=parents,
        help="Display the component hierarchy from an existing analysis.",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=None,
        help="Maximum depth to display (default: show all levels).",
    )
    parser.add_argument(
        "--component-id",
        type=str,
        default=None,
        help="Root the tree at a specific component ID (e.g. '6').",
    )


def validate_arguments(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.local is None:
        parser.error("tree requires --local")


def _depth_of(component_id: str) -> int:
    return component_id.count(".") + 1


def _build_tree(
    root_components: list,
    sub_analyses: dict,
    max_depth: int | None = None,
) -> list[tuple[str, str, bool]]:
    """Build a flat list of (component_id, name, can_expand) tuples in tree order.

    Args:
        root_components: Top-level Component objects to start from.
        sub_analyses: Mapping of component_id -> AnalysisInsights for expanded components.
        max_depth: Maximum depth to include, or None for unlimited.
    """
    result: list[tuple[str, str, bool]] = []

    def _walk(components: list, depth: int) -> None:
        if max_depth is not None and depth > max_depth:
            return
        for comp in components:
            cid = comp.component_id
            name = comp.name
            can_expand = getattr(comp, "can_expand", False) or cid in sub_analyses
            result.append((cid, name, can_expand))

            if cid in sub_analyses:
                _walk(sub_analyses[cid].components, depth + 1)

    _walk(root_components, 1)
    return result


def _print_tree(
    entries: list[tuple[str, str, bool]],
    repo_name: str,
    depth_level: int,
    root_id: str | None = None,
) -> None:
    """Print the tree with box-drawing characters."""
    header = f"{repo_name} Components (depth_level: {depth_level})"
    if root_id:
        header += f" — rooted at {root_id}"
    print(f"\n{header}")
    print("=" * len(header))

    if not entries:
        print("  (no components found)")
        return

    for i, (cid, name, can_expand) in enumerate(entries):
        depth = _depth_of(cid)

        if depth == 1:
            prefix = ""
        else:
            prefix_parts = []
            for pd in range(1, depth):
                has_sibling_below = any(_depth_of(e[0]) == pd for e in entries[i + 1 :])
                prefix_parts.append("    " if has_sibling_below else "│   ")

            has_sibling_at_same_depth = any(
                _depth_of(e[0]) == depth for e in entries[i + 1 :] if _depth_of(e[0]) >= depth
            )
            connector = "└── " if not has_sibling_at_same_depth else "├── "
            prefix = "".join(prefix_parts) + connector

        expand_marker = " [+]" if can_expand else ""
        print(f"{prefix}{cid}: {name}{expand_marker}")


def run_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    validate_arguments(args, parser)

    repo_path = args.local.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else repo_path / CODEBOARDING_DIR_NAME

    if not output_dir.exists():
        print(f"Error: No analysis directory found at {output_dir}")
        print("Run a full analysis first: uv run python main.py full --local <repo>")
        raise SystemExit(1)

    metadata = load_analysis_metadata(output_dir)
    if metadata is None:
        print(f"Error: No analysis.json found in {output_dir}")
        print("Run a full analysis first.")
        raise SystemExit(1)

    depth_level = int(metadata.get("depth_level", 1))
    repo_name = metadata.get("repo_name", repo_path.name)

    full_result = load_full_analysis(output_dir)
    if full_result is None:
        print(f"Error: Could not parse analysis.json in {output_dir}")
        raise SystemExit(1)

    root_analysis, sub_analyses = full_result

    root_components = list(root_analysis.components)

    if args.component_id:
        found = None
        for comp in root_components:
            if comp.component_id == args.component_id:
                found = comp
                break
        if found is None:
            for sub in sub_analyses.values():
                for comp in sub.components:
                    if comp.component_id == args.component_id:
                        found = comp
                        break
                if found is not None:
                    break
        if found is None:
            print(f"Error: Component '{args.component_id}' not found in analysis")
            raise SystemExit(1)
        root_components = [found]

    entries = _build_tree(root_components, sub_analyses, max_depth=args.depth)
    _print_tree(entries, repo_name, depth_level, root_id=args.component_id)
