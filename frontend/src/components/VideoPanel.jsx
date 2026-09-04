import { CheckIcon, DownloadIcon, FilmIcon, LoaderIcon } from "./icons";

const STAGES = [
  { id: "parse", label: "Parsing code" },
  { id: "plan", label: "Planning visualization" },
  { id: "render", label: "Rendering video" },
];

function ProgressSteps({ activeIndex }) {
  return (
    <ol className="progress-steps">
      {STAGES.map((stage, i) => {
        const state =
          i < activeIndex ? "done" : i === activeIndex ? "active" : "pending";
        return (
          <li key={stage.id} className={`progress-steps__item is-${state}`}>
            <span className="progress-steps__marker">
              {state === "done" ? (
                <CheckIcon width={13} height={13} />
              ) : state === "active" ? (
                <LoaderIcon className="btn__spinner" width={13} height={13} />
              ) : (
                <span className="progress-steps__dot" />
              )}
            </span>
            <span className="progress-steps__label">{stage.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

function VideoPanel({ loading, stageIndex, videoUrl, meta }) {
  return (
    <section className="panel video-panel">
      <div className="panel__header">
        <div className="panel__title">
          <FilmIcon width={18} height={18} />
          <h2>Visualization</h2>
        </div>
      </div>

      <div className="video-stage">
        {loading && (
          <div className="state-box">
            <ProgressSteps activeIndex={stageIndex} />
            <p className="state-box__hint">
              This can take up to a minute depending on code complexity.
            </p>
          </div>
        )}

        {!loading && !videoUrl && (
          <div className="state-box state-box--empty">
            <div className="state-box__icon">
              <FilmIcon width={30} height={30} />
            </div>
            <p className="state-box__title">No visualization yet</p>
            <p className="state-box__hint">
              Paste some code on the left and hit{" "}
              <strong>Generate Visualization</strong> to render an animated
              walkthrough here.
            </p>
          </div>
        )}

        {!loading && videoUrl && (
          <div className="result">
            {meta && (
              <div className="badge-row">
                {meta.title && <span className="badge badge--title">{meta.title}</span>}
                {meta.algorithm && (
                  <span className="badge">Algorithm: {meta.algorithm}</span>
                )}
                {meta.dataStructure && (
                  <span className="badge">
                    Structure: {meta.dataStructure}
                  </span>
                )}
              </div>
            )}

            <div className="video-frame">
              <video controls src={videoUrl} />
            </div>

            <a
              href={videoUrl}
              download="code-visualization.mp4"
              className="btn btn--secondary"
            >
              <DownloadIcon width={17} height={17} />
              Download Video
            </a>
          </div>
        )}
      </div>
    </section>
  );
}

export default VideoPanel;
