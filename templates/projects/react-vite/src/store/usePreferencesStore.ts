/** @description 管理工作台展示偏好，只持久化面板显示设置。 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface Preferences {
  showDetails: boolean;
  setShowDetails: (value: boolean) => void;
}

/** 提供跨页面展示偏好，服务状态始终由当前请求确定。 */
export const usePreferencesStore = create<Preferences>()(
  persist(
    (set) => ({
      showDetails: true,
      setShowDetails: (showDetails) => set({ showDetails }),
    }),
    {
      name: "starter-workbench-preferences",
      partialize: ({ showDetails }) => ({ showDetails }),
    },
  ),
);
