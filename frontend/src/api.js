const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? "";
const API_BASE_URL = configuredBaseUrl.replace(/\/+$/, "");

export class ChatApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : "The request could not be completed.");
    this.name = "ChatApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function sendChat(payload) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  let body = {};
  try {
    body = await response.json();
  } catch {
    // Keep a useful HTTP error if a proxy or server returns a non-JSON body.
  }

  if (!response.ok) {
    throw new ChatApiError(response.status, body.detail);
  }

  return body;
}

export function errorMessage(error) {
  if (error instanceof ChatApiError) {
    if (error.status === 422) {
      const detail = Array.isArray(error.detail)
        ? error.detail.map((item) => item.msg).filter(Boolean).join(" ")
        : error.detail;
      return detail
        ? `Please check your request: ${detail}`
        : "Please check your message and try again.";
    }
    if (error.status === 503) {
      return "All AI providers are currently unavailable. Please try again shortly.";
    }
    return typeof error.detail === "string" && error.detail
      ? error.detail
      : "The request could not be completed. Please try again.";
  }

  return "Unable to reach Lyftr AI. Check your connection and try again.";
}
