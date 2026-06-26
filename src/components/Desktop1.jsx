/*
 * Desktop1.jsx — generated from src/tokens/figma_schema.json
 * Figma component: "Desktop - 1"  (file key IbOn2ySG7DtiHMWYY0r1cy, node 1:2)
 *
 * Generated via the Figma REST API path. Every node from the schema tree is
 * represented below with its inferred HTML tag and content. Data-node-id
 * attributes preserve traceability back to the Figma node ids.
 */

import "./tokens.css";
import "./Desktop1.css";

export default function Desktop1() {
  return (
    <div className="desktop1" data-node-id="1:2" aria-label="Desktop - 1">
      <div className="desktop1__map" data-node-id="1:3">
        {/* Map hint */}
        <div className="desktop1__text desktop1__map-hint" data-node-id="1:6">
          Have maps loaded here with everything layered on top
        </div>

        {/* Drag-handle bars */}
        <button type="button" className="desktop1__handle" data-node-id="2:27" aria-label="Rectangle 6" />
        <button type="button" className="desktop1__handle" data-node-id="2:28" aria-label="Rectangle 7" />
        <button type="button" className="desktop1__handle" data-node-id="2:30" aria-label="Rectangle 8" />

        {/* Decorative shapes */}
        <div className="desktop1__star" data-node-id="2:36" aria-label="Star 1" />
        <ul className="desktop1__polygon" data-node-id="2:37" aria-label="Polygon 1" />

        {/* Tab labels */}
        <div className="desktop1__text desktop1__label-saved" data-node-id="2:39">
          Saved
        </div>
        <div className="desktop1__text desktop1__label-recent" data-node-id="2:38">
          Recent
        </div>

        {/* Search bar */}
        <button type="button" className="desktop1__search" data-node-id="2:16" aria-label="Search">
          <span className="desktop1__text desktop1__label-search-placeholder" data-node-id="2:18">
            Search...
          </span>
        </button>

        {/* Option chips */}
        <button type="button" className="desktop1__chip desktop1__chip--2" data-node-id="2:20" aria-label="Rectangle 2" />
        <button type="button" className="desktop1__chip desktop1__chip--3" data-node-id="2:21" aria-label="Rectangle 3" />
        <button type="button" className="desktop1__chip desktop1__chip--4" data-node-id="2:23" aria-label="Rectangle 4" />
        <button type="button" className="desktop1__chip desktop1__chip--5" data-node-id="2:25" aria-label="Rectangle 5" />

        {/* Section captions */}
        <div className="desktop1__text desktop1__label-search-bar" data-node-id="2:34">
          Search Bar
        </div>
        <div className="desktop1__text desktop1__label-chips" data-node-id="2:35">
          Chips for options like No Stairs, Accessible Doors, Fitness Tracker, Etc.
        </div>

        {/* Account */}
        <div className="desktop1__text desktop1__label-account" data-node-id="1:9">
          Account
        </div>
        <div className="desktop1__avatar" data-node-id="2:19" aria-label="Ellipse 1" />
        <div className="desktop1__ellipse-2" data-node-id="2010:2" aria-label="Ellipse 2" />
      </div>
    </div>
  );
}
