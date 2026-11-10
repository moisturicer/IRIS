import { describe, expect, it } from "vitest";

import { profileApi } from "./profile";
import { installApiStub } from "@/test/apiAdapter";

const stub = installApiStub();

describe("profile photo upload", () => {
  it("sends the framed image and crop as multipart form data", async () => {
    const photo = new File(["image"], "profile.png", { type: "image/png" });

    await profileApi.uploadPhoto(photo, { x: 12, y: 34, size: 56 });

    const sent = stub.only();
    expect(sent).toMatchObject({ method: "put", url: "/users/me/photo/" });
    expect(sent.headers["Content-Type"]).toContain("multipart/form-data");
    expect(sent.body).toBeInstanceOf(FormData);
    expect(Object.fromEntries((sent.body as FormData).entries())).toEqual({
      photo,
      crop_x: "12",
      crop_y: "34",
      crop_size: "56",
    });
  });
});
