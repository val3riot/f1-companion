import { useState } from "react";
import ArchiveView from "./ArchiveView";
import { LiveView } from "./LiveView";
import { PostRaceView } from "./PostRaceView";
import { PredictionView } from "./PredictionView";

type View = "live" | "archive" | "post-race" | "predictions";

function App() {
  const [view, setView] = useState<View>("live");

  return (
    <main>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">F1</span>
          <span>INSIGHT</span>
        </div>
        <nav className="main-nav" aria-label="Sezioni">
          <button
            className={view === "live" ? "active" : ""}
            onClick={() => setView("live")}
          >
            Live
          </button>
          <button
            className={view === "archive" ? "active" : ""}
            onClick={() => setView("archive")}
          >
            Archivio
          </button>
          <button
            className={view === "post-race" ? "active" : ""}
            onClick={() => setView("post-race")}
          >
            Post-gara
          </button>
          <button
            className={view === "predictions" ? "active" : ""}
            onClick={() => setView("predictions")}
          >
            Predizioni
          </button>
        </nav>
        <div className="source-status">
          <span className="dot" />
          DATI STORICI · TELEMETRIA
        </div>
      </header>

      {view === "live" && <LiveView />}
      {view === "archive" && <ArchiveView />}
      {view === "post-race" && <PostRaceView />}
      {view === "predictions" && <PredictionView />}
    </main>
  );
}

export default App;
