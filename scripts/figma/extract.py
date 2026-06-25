"""
extract.py — Figma design schema assembler
Usage: python extract.py <file_key> [--node <node_id>]

Reads:
  /tmp/figma_file.json       (or /tmp/figma_nodes.json if --node is given)
  /tmp/figma_styles.json
  /tmp/figma_images_svg.json  (optional)
  /tmp/figma_images_png.json  (optional)

Writes:
  /tmp/figma_schema.json     (clean design schema for Claude to consume)
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
    """Map Figma alignment enum values to CSS flexbox values."""
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

def extract_tokens(styles_data, file_data):
    """
    Build the tokens dict from published styles + any inline values
    found on nodes in the file tree.
    """
    tokens = {"colors": {}, "typography": {}, "spacing": {}, "radii": {}, "shadows": {}}
    unnamed_color_index = 1

    style_meta = styles_data.get("meta", {}).get("styles", [])

    # Map style node IDs to their names for lookup during tree walk
    style_id_to_name = {s["node_id"]: s["name"] for s in style_meta}

    # Pull color and text styles out of the file's styles dict
    file_styles = file_data.get("styles", {})

    for node_id, style_info in file_styles.items():
        style_type = style_info.get("styleType")
        name = style_info.get("name", f"unnamed-{unnamed_color_index}")
        slug = slugify(name)

        if style_type == "FILL":
            # Color value is on the node itself, not in the styles endpoint —
            # we resolve it during the tree walk below; register the name here.
            tokens["colors"][f"--color-{slug}"] = None  # placeholder

        elif style_type == "TEXT":
            tokens["typography"][f"--font-family-{slug}"] = None
            tokens["typography"][f"--font-size-{slug}"] = None
            tokens["typography"][f"--font-weight-{slug}"] = None
            tokens["typography"][f"--line-height-{slug}"] = None

    # Walk the tree once to resolve color/text style values and
    # collect any inline fills that aren't published styles.
    def walk(node):
        # Resolve color fills
        style_refs = node.get("styles", {})
        fills = node.get("fills", [])
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
                # Inline fill — add it if we haven't seen this hex already
                if hex_val not in tokens["colors"].values():
                    tokens["colors"][f"--color-unnamed-{unnamed_color_index}"] = hex_val

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
                    tokens["typography"][f"--line-height-{slug}"] = (
                        f"{round(lh / ts['fontSize'], 2)}" if lh and ts.get("fontSize") else "1.5"
                    )

        # Collect border radii
        radius = node.get("cornerRadius")
        if radius and radius > 0:
            key = f"--radius-{px(radius).replace('px', '')}"
            tokens["radii"][key] = px(radius)

        # Collect box shadows
        effects = node.get("effects", [])
        for i, effect in enumerate(effects):
            if effect.get("type") in ("DROP_SHADOW", "INNER_SHADOW") and effect.get("visible", True):
                c = effect.get("color", {})
                hex_c = rgba_to_hex(c.get("r", 0), c.get("g", 0), c.get("b", 0), c.get("a", 0.15))
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

    # Remove any color placeholders that were never resolved
    tokens["colors"] = {k: v for k, v in tokens["colors"].items() if v is not None}

    # Add common spacing scale derived from the smallest non-zero gap found
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
        base = min(gaps)
        for multiplier, name in [(0.5, "xs"), (1, "sm"), (2, "md"), (3, "lg"), (4, "xl"), (6, "2xl")]:
            tokens["spacing"][f"--space-{name}"] = px(base * multiplier)
    else:
        # Sensible defaults
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


def infer_html_tag(name):
    name_lower = name.lower()
    if any(k in name_lower for k in ("button", "cta", "btn")):
        return "button"
    if any(k in name_lower for k in ("input", "field", "textfield", "text-field")):
        return "input"
    if any(k in name_lower for k in ("image", "img", "photo", "thumbnail", "avatar")):
        return "img"
    if any(k in name_lower for k in ("icon",)):
        return "svg"
    if any(k in name_lower for k in ("h1", "heading-1", "display")):
        return "h1"
    if any(k in name_lower for k in ("h2", "heading-2", "title")):
        return "h2"
    if any(k in name_lower for k in ("h3", "heading-3", "subtitle")):
        return "h3"
    if any(k in name_lower for k in ("label", "caption", "overline")):
        return "span"
    if any(k in name_lower for k in ("paragraph", "body", "description", "text")):
        return "p"
    if any(k in name_lower for k in ("nav", "navigation", "navbar")):
        return "nav"
    if any(k in name_lower for k in ("header",)):
        return "header"
    if any(k in name_lower for k in ("footer",)):
        return "footer"
    if any(k in name_lower for k in ("list", "ul", "ol")):
        return "ul"
    if any(k in name_lower for k in ("section",)):
        return "section"
    if any(k in name_lower for k in ("card",)):
        return "article"
    return "div"


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
    constraints = node.get("layoutSizingHorizontal", "FIXED")
    h_constraints = node.get("layoutSizingVertical", "FIXED")
    w = node.get("absoluteBoundingBox", {}).get("width")
    h = node.get("absoluteBoundingBox", {}).get("height")
    return {
        "width": "100%" if constraints == "FILL" else ("fit-content" if constraints == "HUG" else (px(w) if w else None)),
        "height": "auto" if h_constraints == "HUG" else (px(h) if h else None),
        "flex": "1" if constraints == "FILL" else None,
    }


def is_image_node(node):
    fills = node.get("fills", [])
    return fills and fills[0].get("type") == "IMAGE"


def build_tree(node, image_node_ids):
    if should_ignore(node):
        return None

    node_type = node.get("type", "")
    result = {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node_type,
        "tag": infer_html_tag(node.get("name", "")),
    }

    # Layout
    layout = extract_layout(node)
    if layout:
        result["layout"] = layout

    # Size
    result["size"] = extract_size(node)

    # Text content
    if node_type == "TEXT":
        result["content"] = node.get("characters", "")
        ts = node.get("style", {})
        result["text_style"] = {
            "font_family": ts.get("fontFamily"),
            "font_size": ts.get("fontSize"),
            "font_weight": ts.get("fontWeight"),
            "line_height_px": ts.get("lineHeightPx"),
            "text_align": ts.get("textAlignHorizontal", "LEFT").lower(),
            "color": rgba_to_hex(**node["fills"][0]["color"]) if node.get("fills") and node["fills"][0].get("type") == "SOLID" else None,
        }

    # Image fill
    if is_image_node(node):
        image_node_ids.append(node["id"])
        result["is_image"] = True

    # Corner radius
    radius = node.get("cornerRadius")
    if radius:
        result["border_radius"] = px(radius)

    # Opacity
    opacity = node.get("opacity", 1.0)
    if opacity < 0.999:
        result["opacity"] = round(opacity, 2)

    # Component / instance
    if node_type in ("COMPONENT", "INSTANCE"):
        result["component_name"] = node.get("name")
        if node_type == "INSTANCE":
            result["component_id"] = node.get("componentId")

    # Children
    children = [
        build_tree(child, image_node_ids)
        for child in node.get("children", [])
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
            images = data.get("images", {})
            for node_id, url in images.items():
                if url:
                    # Use SVG url if both exist, PNG as fallback
                    clean_id = node_id.replace(":", "-")
                    if clean_id not in assets or path.endswith("svg.json"):
                        assets[clean_id] = url
    return assets


def label_image_assets(tree, image_node_ids, asset_urls):
    """Walk the tree and attach asset URLs to image nodes."""
    if not tree:
        return
    if tree.get("is_image"):
        clean_id = tree["id"].replace(":", "-")
        url = asset_urls.get(clean_id)
        if url:
            tree["asset_url"] = url
    for child in tree.get("children", []):
        label_image_assets(child, image_node_ids, asset_urls)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Assemble Figma design schema")
    parser.add_argument("file_key", help="Figma file key")
    parser.add_argument("--node", help="Target node ID (optional)", default=None)
    parser.add_argument("--out", help="Output path", default="/tmp/figma_schema.json")
    args = parser.parse_args()

    # Load raw API responses
    if args.node:
        raw_path = Path("/tmp/figma_nodes.json")
    else:
        raw_path = Path("/tmp/figma_file.json")

    if not raw_path.exists():
        print(f"ERROR: {raw_path} not found. Run the curl extraction steps in SKILL.md first.", file=sys.stderr)
        sys.exit(1)

    styles_path = Path("/tmp/figma_styles.json")
    if not styles_path.exists():
        print("ERROR: /tmp/figma_styles.json not found.", file=sys.stderr)
        sys.exit(1)

    file_data = json.loads(raw_path.read_text())
    styles_data = json.loads(styles_path.read_text())

    # If targeting a specific node, unwrap the nodes response
    if args.node:
        node_id = args.node.replace("-", ":")
        nodes = file_data.get("nodes", {})
        if node_id not in nodes:
            # Try the raw node ID as given
            node_id = args.node
        target = nodes.get(node_id, {}).get("document")
        if not target:
            print(f"ERROR: Node {args.node} not found in figma_nodes.json", file=sys.stderr)
            sys.exit(1)
        component_name = target.get("name", "Component")
        file_data_for_tokens = {"document": target, "styles": file_data.get("styles", {})}
    else:
        # Use the first page's first frame as target if no node specified
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
            names = ", ".join(f['name'] for f in frames)
            print(f"INFO: Multiple frames found: {names}", file=sys.stderr)
            print(f"INFO: Using first frame: {frames[0]['name']}", file=sys.stderr)
            print(f"INFO: Use --node <id> to target a specific frame.", file=sys.stderr)
        target = frames[0]
        component_name = target.get("name", "Component")
        file_data_for_tokens = file_data

    # Extract tokens
    tokens = extract_tokens(styles_data, file_data_for_tokens)

    # Build tree
    image_node_ids = []
    tree = build_tree(target, image_node_ids)

    # Load and attach asset URLs
    asset_urls = load_asset_urls()
    label_image_assets(tree, image_node_ids, asset_urls)

    # Assemble schema
    schema = {
        "meta": {
            "file_key": args.file_key,
            "target_node": args.node,
            "component_name": component_name,
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
    print(f"  Tree nodes: {count_nodes(tree)}")


def count_nodes(node):
    if not node:
        return 0
    return 1 + sum(count_nodes(c) for c in node.get("children", []))


if __name__ == "__main__":
    main()
