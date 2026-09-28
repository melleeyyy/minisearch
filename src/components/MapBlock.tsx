import { useEffect, useRef } from "react";

interface MapBlockProps {
  lat: number;
  lon: number;
  label: string;
  expanded?: boolean;
  onToggle?: () => void;
}

interface LeafletMap {
  remove: () => void;
}

interface LeafletStatic {
  map: (el: HTMLElement, opts: Record<string, boolean>) => LeafletMap & {
    setView: (coords: [number, number], zoom: number) => LeafletMap & { setView: LeafletMap & { setView: unknown } };
  };
  tileLayer: (url: string, opts: Record<string, unknown>) => { addTo: (m: unknown) => void };
  marker: (coords: [number, number]) => { addTo: (m: unknown) => { bindPopup: (l: string) => void } };
}

/**
 * Expandable Leaflet/OSM map block. Leaflet loads from CDN (index.html);
 * when it is unavailable (offline PWA), the block falls back to a plain
 * OSM link instead of breaking the card.
 */
export default function MapBlock({ lat, lon, label, expanded = false, onToggle }: MapBlockProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);

  useEffect(() => {
    if (!expanded || !ref.current) return;
    const L = (window as unknown as { L?: LeafletStatic }).L;
    if (!L) return;
    const map = L.map(ref.current, {
      zoomControl: true,
      attributionControl: true,
    }).setView([lat, lon], 11);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);
    const marker = L.marker([lat, lon]).addTo(map);
    if (label) marker.bindPopup(label);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [expanded, lat, lon, label]);

  const osmUrl = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=11/${lat}/${lon}`;

  return (
    <div className="map-block">
      <div className="map-block-head">
        <span className="map-block-title">Map</span>
        {onToggle && (
          <button
            type="button"
            className="map-toggle"
            onClick={onToggle}
            aria-expanded={expanded}
          >
            {expanded ? "Collapse map" : "Expand map"}
          </button>
        )}
      </div>
      {expanded ? (
        <div className="map-canvas" ref={ref} role="img"
             aria-label={`Map showing ${label || "location"}`} />
      ) : (
        <a className="map-preview" href={osmUrl} target="_blank" rel="noreferrer">
          <span className="map-pin">📍</span>
          <span>
            {lat.toFixed(3)}°, {lon.toFixed(3)}° — view on OpenStreetMap
          </span>
        </a>
      )}
    </div>
  );
}
