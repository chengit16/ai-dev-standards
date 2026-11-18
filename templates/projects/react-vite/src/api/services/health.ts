/** @description 校验健康响应，未知值不会被当成 API 已连接。 */
import { apiClient } from "../client";

/** 获取服务健康状态，信号允许调用方取消已经失效的查询。 */
export async function checkHealth(signal: AbortSignal): Promise<void> {
  const { data } = await apiClient.get<unknown>("/health", { signal });
  if (
    typeof data !== "object" ||
    data === null ||
    !("status" in data) ||
    data.status !== "ok"
  ) {
    throw new Error("健康检查响应无效");
  }
}
