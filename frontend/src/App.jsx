import { useState } from "react";
import { generateVideo } from "./api";
import "./index.css";

function App() {
  const [code, setCode] = useState(
`#include <iostream>
using namespace std;

int main() {
    int arr[] = {5, 2, 8, 1};

    for(int i = 0; i < 4; i++) {
        cout << arr[i] << " ";
    }

    return 0;
}`
  );

  const [language, setLanguage] = useState("cpp");
  const [loading, setLoading] = useState(false);
  const [videoUrl, setVideoUrl] = useState(null);
  const [error, setError] = useState("");

  const handleGenerate = async () => {
    if (!code.trim()) {
      setError("Please enter some code.");
      return;
    }

    setLoading(true);
    setError("");
    setVideoUrl(null);

    try {
      const result = await generateVideo(code, language);

      setVideoUrl(result.video_url);
    } catch (err) {
      setError("Failed to generate visualization.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">

      <header className="navbar">
        <h1>Code2Video</h1>
        <p>Visualize your code with AI</p>
      </header>

      <main className="container">

        <section className="editor-section">

          <div className="section-header">
            <h2>Upload / Enter Code</h2>

            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="cpp">C++</option>
              <option value="python">Python</option>
              <option value="java">Java</option>
              <option value="javascript">JavaScript</option>
            </select>
          </div>

          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Paste your code here..."
            spellCheck="false"
          />

          <button
            onClick={handleGenerate}
            disabled={loading}
          >
            {loading ? "Generating..." : "Generate Visualization"}
          </button>

          {error && (
            <p className="error">
              {error}
            </p>
          )}

        </section>

        <section className="video-section">

          <h2>Visualization</h2>

          {loading && (
            <div className="loading">
              <div className="spinner"></div>
              <p>
                Analyzing code and generating animation...
              </p>
            </div>
          )}

          {!loading && !videoUrl && (
            <div className="empty">
              <p>Your generated visualization will appear here.</p>
            </div>
          )}

          {videoUrl && (
            <div className="video-container">

              <video
                controls
                src={videoUrl}
              />

              <a
                href={videoUrl}
                download="code-visualization.mp4"
                className="download"
              >
                Download Video
              </a>

            </div>
          )}

        </section>

      </main>

    </div>
  );
}

export default App;