# 舆情分析助手 UI 原型 - 开发文档

## 一、项目概述

基于 **Taro 3.6** + **Taro UI 3.3** 的多端 UI 原型，支持 **Web（H5）** 与 **微信/支付宝/百度小程序**。实现整体框架（顶部设置与标题、底部首页/我的）、首页（搜索、新闻热点、历史搜索）、结果页（新闻汇总 / 思考过程 / 分析结果 三标签）及「我的」页。

### 1.1 技术栈

| 技术 | 版本 | 说明 |
|------|------|------|
| Taro | 3.6.32 | 多端框架 |
| React | 18.x | UI 层 |
| TypeScript | 5.x | 类型与工程化 |
| Taro UI | 3.3.x | 组件库 |
| Sass | 1.69+ | 样式预处理 |

### 1.2 兼容说明

- **Taro 4.x** 与 taro-ui 存在兼容问题，本项目采用 **Taro 3.6.x** 稳定组合。
- 推荐 Node.js **16.20+**（或 18 LTS）。

---

## 二、项目结构

```
yuqing-app/
├── config/
│   └── index.ts              # 编译与工程配置
├── src/
│   ├── app.config.ts         # 应用配置（页面路由、tabBar、窗口）
│   ├── app.ts                # 应用入口
│   ├── app.scss              # 全局样式（含 taro-ui 引入）
│   ├── index.html            # H5 入口
│   ├── assets/               # 静态资源
│   ├── components/
│   │   └── NavHeader/        # 顶部导航（标题 + 设置/返回）
│   │       ├── index.tsx
│   │       └── index.scss
│   └── pages/
│       ├── index/            # 首页
│       │   ├── index.tsx
│       │   ├── index.config.ts
│       │   └── index.scss
│       ├── result/           # 结果页
│       │   ├── index.tsx
│       │   ├── index.config.ts
│       │   └── index.scss
│       └── mine/             # 我的
│           ├── index.tsx
│           ├── index.config.ts
│           └── index.scss
├── assets/                   # 根目录资源（tabBar 图标等）
│   ├── tab-home.png
│   ├── tab-home-active.png
│   ├── tab-mine.png
│   └── tab-mine-active.png
├── package.json
├── tsconfig.json
├── babel.config.js
└── project.config.json       # 微信小程序项目配置
```

---

## 三、整体框架布局

### 3.1 顶部：NavHeader

- **组件路径**：`src/components/NavHeader/`
- **能力**：标题居中；可选左侧返回、右侧设置图标；适配小程序胶囊/状态栏高度。
- **使用示例**：

```tsx
<NavHeader
  title="舆情分析助手"
  showSettings
  onSettingsClick={() => Taro.navigateTo({ url: '/pages/mine/index' })}
/>
```

```tsx
<NavHeader title="分析结果" showBack />
```

### 3.2 底部：TabBar

- **配置**：`src/app.config.ts` 的 `tabBar`。
- **项**：首页（`pages/index/index`）、我的（`pages/mine/index`）。
- **图标**：`assets/` 下 `tab-home.png`、`tab-home-active.png`、`tab-mine.png`、`tab-mine-active.png`。当前为占位图，可替换为 81×81 像素图标以适配不同分辨率。

---

## 四、页面说明

### 4.1 首页（pages/index）

- **功能**
  - **搜索**：`AtSearchBar`，输入关键词后点击「搜索」或确认，写入历史并跳转结果页，带 `keyword` 参数。
  - **新闻热点**：首条用 `AtNoticebar`（跑马灯），其余为竖向列表（· 列表）。
  - **历史搜索**：本地存储 `yuqing_search_history`，用 `AtTag` 展示；点击标签用该词跳转结果页；支持「清空」。
- **涉及 Taro UI**：AtSearchBar、AtNoticebar、AtTag。
- **路由**：`/pages/index/index`（tabBar 项）。

### 4.2 结果页（pages/result）

