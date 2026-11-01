const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const POLL_INTERVAL_MS = 1500;

// Starts a background render job, then polls it until it finishes.
// onStage receives the backend stage: "queued" | "tracing" | "planning" | "rendering".
export async function generateVideo(code, language, onStage = () => {}) {
  const response = await fetch(`${API_URL}/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ code, language }),
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || "Video generation failed");
  }

  onStage(data.status);
  const result = await pollJob(data.job_id, onStage);

  if (result.video_url && result.video_url.startsWith("/")) {
    result.video_url = `${API_URL}${result.video_url}`;
  }

  return result;
}

async function pollJob(jobId, onStage) {
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    const response = await fetch(`${API_URL}/jobs/${jobId}`);
    const job = await response.json();

    if (!response.ok) {
      throw new Error(job.detail || "Lost track of the video job");
    }
    if (job.status === "done") {
      return job.result;
    }
    if (job.status === "failed") {
      throw new Error(job.error || "Video generation failed");
    }
    onStage(job.status);
  }
}

export async function parseCode(code, language) {
  const response = await fetch(`${API_URL}/parse`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ code, language }),
  });

  if (!response.ok) {
    const data = await response.json();
    throw new Error(data.detail || "Parse failed");
  }

  return response.json();
}
