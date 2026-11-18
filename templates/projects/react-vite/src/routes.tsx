/** @description 注册首页、未匹配页面和渲染错误恢复入口。 */
import { Button } from "antd";
import { createBrowserRouter, Link } from "react-router-dom";
import { Workbench } from "./Workbench";

function Recovery({ failed }: { failed?: boolean }) {
  return (
    <main className="shell">
      <h1>{failed ? "页面暂时无法显示" : "没有找到这个页面"}</h1>
      {failed ? (
        <Button onClick={() => window.location.assign("/")}>返回首页</Button>
      ) : (
        <Link to="/">返回首页</Link>
      )}
    </main>
  );
}

/** 应用路由及对应的页面恢复动作。 */
export const router = createBrowserRouter([
  { path: "/", element: <Workbench />, errorElement: <Recovery failed /> },
  { path: "*", element: <Recovery /> },
]);
