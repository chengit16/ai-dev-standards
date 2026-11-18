/** @description 启动开发 API，仅在本机回环地址提供探测。 */
import { createApp } from "./app";

async function start(): Promise<void> {
  const port = Number(process.env.STARTER_API_PORT ?? "8000");
  if (!Number.isInteger(port) || port < 1 || port > 65535)
    throw new Error("API 端口无效");
  const app = await createApp();
  app.enableShutdownHooks();
  await app.listen(port, "127.0.0.1");
}

void start().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
