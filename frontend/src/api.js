const API_URL = "http://localhost:8000";

export async function generateVideo(code, language) {

  const response = await fetch(`${API_URL}/generate`, {
    method: "POST",

    headers: {
      "Content-Type": "application/json"
    },

    body: JSON.stringify({
      code,
      language
    })
  });

  if (!response.ok) {
    throw new Error("Video generation failed");
  }

  return await response.json();
}