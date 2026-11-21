import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App.jsx";

const successfulResponse = {
  session_id: "session-test",
  reply: "Hello from Lyftr.",
  metadata: {
    resolution_source: "LIVE_INFERENCE",
    model: "gpt-4o-mini",
    latency_ms: 48,
    input_tokens: 8,
    output_tokens: 4,
    key_id: "key_1",
    fallback_attempts: 0,
  },
};

function jsonResponse(body, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

describe("Lyftr AI chat", () => {
  beforeEach(() => {
    let id = 0;
    vi.stubGlobal("crypto", { randomUUID: () => `session-test-${++id}` });
    vi.stubGlobal("fetch", vi.fn());
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("sends the page session and backend payload, then renders reply metadata", async () => {
    const user = userEvent.setup();
    fetch.mockResolvedValue(jsonResponse(successfulResponse));
    render(<App />);

    const input = screen.getByTestId("chat-input");
    await user.type(input, "What is Lyftr?");
    await user.click(screen.getByTestId("send-button"));

    await screen.findByText("Hello from Lyftr.");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/chat");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      session_id: "session-test-1",
      message: "What is Lyftr?",
    });
    expect(screen.getByTestId("assistant-message")).toBeInTheDocument();
    expect(screen.getByTestId("meta-source")).toHaveTextContent("LIVE_INFERENCE");
    expect(screen.getByTestId("meta-model")).toHaveTextContent("gpt-4o-mini");
    expect(screen.getByTestId("meta-latency")).toHaveTextContent("48 ms");
    expect(screen.getByTestId("meta-input-tokens")).toHaveTextContent("8");
    expect(screen.getByTestId("meta-output-tokens")).toHaveTextContent("4");
  });

  it("sends an edited system prompt and retains the same session for later messages", async () => {
    const user = userEvent.setup();
    fetch.mockResolvedValue(jsonResponse(successfulResponse));
    render(<App />);

    await user.type(screen.getByTestId("system-prompt-input"), "Use short answers.");
    await user.type(screen.getByTestId("chat-input"), "First message");
    await user.keyboard("{Enter}");
    await screen.findByText("Hello from Lyftr.");

    await user.type(screen.getByTestId("chat-input"), "Second message");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));

    const firstPayload = JSON.parse(fetch.mock.calls[0][1].body);
    const secondPayload = JSON.parse(fetch.mock.calls[1][1].body);
    expect(firstPayload.system_prompt).toBe("Use short answers.");
    expect(secondPayload).toEqual({
      session_id: firstPayload.session_id,
      message: "Second message",
    });
  });

  it("creates a fresh session when a new page instance mounts", async () => {
    const user = userEvent.setup();
    fetch.mockResolvedValue(jsonResponse(successfulResponse));
    const firstPage = render(<App />);
    await user.type(screen.getByTestId("chat-input"), "First page");
    await user.click(screen.getByTestId("send-button"));
    await screen.findByText("Hello from Lyftr.");
    const firstSession = JSON.parse(fetch.mock.calls[0][1].body).session_id;

    firstPage.unmount();
    render(<App />);
    await user.type(screen.getByTestId("chat-input"), "Second page");
    await user.click(screen.getByTestId("send-button"));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const secondSession = JSON.parse(fetch.mock.calls[1][1].body).session_id;

    expect(secondSession).not.toBe(firstSession);
  });

  it.each([
    [422, { detail: "message must not be empty" }, /Please check your request/],
    [503, { detail: "all providers unavailable" }, /All AI providers are currently unavailable/],
  ])("shows HTTP %i errors without adding a successful exchange", async (status, body, message) => {
    const user = userEvent.setup();
    fetch.mockResolvedValue(jsonResponse(body, status));
    render(<App />);

    await user.type(screen.getByTestId("chat-input"), "Do not add me on failure");
    await user.click(screen.getByTestId("send-button"));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(document.querySelector(".user-bubble")).not.toBeInTheDocument();
    expect(screen.queryByTestId("assistant-message")).not.toBeInTheDocument();
    expect(screen.getByTestId("chat-input")).toHaveValue("Do not add me on failure");
  });

  it("prevents duplicate submissions while a request is pending", async () => {
    const user = userEvent.setup();
    let finishRequest;
    fetch.mockReturnValue(new Promise((resolve) => { finishRequest = resolve; }));
    render(<App />);

    await user.type(screen.getByTestId("chat-input"), "Only once");
    await user.keyboard("{Enter}");
    expect(await screen.findByTestId("loading-indicator")).toBeInTheDocument();
    expect(screen.getByTestId("send-button")).toBeDisabled();
    await user.keyboard("{Enter}");
    expect(fetch).toHaveBeenCalledTimes(1);

    finishRequest({ ok: true, status: 200, json: async () => successfulResponse });
    await screen.findByText("Hello from Lyftr.");
  });

  it("shows a useful message for unexpected network errors", async () => {
    const user = userEvent.setup();
    fetch.mockRejectedValue(new TypeError("network down"));
    render(<App />);

    await user.type(screen.getByTestId("chat-input"), "Network test");
    await user.click(screen.getByTestId("send-button"));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Unable to reach Lyftr AI/);
    expect(screen.queryByTestId("assistant-message")).not.toBeInTheDocument();
  });
});
