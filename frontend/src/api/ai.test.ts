import { afterEach, describe, expect, it, vi } from "vitest";
import { aiApi } from "./ai";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("./client", () => ({ apiClient: { get } }));

afterEach(() => vi.clearAllMocks());

describe("earlier conversations (IR-957)", () => {
  it("reads one under the public reader protocol (IR-596)", async () => {
    get.mockResolvedValue({ data: {} });

    await aiApi.conversations.get(4);

    expect(get).toHaveBeenCalledWith("/ai/conversations/4/", { headers: { "X-IRIS-Protocol": "public-1" } });
  });

  it("offers no way to ask Django a question", () => {
    expect(Object.keys(aiApi).sort()).toEqual(["conversations", "overview", "status"]);
    expect(Object.keys(aiApi.conversations).sort()).toEqual(["get", "list", "remove"]);
  });
});
