import { useState } from "react";
import type { VideoResultItem } from "../services/videoApi";
import { PlayIcon } from "./icons";

export default function VideoCard({ item }: { item: VideoResultItem }) {
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState(false);

  return (
    <article className="video-card">
      {playing ? (
        // Play in place, on the app page itself.
        <video
          src={item.url}
          poster={item.poster || undefined}
          controls
          autoPlay
          playsInline
          preload="metadata"
          style={{
            width: "100%",
            aspectRatio: "16 / 9",
            background: "#000",
            display: "block",
          }}
        />
      ) : (
        <button
          type="button"
          className="video-thumb-wrap"
          onClick={() => setPlaying(true)}
          aria-label={`Play ${item.title}`}
          style={{
            display: "block",
            width: "100%",
            padding: 0,
            border: 0,
            margin: 0,
            background: "none",
            cursor: "pointer",
            textAlign: "inherit",
          }}
        >
          {item.poster && !failed ? (
            <img
              src={item.poster}
              alt=""
              loading="lazy"
              onError={() => setFailed(true)}
              style={{ display: "block", width: "100%" }}
            />
          ) : (
            <div style={{ aspectRatio: "16 / 9", background: "var(--surface-2)" }} />
          )}
          <span className="video-play" aria-hidden="true">
            <span className="video-play-circle">
              <PlayIcon size={20} />
            </span>
          </span>
        </button>
      )}
      <div className="video-card-body">
        <a
          href={item.page || item.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          <h3 className="video-card-title">{item.title}</h3>
        </a>
        <p className="video-card-meta">
          Wikimedia Commons
          {item.mime ? ` · ${item.mime.replace("video/", "")}` : ""}
        </p>
      </div>
    </article>
  );
}
