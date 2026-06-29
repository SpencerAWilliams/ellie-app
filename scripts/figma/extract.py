"""
extract.py — Figma design schema assembler
Usage: python extract.py <file_key> [--node <node_id>]

Reads:
  /tmp/figma_file.json        (single Figma API response — includes styles)
  /tmp/figma_images_svg.json  (optional)
  /tmp/figma_images_png.json  (optional)

Writes:
  /tmp/figma_schema.json      (clean design schema for Claude to consume)

Note: styles are extracted directly from figma_file.json — no separate
styles endpoint call needed, which reduces API usage from 3 calls to 1.
"""

import json
import sys
import argparse
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rgba_to_hex(r, g, b, a=1.0):
    """Convert Figma's 0-1 float RGBA to a CSS hex string."""
    ri, gi, bi = int(round(r * 255)), int(round(g * 255)), int(round(b * 255))
    if a < 0.999:
        ai = int(round(a * 255))
        return f"#{ri:02X}{gi:02X}{bi:02X}{ai:02X}"
    return f"#{ri:02X}{gi:02X}{bi:02X}"


def slugify(name):
    """Turn a Figma style name like 'Brand / Primary' into 'brand-primary'."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def figma_align_to_css(value):
    mapping = {
        "MIN": "flex-start",
        "CENTER": "center",
        "MAX": "flex-end",
        "SPACE_BETWEEN": "space-between",
        "BASELINE": "baseline",
    }
    return mapping.get(value, "flex-start")


def px(value):
    return f"{round(value)}px"


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------

def extract_tokens(file_data):
    """
    Build the tokens dict from styles embedded in the file response.
    The /v1/files/:file_key response includes a top-level 'styles' dict
    mapping node IDs to style metadata — no separate styles endpoint needed.
    """
    tokens = {"colors": {}, "typography": {}, "spacing": {}, "radii": {}, "shadows": {}}

    # styles dict maps node_id -> { name, styleType, ... }
    file_styles = file_data.get("styles", {})

    # Build a lookup of node_id -> style name for use during tree walk
    style_id_to_name = {
        node_id: meta["name"]
        for node_id, meta in file_styles.items()
    }
    style_id_to_type = {
        node_id: meta.get("styleType", "")
        for node_id, meta in file_styles.items()
    }

    # Register placeholders for each published style so we can fill values
    # during the tree walk
    for node_id, meta in file_styles.items():
        style_type = meta.get("styleType", "")
        slug = slugify(meta["name"])
        if style_type == "FILL":
            tokens["colors"][f"--color-{slug}"] = None
        elif style_type == "TEXT":
            tokens["typography"][f"--font-family-{slug}"] = None
            tokens["typography"][f"--font-size-{slug}"] = None
            tokens["typography"][f"--font-weight-{slug}"] = None
            tokens["typography"][f"--line-height-{slug}"] = None

    unnamed_color_index = [1]  # mutable for closure

    def walk(node):
        style_refs = node.get("styles", {})
        fills = node.get("fills", [])

        # Resolve color fills
        if fills and fills[0].get("type") == "SOLID":
            c = fills[0]["color"]
            hex_val = rgba_to_hex(c["r"], c["g"], c["b"], c.get("a", 1.0))
            if "fill" in style_refs:
                sid = style_refs["fill"]
                sname = style_id_to_name.get(sid)
                if sname:
                    key = f"--color-{slugify(sname)}"
                    if key in tokens["colors"]:
                        tokens["colors"][key] = hex_val
            else:
                # Inline fill — add if not already seen
                if hex_val not in tokens["colors"].values():
                    tokens["colors"][f"--color-inline-{unnamed_color_index[0]}"] = hex_val
                    unnamed_color_index[0] += 1

        # Resolve text styles
        if node.get("type") == "TEXT":
            ts = node.get("style", {})
            if "text" in style_refs:
                sid = style_refs["text"]
                sname = style_id_to_name.get(sid)
                if sname:
                    slug = slugify(sname)
                    tokens["typography"][f"--font-family-{slug}"] = (
                        ts.get("fontFamily", "sans-serif") + ", sans-serif"
                    )
                    tokens["typography"][f"--font-size-{slug}"] = px(ts.get("fontSize", 16))
                    tokens["typography"][f"--font-weight-{slug}"] = str(ts.get("fontWeight", 400))
                    lh = ts.get("lineHeightPx")
                    fs = ts.get("fontSize")
                    tokens["typography"][f"--line-height-{slug}"] = (
                        f"{round(lh / fs, 2)}" if lh and fs else "1.5"
                    )

        # Collect border radii
        radius = node.get("cornerRadius")
        if radius and radius > 0:
            key = f"--radius-{round(radius)}"
            tokens["radii"][key] = px(radius)

        # Collect box shadows
        for i, effect in enumerate(node.get("effects", [])):
            if effect.get("type") in ("DROP_SHADOW", "INNER_SHADOW") and effect.get("visible", True):
                c = effect.get("color", {})
                hex_c = rgba_to_hex(
                    c.get("r", 0), c.get("g", 0), c.get("b", 0), c.get("a", 0.15)
                )
                ox = round(effect.get("offset", {}).get("x", 0))
                oy = round(effect.get("offset", {}).get("y", 0))
                blur = round(effect.get("radius", 4))
                spread = round(effect.get("spread", 0))
                prefix = "inset " if effect["type"] == "INNER_SHADOW" else ""
                tokens["shadows"][f"--shadow-{i + 1}"] = (
                    f"{prefix}{ox}px {oy}px {blur}px {spread}px {hex_c}"
                )

        for child in node.get("children", []):
            walk(child)

    root = file_data.get("document", file_data)
    walk(root)

    # Drop any color placeholders that were never resolved during tree walk
    tokens["colors"] = {k: v for k, v in tokens["colors"].items() if v is not None}

    # Derive spacing scale from smallest gap found in auto-layout frames
    gaps = []

    def collect_gaps(node):
        if node.get("layoutMode", "NONE") != "NONE":
            gap = node.get("itemSpacing", 0)
            if gap > 0:
                gaps.append(gap)
        for child in node.get("children", []):
            collect_gaps(child)

    collect_gaps(root)

    if gaps:
        base = max(min(gaps), 4)  # M3 uses a 4px base grid; sub-4 gaps are state-layer internals
        for mult, name in [(1, "xs"), (2, "sm"), (3, "md"), (4, "lg"), (6, "xl"), (8, "2xl")]:
            tokens["spacing"][f"--space-{name}"] = px(base * mult)
    else:
        for val, name in [(4, "xs"), (8, "sm"), (16, "md"), (24, "lg"), (32, "xl"), (48, "2xl")]:
            tokens["spacing"][f"--space-{name}"] = px(val)

    return tokens


# ---------------------------------------------------------------------------
# Tree extraction
# ---------------------------------------------------------------------------

IGNORED_PREFIXES = ("_", "[annotation]", "⚠", "📐")
IGNORED_TYPES = ("SLICE",)


def should_ignore(node):
    name = node.get("name", "")
    if not node.get("visible", True):
        return True
    if node.get("type") in IGNORED_TYPES:
        return True
    if any(name.startswith(p) for p in IGNORED_PREFIXES):
        return True
    return False


def infer_html_tag(name, node_type="FRAME"):
    n = name.lower()
    if any(k in n for k in ("button", "cta", "btn")):
        return "button"
    if any(k in n for k in ("input", "field", "textfield", "text-field")):
        return "input"
    # Avatar is a styled container, not a media element
    if "avatar" in n:
        return "div"
    if any(k in n for k in ("image", "img", "photo", "thumbnail")):
        return "img"
    # Heading and inline tags only apply to TEXT nodes — applying them to FRAME
    # containers causes invalid nesting (block elements inside <p>, nested <h2>)
    if node_type == "TEXT":
        if any(k in n for k in ("h1", "heading-1", "display")):
            return "h1"
        if any(k in n for k in ("h2", "heading-2")):
            return "h2"
        if any(k in n for k in ("h3", "heading-3")):
            return "h3"
        if any(k in n for k in ("label", "caption", "overline")):
            return "span"
        if any(k in n for k in ("paragraph", "body", "description", "supporting")):
            return "p"
        return "span"  # safe default; <p> adds browser margin that breaks component layouts
    # Structural container tags for non-text nodes
    if any(k in n for k in ("nav", "navigation", "navbar")):
        return "nav"
    if any(k in n for k in ("header",)):
        return "header"
    if any(k in n for k in ("footer",)):
        return "footer"
    # "list" only — "ul"/"ol" are too short and match substrings like "column", "scroll"
    if "list" in n:
        return "ul"
    if any(k in n for k in ("section",)):
        return "section"
    if any(k in n for k in ("card",)):
        return "article"
    return "div"


# ---------------------------------------------------------------------------
# Icon name resolution
# ---------------------------------------------------------------------------

_ICON_PATTERNS = [
    re.compile(r'\bicon=([a-z][a-z0-9_]+)', re.IGNORECASE),
    re.compile(r'icons?/(?:\d+/)?([a-z][a-z0-9_]+)$', re.IGNORECASE),
    re.compile(r'material.?symbols?/([a-z][a-z0-9_]+)$', re.IGNORECASE),
]

def extract_icon_name(name):
    """Return a Material Symbols glyph name encoded in a Figma component name, or None."""
    if not name:
        return None
    for pat in _ICON_PATTERNS:
        m = pat.search(name)
        if m:
            return m.group(1).lower()
    return None


def extract_layout(node):
    layout_mode = node.get("layoutMode", "NONE")
    if layout_mode == "NONE":
        return None
    return {
        "direction": "row" if layout_mode == "HORIZONTAL" else "column",
        "gap": node.get("itemSpacing", 0),
        "padding": [
            node.get("paddingTop", 0),
            node.get("paddingRight", 0),
            node.get("paddingBottom", 0),
            node.get("paddingLeft", 0),
        ],
        "justify_content": figma_align_to_css(node.get("primaryAxisAlignItems", "MIN")),
        "align_items": figma_align_to_css(node.get("counterAxisAlignItems", "MIN")),
        "wrap": node.get("layoutWrap") == "WRAP",
    }


def extract_size(node):
    h_sizing = node.get("layoutSizingHorizontal", "FIXED")
    v_sizing = node.get("layoutSizingVertical", "FIXED")
    bbox = node.get("absoluteBoundingBox", {})
    w = bbox.get("width")
    h = bbox.get("height")
    return {
        "width": "100%" if h_sizing == "FILL" else ("fit-content" if h_sizing == "HUG" else (px(w) if w else None)),
        "height": "auto" if v_sizing == "HUG" else (px(h) if h else None),
        "flex": "1" if h_sizing == "FILL" else None,
    }


def is_image_node(node):
    fills = node.get("fills", [])
    return bool(fills and fills[0].get("type") == "IMAGE")


def build_tree(node, image_node_ids, components=None):
    if should_ignore(node):
        return None

    node_type = node.get("type", "")
    result = {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node_type,
        "tag": infer_html_tag(node.get("name", ""), node_type),
    }

    layout = extract_layout(node)
    if layout:
        result["layout"] = layout

    result["size"] = extract_size(node)

    if node_type == "TEXT":
        result["content"] = node.get("characters", "")
        ts = node.get("style", {})
        color = None
        if node.get("fills") and node["fills"][0].get("type") == "SOLID":
            c = node["fills"][0]["color"]
            color = rgba_to_hex(c["r"], c["g"], c["b"], c.get("a", 1.0))
        result["text_style"] = {
            "font_family": ts.get("fontFamily"),
            "font_size": ts.get("fontSize"),
            "font_weight": ts.get("fontWeight"),
            "line_height_px": ts.get("lineHeightPx"),
            "text_align": ts.get("textAlignHorizontal", "LEFT").lower(),
            "color": color,
        }

    if is_image_node(node):
        image_node_ids.append(node["id"])
        result["is_image"] = True

    radius = node.get("cornerRadius")
    if radius:
        result["border_radius"] = px(radius)

    opacity = node.get("opacity", 1.0)
    if opacity < 0.999:
        result["opacity"] = round(opacity, 2)

    if node_type in ("COMPONENT", "INSTANCE"):
        result["component_name"] = node.get("name")
        if node_type == "INSTANCE":
            comp_id = node.get("componentId", "")
            result["component_id"] = comp_id
            master_name = (components or {}).get(comp_id, {}).get("name", "")
            icon_name = extract_icon_name(master_name) or extract_icon_name(node.get("name", ""))
            if icon_name:
                result["icon_name"] = icon_name
                result["tag"] = "span"

    raw_children = sorted(
        node.get("children", []),
        key=lambda c: (
            c.get("absoluteBoundingBox", {}).get("y", 0),
            c.get("absoluteBoundingBox", {}).get("x", 0),
        ),
    )
    children = [
        build_tree(child, image_node_ids, components)
        for child in raw_children
    ]
    children = [c for c in children if c is not None]
    if children:
        result["children"] = children

    return result


# ---------------------------------------------------------------------------
# Asset URL merging
# ---------------------------------------------------------------------------

def load_asset_urls():
    assets = {}
    for path in ("/tmp/figma_images_svg.json", "/tmp/figma_images_png.json"):
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text())
            for node_id, url in data.get("images", {}).items():
                if url:
                    clean_id = node_id.replace(":", "-")
                    if clean_id not in assets or path.endswith("svg.json"):
                        assets[clean_id] = url
    return assets


def label_image_assets(tree, image_node_ids, asset_urls):
    if not tree:
        return
    if tree.get("is_image"):
        clean_id = tree["id"].replace(":", "-")
        url = asset_urls.get(clean_id)
        if url:
            tree["asset_url"] = url
    for child in tree.get("children", []):
        label_image_assets(child, image_node_ids, asset_urls)


def count_nodes(node):
    if not node:
        return 0
    return 1 + sum(count_nodes(c) for c in node.get("children", []))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Assemble Figma design schema")
    parser.add_argument("file_key", help="Figma file key")
    parser.add_argument("--node", help="Target node ID (optional)", default=None)
    parser.add_argument("--out", help="Output path", default="/tmp/figma_schema.json")
    args = parser.parse_args()

    raw_path = Path("/tmp/figma_nodes.json" if args.node else "/tmp/figma_file.json")
    if not raw_path.exists():
        print(f"ERROR: {raw_path} not found.", file=sys.stderr)
        sys.exit(1)

    file_data = json.loads(raw_path.read_text())

    # Check for API error responses
    if "status" in file_data and file_data.get("status") != 200:
        status = file_data.get("status")
        err = file_data.get("err", "unknown error")
        print(f"ERROR: Figma API returned error {status}: {err}", file=sys.stderr)
        sys.exit(1)

    # Resolve target node
    if args.node:
        node_id = args.node.replace("-", ":")
        nodes = file_data.get("nodes", {})
        target = nodes.get(node_id, nodes.get(args.node, {})).get("document")
        if not target:
            print(f"ERROR: Node {args.node} not found in figma_nodes.json", file=sys.stderr)
            sys.exit(1)
        component_name = target.get("name", "Component")
        # Inject styles from the nodes response for token extraction
        file_data_for_tokens = {"document": target, "styles": file_data.get("styles", {})}
    else:
        doc = file_data.get("document", {})
        pages = doc.get("children", [])
        if not pages:
            print("ERROR: No pages found in Figma file.", file=sys.stderr)
            sys.exit(1)
        first_page = pages[0]
        frames = [n for n in first_page.get("children", []) if n.get("type") == "FRAME"]
        if not frames:
            print("ERROR: No top-level frames found. Specify --node to target a component.", file=sys.stderr)
            sys.exit(1)
        if len(frames) > 1:
            names = ", ".join(f["name"] for f in frames)
            print(f"INFO: Multiple frames found: {names}", file=sys.stderr)
            def descendant_count(node):
                return sum(1 + descendant_count(c) for c in node.get("children", []))
            frames.sort(key=descendant_count, reverse=True)
            print(f"INFO: Using frame with most content: {frames[0]['name']}", file=sys.stderr)
            print(f"INFO: Use --node <id> to target a specific frame.", file=sys.stderr)
        target = frames[0]
        component_name = target.get("name", "Component")
        file_data_for_tokens = file_data

    tokens = extract_tokens(file_data_for_tokens)

    # Build master-component name lookup for icon resolution
    components = {
        cid: {"name": meta.get("name", "")}
        for cid, meta in file_data.get("components", {}).items()
    }

    image_node_ids = []
    tree = build_tree(target, image_node_ids, components)

    asset_urls = load_asset_urls()
    label_image_assets(tree, image_node_ids, asset_urls)

    schema = {
        "meta": {
            "file_key": args.file_key,
            "target_node": args.node,
            "component_name": component_name,
            "source": "figma-rest-api",
        },
        "tokens": tokens,
        "tree": tree,
        "assets": asset_urls,
        "image_node_ids": image_node_ids,
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(schema, indent=2))
    print(f"Schema written to {out_path}")
    print(f"  Colors:     {len(tokens['colors'])}")
    print(f"  Typography: {len(tokens['typography']) // 4} styles")
    print(f"  Spacing:    {len(tokens['spacing'])} steps")
    print(f"  Shadows:    {len(tokens['shadows'])}")
    print(f"  Assets:     {len(asset_urls)}")
    def count_icons(node):
        if not node:
            return 0
        return (1 if node.get("icon_name") else 0) + sum(count_icons(c) for c in node.get("children", []))

    print(f"  Tree nodes: {count_nodes(tree)}")
    print(f"  Icons resolved: {count_icons(tree)}")


if __name__ == "__main__":
    main()