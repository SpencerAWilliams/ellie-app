# figma-to-code

Reads `src/tokens/figma_schema.json` and generates a React component with CSS custom properties into `src/components/`.

## Inputs

- `src/tokens/figma_schema.json` — produced by `scripts/figma/extract.py`

## Output files

| File | Description |
|------|-------------|
| `src/components/tokens.css` | CSS custom properties for all design tokens |
| `src/components/{ComponentName}.css` | BEM component styles referencing the tokens |
| `src/components/{ComponentName}.jsx` | React functional component |

`ComponentName` = `meta.component_name` converted to PascalCase with spaces, hyphens, and special characters removed.
Example: `"Desktop - 1"` → `Desktop1`

---

## tokens.css rules

- Single `:root {}` block
- Output every key from `tokens.colors`, `tokens.typography`, `tokens.spacing`, `tokens.radii`, and `tokens.shadows` as-is
- If `tokens.typography` is empty, derive typography tokens from `text_style` fields found in tree nodes:
  - `--font-family-base`, `--font-size-base`, `--font-weight-base`, `--line-height-base`

---

## {ComponentName}.css rules

- BEM naming: block = kebab-case component name (e.g. `.desktop1`)
- Every distinct visual element gets its own element class: `.desktop1__search`, `.desktop1__chip`, etc.
- Use CSS custom properties from `tokens.css` for all color, spacing, radius, shadow, and font values — never hardcode design values
- Exception: structural layout values (e.g. `width`, `height`) may be hardcoded from the schema `size` field
- No inline styles in JSX — all styling goes in the CSS file
- Layout: flexbox only, no absolute/pixel positioning

### Node-to-CSS mapping

| Schema `type` | CSS approach |
|--------------|-------------|
| `FRAME` with `layout` | `display: flex` + direction, gap, padding, justify-content, align-items from `layout` |
| `FRAME` without `layout` | `display: flex; flex-wrap: wrap; align-content: flex-start` |
| `ELLIPSE` | `border-radius: 50%` |
| `STAR` | `clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%)` |
| `REGULAR_POLYGON` | `clip-path: polygon(50% 0%, 100% 100%, 0% 100%)` |
| `RECTANGLE` with `border_radius` | apply `border-radius` from `border_radius` field |
| `VECTOR` with `svg_path` | inline `<svg>` with `<path d=.../>`, `fill="currentColor"` |

---

## {ComponentName}.jsx rules

```jsx
import "./tokens.css";
import "./{ComponentName}.css";

export default function {ComponentName}() {
  return ( /* tree */ );
}
```

- Every schema node renders as its `tag` field value
- Every element gets:
  - `className` — BEM class (and modifier classes for variants)
  - `data-node-id` — the node's `id` for Figma traceability
  - `aria-label` — the node's `name` (skip if `name` is a generic placeholder like "Rectangle 6")
- `TEXT` nodes: render `content` as the element's text content. If `text_style.color` is present, emit it as a CSS property on that element's class — do not rely solely on a global token if the node has a specific color override.
- `FRAME` nodes: render children recursively in document order
- Image nodes (id appears in `image_node_ids`): render as `<img src={assets[id]} alt={name} />`
- Decorative shapes with no meaningful name: `aria-hidden="true"`

### Vector / icon nodes

If a schema node has an `svg_path` field (type `VECTOR`), render it as an inline SVG — **do not recurse into its children**:

```jsx
<svg
  viewBox="{node.svg_viewbox}"
  aria-hidden="true"
  fill="currentColor"
  xmlns="http://www.w3.org/2000/svg"
>
  <path fillRule="{node.svg_fill_rule}" d="{node.svg_path}" />
</svg>
```

Apply `width` and `height` from the node's `size` field. The parent container's `color` CSS property controls the fill via `currentColor`. Do **not** add a BEM class to the `<path>` — style only the `<svg>` element itself.

### Icon name nodes

If a schema node has an `icon_name` field (no `svg_path`), render it as a Material Symbols glyph — **do not recurse into its children**:

```jsx
<span className="material-symbols-outlined" aria-hidden="true">{node.icon_name}</span>
```

The Material Symbols font must be loaded in the host HTML (via Google Fonts CDN). The `.material-symbols-outlined` CSS class must be defined globally:

```css
.material-symbols-outlined {
  font-family: 'Material Symbols Outlined';
  font-weight: normal;
  font-style: normal;
  font-size: 24px;
  line-height: 1;
  letter-spacing: normal;
  text-transform: none;
  display: inline-block;
  white-space: nowrap;
  direction: ltr;
  -webkit-font-smoothing: antialiased;
  color: inherit;
  user-select: none;
}
```

Do NOT add a CSS class for each individual icon — the glyph name in the text content is sufficient.

### Tag overrides (apply after reading schema `tag`)

| Condition | Use |
|-----------|-----|
| RECTANGLE named like a search/input field | `<button>` wrapping an `<input type="text" />` |
| RECTANGLE named like a chip/filter/tag | `<button type="button">` |
| TEXT that is a label for another element | `<span>` instead of `<div>` |
| ELLIPSE that looks like an avatar | `<div>` with `role="img"` |

### HTML nesting constraints (check before emitting any tag)

- **Never render block-level children** (`div`, `p`, `header`, `ul`, `article`, `section`, `nav`, `button`) inside a `<p>` — change the parent to `<div>` instead
- **Never nest a heading** (`h1`–`h3`) inside another heading — demote the outer container to `<div>` or the inner text to `<span>`
- **`<svg>` must only contain SVG-namespace children** (`path`, `rect`, `circle`, `g`, etc.). Icon nodes that have no real SVG path data (no `d`/`points` attributes in the schema) must be rendered as `<div aria-hidden="true">` with CSS — never place `<div>` or `<span>` inside `<svg>`
- **Heading tags apply only to TEXT nodes** — a FRAME container whose Figma name contains "title" or "heading" is still a layout container; render it as `<div>`

---

## What NOT to generate

- TypeScript (`.ts`/`.tsx`) unless the project already uses it
- Storybook stories
- Unit tests
- `GENERATION_NOTES.md` or any documentation files
- Prop types or default props beyond what the schema provides
- Placeholder comments explaining what the code does

---

## API path context

This skill is used with the **Figma REST API path**: the schema is assembled from a single `/v1/files/:key` call by `scripts/figma/extract.py`.

Children in the schema tree are **already sorted by visual position** (top-to-bottom, then left-to-right by bounding box). Render them in document order — this matches the intended reading and stacking order in the design. Do not re-sort or reorder elements.
