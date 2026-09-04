import { AlertIcon, CodeIcon, LoaderIcon, WandIcon } from "./icons";
import { LANGUAGES, SAMPLE_CODE } from "./languages";

function CodeEditorPanel({
  code,
  setCode,
  language,
  setLanguage,
  loading,
  onGenerate,
  error,
}) {
  const loadExample = () => {
    setCode(SAMPLE_CODE[language] || SAMPLE_CODE.cpp);
  };

  return (
    <section className="panel editor-panel">
      <div className="panel__header">
        <div className="panel__title">
          <CodeIcon width={18} height={18} />
          <h2>Your Code</h2>
        </div>

        <div className="lang-switch" role="tablist" aria-label="Language">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.id}
              type="button"
              role="tab"
              aria-selected={language === lang.id}
              className={`lang-switch__item ${
                language === lang.id ? "is-active" : ""
              }`}
              onClick={() => setLanguage(lang.id)}
              style={{ "--lang-accent": lang.accent }}
            >
              <span className="lang-switch__dot" />
              {lang.label}
            </button>
          ))}
        </div>
      </div>

      <div className="editor-shell">
        <div className="editor-shell__topbar">
          <span className="editor-dot editor-dot--red" />
          <span className="editor-dot editor-dot--yellow" />
          <span className="editor-dot editor-dot--green" />
          <span className="editor-shell__filename">
            snippet.{extensionFor(language)}
          </span>
        </div>

        <textarea
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="Paste your code here… e.g. a sorting algorithm, a graph traversal, or a linked-list operation."
          spellCheck="false"
          aria-label="Source code input"
        />
      </div>

      <div className="editor-actions">
        <button
          type="button"
          className="chip-button"
          onClick={loadExample}
          disabled={loading}
        >
          <WandIcon width={15} height={15} />
          Try an example
        </button>

        <button
          type="button"
          className="btn btn--primary"
          onClick={onGenerate}
          disabled={loading}
        >
          {loading ? (
            <>
              <LoaderIcon className="btn__spinner" width={18} height={18} />
              Generating…
            </>
          ) : (
            <>
              <WandIcon width={18} height={18} />
              Generate Visualization
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="alert" role="alert">
          <AlertIcon width={18} height={18} />
          <span>{error}</span>
        </div>
      )}
    </section>
  );
}

function extensionFor(language) {
  switch (language) {
    case "cpp":
      return "cpp";
    case "python":
      return "py";
    case "java":
      return "java";
    case "javascript":
      return "js";
    default:
      return "txt";
  }
}

export default CodeEditorPanel;
