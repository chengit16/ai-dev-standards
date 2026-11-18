/** @description 装配路由和 Ant Design 主题，保持入口与业务页面解耦。 */
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { router } from "./routes";
import "virtual:uno.css";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("缺少应用挂载节点");

createRoot(root).render(
  <StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{ token: { colorPrimary: "#005b4b", borderRadius: 5 } }}
    >
      <RouterProvider router={router} />
    </ConfigProvider>
  </StrictMode>,
);
