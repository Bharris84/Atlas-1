import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";

/**
 * The Authorization header must actually reach the network call.
 *
 * This exists because the Owner tab once called `fetch()` directly and so sent
 * no token at all — a bug invisible under development auth, which accepts
 * anonymous requests, and fatal the moment Supabase auth is enabled.
 */
describe("API client authentication", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    // A fresh Response per call: a body can only be read once, so a shared
    // instance fails the moment two requests are in flight.
    fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response("[]", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
    );
    vi.stubGlobal("fetch", fetchMock);
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  function headersOf(call: number = 0): Record<string, string> {
    return (fetchMock.mock.calls[call][1] as RequestInit).headers as Record<string, string>;
  }

  it("attaches the bearer token when one is stored", async () => {
    window.localStorage.setItem("atlas.access_token", "test-token-value");
    await api.listProperties();
    expect(headersOf().Authorization).toBe("Bearer test-token-value");
  });

  it("omits the header entirely when no token is stored", async () => {
    await api.listProperties();
    expect(headersOf().Authorization).toBeUndefined();
  });

  it("authenticates the owners endpoint", async () => {
    // The endpoint that previously bypassed the client.
    window.localStorage.setItem("atlas.access_token", "test-token-value");
    await api.listOwners("prop-1");
    expect(fetchMock.mock.calls[0][0]).toContain("/api/properties/prop-1/owners");
    expect(headersOf().Authorization).toBe("Bearer test-token-value");
  });

  it("authenticates every read used by the property page", async () => {
    window.localStorage.setItem("atlas.access_token", "test-token-value");
    await Promise.all([
      api.listOwners("p"),
      api.listComps("p"),
      api.listCommunications("p"),
      api.listAnalyses("p"),
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    for (let i = 0; i < 4; i += 1) {
      expect(headersOf(i).Authorization).toBe("Bearer test-token-value");
    }
  });
});
