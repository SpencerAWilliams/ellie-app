import "./tokens.css";
import "./Desktop1.css";

export default function Desktop1() {
  return (
    <div className="desktop1" data-node-id="1:2" aria-label="Desktop - 1">
      <div className="desktop1__map" data-node-id="1:3" aria-label="Map">
        <div className="desktop1__caption" data-node-id="1:6">
          Have maps loaded here with everything layered on top
        </div>

        <button className="desktop1__handle" data-node-id="2:27" aria-hidden="true" />
        <button className="desktop1__handle" data-node-id="2:28" aria-hidden="true" />
        <button className="desktop1__handle" data-node-id="2:30" aria-hidden="true" />

        <div className="desktop1__star" data-node-id="2:36" aria-hidden="true" />
        <ul className="desktop1__polygon" data-node-id="2:37" aria-hidden="true" />

        <span className="desktop1__label desktop1__label--saved" data-node-id="2:39">
          Saved
        </span>
        <span className="desktop1__label desktop1__label--recent" data-node-id="2:38">
          Recent
        </span>

        <button className="desktop1__search" data-node-id="2:16" aria-label="Search">
          <input
            className="desktop1__search-input"
            type="text"
            placeholder="Search..."
          />
        </button>
        <span className="desktop1__search-placeholder" data-node-id="2:18">
          Search...
        </span>

        <button type="button" className="desktop1__chip desktop1__chip--1" data-node-id="2:20" />
        <button type="button" className="desktop1__chip desktop1__chip--2" data-node-id="2:21" />
        <button type="button" className="desktop1__chip desktop1__chip--3" data-node-id="2:23" />
        <button type="button" className="desktop1__chip desktop1__chip--4" data-node-id="2:25" />

        <span className="desktop1__label desktop1__label--search-bar" data-node-id="2:34">
          Search Bar
        </span>
        <div className="desktop1__hint" data-node-id="2:35">
          Chips for options like No Stairs, Accessible Doors, Fitness Tracker, Etc.
        </div>
        <span className="desktop1__label desktop1__label--account" data-node-id="1:9">
          Account
        </span>

        <div className="desktop1__avatar" data-node-id="2:19" aria-hidden="true" />
        <div className="desktop1__blob" data-node-id="2010:2" aria-hidden="true" />
      </div>
    </div>
  );
}