- **入口**：首页搜索或点击历史标签，URL 带 `?keyword=xxx`。
- **顶部**：NavHeader 标题为当前关键词，左侧返回。
- **三个主标签（AtTabs）**

| 标签 | 内容 |
|------|------|
| **标签 1 - 新闻汇总** | 新闻快讯列表（AtList/AtListItem）+ 下方「分析结论」文案卡片。 |
| **标签 2 - 思考过程** | 子标签（步骤一/二/三）；选中子标签后模拟流式输出（逐字追加），用 AtIcon loading + 文本展示。 |
| **标签 3 - 分析结果** | 文字汇总段落 + 「数据概览」区（AtProgress 表示情感分布、热度指数等，可后续替换为图表）。 |

- **涉及 Taro UI**：AtTabs、AtTabsPane、AtList、AtListItem、AtProgress、AtIcon。
- **路由**：`/pages/result/index`（非 tabBar，需从首页跳转）。

### 4.3 我的（pages/mine）

- **功能**：用户信息区（AtAvatar + 文案）、菜单列表（AtList/AtListItem）：搜索历史（跳首页）、收藏与订阅、消息通知、设置（当前为 Toast 占位）。
- **涉及 Taro UI**：AtAvatar、AtList、AtListItem。
- **路由**：`/pages/mine/index`（tabBar 项）。

---

## 五、运行与构建

### 5.1 安装依赖

```bash
cd yuqing-app
npm install
```

若安装 taro-ui 或 Taro 相关包报错，请使用：

```bash
npm install --legacy-peer-deps
```

### 5.2 开发

```bash
# H5（Web 原型，默认 http://localhost:10086）
npm run dev:h5

# 微信小程序（需先安装微信开发者工具，并导入 dist/weapp 目录）
npm run dev:weapp

# 支付宝小程序
npm run dev:alipay

# 百度小程序
npm run dev:swan
```

### 5.3 构建

```bash
npm run build:h5      # 输出 dist/h5
npm run build:weapp   # 输出 dist/weapp
npm run build:alipay
npm run build:swan
```

- **H5**：将 `dist/h5` 部署到任意静态服务器即可。
- **小程序**：用对应开发者工具打开 `dist/weapp`（或 alipay/swan）并上传。

---

## 六、配置要点

### 6.1 设计稿与尺寸

- `config/index.ts` 中 `designWidth: 750`，按 750 设计稿编写样式，Taro 会做 rpx 转换。
- 如需修改设计稿宽度，可调整 `deviceRatio` 与 `designWidth`。

### 6.2 自定义导航栏

- 各页 `index.config.ts` 中设置 `navigationStyle: 'custom'`，页面内使用固定定位的 `NavHeader`，需为内容区预留 `padding-top`（如 120px），避免被导航遮挡。

### 6.3 TabBar 图标

- 图标路径相对于**项目根目录**，构建时会通过 `copy.patterns` 将 `assets` 拷到输出目录。
- 替换为正式图标时，建议尺寸 81×81 px，格式 PNG。

---

## 七、扩展建议

1. **结果页标签 1**：将 `MOCK_NEWS` 改为接口请求，分析结论改为接口返回字段。
2. **标签 2 流式**：将当前定时器模拟改为 WebSocket 或 SSE，按后端推送内容追加到 `streamText`。
3. **标签 3 图表**：在 H5 可引入 ECharts / F2；小程序侧使用 Taro 生态图表组件或 canvas 封装。
4. **我的页**：接入登录态、头像与昵称、设置项（主题、通知开关等）。
5. **新闻热点**：从接口拉取列表，首条继续用 Noticebar，其余用列表或可点击跳转详情。

---

## 八、参考

- [Taro 3.x 文档](https://docs.taro.zone/docs/3.x)
- [Taro UI 文档](https://taro-ui.jd.com/)
- [Taro UI GitHub](https://github.com/jd-opensource/taro-ui)
