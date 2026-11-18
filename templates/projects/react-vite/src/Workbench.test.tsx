/** @description 验证健康探测失败后可重试，以及独立前端不会误报后端连接。 */
// @vitest-environment happy-dom
import config from "../starter.json";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { checkHealth } from "./api/services/health";

vi.mock("../starter.json", () => ({ default: { hasApi: false } }));
vi.mock("./api/services/health", () => ({ checkHealth: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("后端失败时显示错误，重新检查后显示连接成功", async () => {
  config.hasApi = true;
  vi.mocked(checkHealth)
    .mockRejectedValueOnce(new Error("响应无效"))
    .mockResolvedValueOnce();
  const { Workbench } = await import("./Workbench");
  render(<Workbench />);
  await screen.findByText("API 返回了无法识别的响应。");
  fireEvent.click(screen.getByRole("button", { name: "重新检查" }));
  await screen.findByText("API 已连接");
  expect(checkHealth).toHaveBeenCalledTimes(2);
});

it("独立前端不发起健康探测", async () => {
  config.hasApi = false;
  const { Workbench } = await import("./Workbench");
  render(<Workbench />);
  expect(screen.getByText("此工程使用独立前端模板")).toBeTruthy();
  expect(checkHealth).not.toHaveBeenCalled();
});
