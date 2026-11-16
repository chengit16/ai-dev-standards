# React 前端规范

适用于采用本技术栈的新项目，配合[通用工程规范](../common/engineering.md)使用。已有项目接入时保留有效的请求层和现有配置，按实际改动补齐边界，不整体迁移。

## 固定技术选型

| 职责 | 首版选型与用法 |
| --- | --- |
| 构建与类型 | React、TypeScript、Vite、pnpm。开启 TypeScript `strict`，固定包管理器版本并维护锁文件。 |
| 组件 | Ant Design。表单、弹窗、表格优先复用组件；由应用入口的 `ConfigProvider` 统一语言和主题，通过公开 Token 和属性定制。 |
| 样式 | UnoCSS 用于常规布局、间距、响应式和状态样式；全局样式、焦点与复杂选择器可使用受控 CSS。集中维护语义设计变量，条件样式使用可静态识别的完整类名。 |
| 路由 | React Router。统一维护布局、路由、登录守卫与错误页；后端菜单驱动的路由按项目需要引入。客户端守卫不承担服务端授权。 |
| 客户端状态 | Zustand。用于跨页面共享的客户端状态，按领域分 Store，组件订阅所需片段。持久化采用字段白名单，只保存适合持久化的偏好。 |
| 常规 HTTP | Axios。由唯一 Client 入口封装；不在页面、组件、Hook 或 Store 里直接使用 Axios 或 `fetch` 发业务请求。 |

## 模块与状态归属

- `app/` 装配应用壳和 Provider，`routes/` 维护路由；`pages/{domain}/{feature}/` 放页面、业务 Hook 和私有组件。跨页面组件放 `components/`，公共组件不依赖具体路由。
- `api/client.ts` 维护传输边界，`api/services/` 按领域组织接口；`store/` 维护共享客户端状态，`styles/` 维护 Token 和全局样式。目录按真实职责建立。
- 服务端数据由页面业务 Hook 经 Service 管理；更新成功后重新读取或精确更新受影响的数据。首版不默认安装 TanStack Query；确需跨页面查询缓存、请求去重或后台刷新时再引入。查询键须覆盖工作区、资源、筛选和分页等影响结果的条件。
- 表单草稿、校验和弹窗状态优先留在拥有它们的组件或局部 Hook。请求失败保留输入，重新查询不覆盖未保存草稿。可分享、可刷新恢复的筛选和定位放 URL；不在 Store 重复保存 URL 或服务端数据。
- 切换账号或工作区时，取消或隔离旧请求与订阅，并清理受影响的状态和缓存。即使旧工作区的列表响应晚到，也不能覆盖当前页面。

## HTTP 请求

固定调用链：页面或业务 Hook → 领域 Service → Axios Client。

| 层 | 职责 |
| --- | --- |
| Client | 集中设置基址、请求凭证、超时、取消和错误归一化。按协议区分会话失效、取消、连接异常和服务端返回。请求中断只停止本地等待，不能当作服务端已撤销。 |
| Service | 维护路径、方法、参数、返回类型与数据转换。未知响应先验证，再返回可信类型。后端字段和协议差异收敛在这一层。 |
| 页面或业务 Hook | 管理加载、空数据、成功、失败及恢复动作；按接口支持区分无权和冲突。提交期间防重复触发。会话失效在应用入口统一处理，业务反馈由当前页面负责，避免重复提示。 |

- 基址、认证方式、响应结构和超时时间由接口契约及部署决定；不复制参考项目的固定包裹格式或会话刷新协议。需要刷新会话时集中处理并限制重放，默认不自动重试写请求；确有幂等保证时才配置有限重试。
- SSE、流式读取、下载或上传放在 `api/` 的专用模块，按协议选择合适的传输实现；例如流式响应可用 `fetch` 或 `EventSource`。专用模块仍遵守凭证范围、取消和错误边界。
- 浏览器存储、URL、日志和埋点不记录密钥、Cookie 或长期令牌；富文本和用户生成内容按不可信输入处理。

## 编写与验证

- 组件及类型用 `PascalCase`，函数与变量用 `camelCase`，Hook 用 `useXxx`。公开 Props 只暴露调用方所需的数据和回调。外部未知值用 `unknown` 收窄，不用断言掩盖未验证状态。
- 新增手写 TS/TSX 或实际修改文件职责时，在首个 `import` 前使用中文 `@description`；为新增或修改的公开组件、Hook、Service 和类型补充中文 JSDoc。说明职责、关键 Props、回调时机或副作用；生成文件、第三方文件和纯再导出入口免加文件头。
- 验证请求取消、失败恢复和关键用户流程。界面改动按影响验证桌面、窄屏、键盘和焦点；路由改动验证刷新、深链和前进后退。采用项目已有检查脚本及格式化配置。

## 参考与取舍

提取日期：2026-11-16。

| 来源版本 | 参考位置 | 采用内容 |
| --- | --- | --- |
| `main-platform@ee79adac06934bff9f600fbf04dc11cbeefd0e4f` | `docs/rules/coding-standards.md`、`src/api/apiClient.ts`、`src/App.tsx`、`uno.config.ts` | Zustand、React Router、UnoCSS、Axios 单一入口与领域 Service。 |
| `release-harbor@051696e909f2aabe22d9cc8f12dce183eaeee1b9` | `docs/governance/frontend-code-standards.md`、`apps/web/src/main.tsx`、`apps/web/src/api/client.ts` | Ant Design 直接接入、全局主题、响应运行时解码。 |
| `KnowSpace@cca5e6696ee8c38e919042df8cd144faaa97e1a8` | `docs/2026-09-23/开发基线/governance/frontend-code-standards.md`、`apps/web/src/main.tsx` | 工作区状态隔离、React Router 与查询缓存边界。 |

技术组合按本工具包已确认的选型执行。参考项目的内部组件库、微前端桥接、动态菜单协议与旧错误拦截实现不纳入通用模板。
