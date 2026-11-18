/** @description 统一 HTTP 超时和公开错误提示，取消交由请求发起方处理。 */
import axios from "axios";

/** 同源 API 传输入口，服务层负责校验响应。 */
export const apiClient = axios.create({ baseURL: "/api", timeout: 4000 });

/** 将传输错误归为面向用户的提示，避免泄露服务内部信息。 */
export function requestMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    return error.code === "ECONNABORTED"
      ? "请求超时，请重试。"
      : "无法连接 API，请确认后端已启动。";
  }
  return "API 返回了无法识别的响应。";
}
