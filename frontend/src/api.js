const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8002";

export async function generateVideo(code, language) {
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

  if (data.video_url && data.video_url.startsWith("/")) {
    data.video_url = `${API_URL}${data.video_url}`;
  }

  return data;
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
