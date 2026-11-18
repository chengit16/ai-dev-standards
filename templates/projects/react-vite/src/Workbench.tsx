/** @description 展示工程和 API 的实际状态，支持重新检查和切换说明。 */
import config from "../starter.json";
import { Button, Switch } from "antd";
import { useEffect, useState } from "react";
import { requestMessage } from "./api/client";
import { checkHealth } from "./api/services/health";
import { usePreferencesStore } from "./store/usePreferencesStore";

type Connection =
  | { state: "loading" }
  | { state: "ready" }
  | { state: "failed"; message: string };

function ApiStatus() {
  const [attempt, setAttempt] = useState(0);
  const [connection, setConnection] = useState<Connection>({
    state: "loading",
  });

  useEffect(() => {
    const controller = new AbortController();
    async function probe() {
      try {
        await checkHealth(controller.signal);
        if (!controller.signal.aborted) setConnection({ state: "ready" });
      } catch (error) {
        // 新一轮检查或离开页面后忽略旧请求，防止它覆盖当前状态。
        if (!controller.signal.aborted)
          setConnection({ state: "failed", message: requestMessage(error) });
      }
    }
    void probe();
    return () => controller.abort();
  }, [attempt]);

  return (
    <>
      <p className="status" data-state={connection.state} role="status">
        {connection.state === "loading"
          ? "正在检查 API"
          : connection.state === "ready"
            ? "API 已连接"
            : connection.message}
      </p>
      <Button
        onClick={() => {
          setConnection({ state: "loading" });
          setAttempt((value) => value + 1);
        }}
        disabled={connection.state === "loading"}
      >
        重新检查
      </Button>
    </>
  );
}

/** 展示模板当前可用能力，独立前端不请求未配置的 API。 */
export function Workbench() {
  const { hasApi } = config;
  const showDetails = usePreferencesStore((state) => state.showDetails);
  const setShowDetails = usePreferencesStore((state) => state.setShowDetails);

  return (
    <main className="shell">
      <header className="flex items-center justify-between gap-4">
        <span className="brand">
          <span aria-hidden="true" />
          工程工作台
        </span>
        <Switch
          checked={showDetails}
          onChange={setShowDetails}
          aria-label="显示启动说明"
        />
      </header>
      <section className="overview">
        <h1>工程状态</h1>
        <p>前端已就绪</p>
      </section>
      <section className="panel" aria-labelledby="connection">
        <div>
          <h2 id="connection">后端连通性</h2>
          {showDetails && hasApi && (
            <p className="hint">
              通过开发代理访问 <code>/api/health</code>。
            </p>
          )}
        </div>
        <div>
          {hasApi ? (
            <ApiStatus />
          ) : (
            <p className="status" role="status">
              此工程使用独立前端模板
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
