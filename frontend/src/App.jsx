import { useRef, useState } from "react";
import { generateVideo } from "./api";
import Header from "./components/Header";
import CodeEditorPanel from "./components/CodeEditorPanel";
import VideoPanel from "./components/VideoPanel";
import "./index.css";

const DEFAULT_CODE = `#include <iostream>
using namespace std;

int main() {
    int arr[] = {5, 2, 8, 1};

    for(int i = 0; i < 4; i++) {
        cout << arr[i] << " ";
    }

    return 0;
}`;

function App() {
  const [code, setCode] = useState(DEFAULT_CODE);
  const [language, setLanguage] = useState("cpp");
  const [loading, setLoading] = useState(false);
  const [stageIndex, setStageIndex] = useState(0);
  const [videoUrl, setVideoUrl] = useState(null);
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState("");

  const timers = useRef([]);

  const clearStageTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };

  // The backend performs parse -> plan -> render as a single synchronous
  // call, so there's no real progress feed. These staged messages are a
  // simulated, best-effort approximation to keep the wait feeling honest
  // and informative rather than a single opaque spinner.
  const runStagedProgress = () => {
    setStageIndex(0);
    timers.current.push(setTimeout(() => setStageIndex(1), 1200));
    timers.current.push(setTimeout(() => setStageIndex(2), 2800));
  };

  const handleGenerate = async () => {
    if (!code.trim()) {
      setError("Please enter some code.");
      return;
    }

    setLoading(true);
    setError("");
    setVideoUrl(null);
    setMeta(null);
    runStagedProgress();

    try {
      const result = await generateVideo(code, language);

      setVideoUrl(result.video_url);
      setMeta({
        algorithm: result.algorithm,
        title: result.title,
        dataStructure: result.data_structure,
      });
    } catch (err) {
      setError(err.message || "Failed to generate visualization.");
      console.error(err);
    } finally {
      clearStageTimers();
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <div className="app__glow" aria-hidden="true" />

      <Header />

      <main className="container">
        <CodeEditorPanel
          code={code}
          setCode={setCode}
          language={language}
          setLanguage={setLanguage}
          loading={loading}
          onGenerate={handleGenerate}
          error={error}
        />

        <VideoPanel
          loading={loading}
          stageIndex={stageIndex}
          videoUrl={videoUrl}
          meta={meta}
        />
      </main>

      <footer className="app-footer">
        <p>Code2Video — AI-assisted algorithm animation</p>
      </footer>
    </div>
  );
}

export default App;
