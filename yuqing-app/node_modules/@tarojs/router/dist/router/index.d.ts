import { MpaRouterConfig, SpaRouterConfig } from '../../types/router';
declare class RouterConfig {
    private static __config;
    static set config(e: SpaRouterConfig | MpaRouterConfig);
    static get config(): SpaRouterConfig | MpaRouterConfig;
    static get pages(): string[];
    static get router(): import("../types/router").Router;
    static get mode(): "hash" | "browser" | "multi";
    static get customRoutes(): Record<string, string | string[]>;
    // 这个方法不考虑 basename 和 customRoutes，只判断原始的 url 是否在 pages 中
    static isPage(url?: string): boolean;
}
export { RouterConfig };
