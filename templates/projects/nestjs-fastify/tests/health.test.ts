/** @description 通过 Fastify 注入校验真实路由和响应，不占用端口。 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createApp } from "../src/app";

test("健康接口返回稳定响应", async () => {
  const app = await createApp();
  try {
    await app.init();
    const response = await app.inject({ method: "GET", url: "/api/health" });
    assert.equal(response.statusCode, 200);
    assert.deepEqual(response.json(), { status: "ok" });
  } finally {
    await app.close();
  }
});
