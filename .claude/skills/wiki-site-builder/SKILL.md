---
name: wiki-site-builder
description: Forza Horizon 攻略庫靜態網站（VitePress + GitHub Pages）建置與維護助手。當使用者要求「建靜態網站」「部署到 GitHub Pages」「修網站樣式」「新增分類頁」「更新側邊欄」時使用。將 Docs/wiki/ 轉換為可搜尋、可瀏覽、可部署的靜態網站。
user-invokable: true
argument-hint: "[子命令]  init | sidebar | deploy | dev  （留白 = 顯示狀態）"
---

# wiki-site-builder（靜態網站建置與維護）

## 技術棧

| 技術 | 用途 |
|------|------|
| **VitePress** | 靜態網站產生器（吃 Markdown + frontmatter） |
| **Vue 3** | VitePress 內建；自訂查詢組件時使用 |
| **js-yaml** | 讀 `_category.yml` 產生側邊欄 |
| **GitHub Actions** | 推送 main 自動部署到 gh-pages |

**為什麼選 VitePress 不是自幹 Vue**：本專案內容本身就是 Markdown，VitePress 零改寫就能跑；搜尋、暗色主題、側邊欄、導航全內建。

---

## 目錄結構（建置完成後）

```
d:/Projects/Forza Horizon/
├── Docs/
│   ├── _raw/           # 不發佈
│   ├── _sources/       # 不發佈（可選擇要不要公開；預設不）
│   └── wiki/           # ⭐ VitePress srcDir
│       ├── .vitepress/
│       │   ├── config.ts           # 站台設定
│       │   ├── theme/              # （可選）自訂主題
│       │   └── generateSidebar.ts  # 讀 _category.yml 產側邊欄
│       ├── _category.yml
│       ├── index.md                # 首頁
│       ├── tuning/
│       │   ├── index.md            # 分類總覽（綜覽）
│       │   └── *.md
│       └── ...
├── package.json                    # dev / build / deploy 指令
├── .github/
│   └── workflows/
│       └── deploy.yml              # GitHub Pages 部署
└── .gitignore                      # node_modules, .vitepress/dist
```

---

## 子命令

### `init` — 初始化網站骨架（一次性）

**前置檢查**：
- 確認 `package.json` 不存在（若存在先詢問）
- 確認 `Docs/wiki/` 存在且有 `_category.yml`
- 確認 Node.js 可用（`node --version`）

**步驟**：

1. **建立 `package.json`**（專案根）：

```json
{
  "name": "forza-horizon-wiki",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "docs:dev": "vitepress dev Docs/wiki",
    "docs:build": "vitepress build Docs/wiki",
    "docs:preview": "vitepress preview Docs/wiki"
  },
  "devDependencies": {
    "vitepress": "^1.5.0",
    "vue": "^3.5.0",
    "js-yaml": "^4.1.0"
  }
}
```

2. **建立 `Docs/wiki/.vitepress/config.ts`**：

```ts
import { defineConfig } from 'vitepress'
import { generateSidebar, generateNav } from './generateSidebar'

export default defineConfig({
  title: 'Forza Horizon 攻略庫',
  description: '繁體中文 Forza Horizon 攻略資料庫',
  lang: 'zh-TW',
  lastUpdated: true,
  cleanUrls: true,

  // GitHub Pages base（請依 repo 名修改）
  base: '/forza-horizon-wiki/',

  // 忽略不發佈的資料夾
  srcExclude: ['**/_raw/**', '**/_sources/**', '**/_category.yml'],

  themeConfig: {
    nav: generateNav(),
    sidebar: generateSidebar(),

    outline: { level: [2, 3], label: '本頁大綱' },
    docFooter: { prev: '上一篇', next: '下一篇' },
    lastUpdatedText: '最後更新',

    search: {
      provider: 'local',
      options: {
        locales: {
          root: {
            translations: {
              button: { buttonText: '搜尋攻略', buttonAriaLabel: '搜尋' },
              modal: {
                noResultsText: '找不到結果',
                resetButtonTitle: '清除',
                footer: { selectText: '選擇', navigateText: '切換' }
              }
            }
          }
        }
      }
    },

    socialLinks: [
      // { icon: 'github', link: 'https://github.com/USER/REPO' }
    ],

    footer: {
      message: '攻略資料可追溯至 _sources/ 原始整理版',
      copyright: 'Forza Horizon 攻略庫'
    }
  }
})
```

3. **建立 `Docs/wiki/.vitepress/generateSidebar.ts`**：

```ts
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import yaml from 'js-yaml'

const __dirname = dirname(fileURLToPath(import.meta.url))
const WIKI_ROOT = join(__dirname, '..')
const CATEGORY_YML = join(WIKI_ROOT, '_category.yml')

interface CategoryDef {
  slug: string
  name: string
  icon: string
  short: string
  order: number
}

function loadCategories(): CategoryDef[] {
  const raw = readFileSync(CATEGORY_YML, 'utf-8')
  const parsed = yaml.load(raw) as { categories: CategoryDef[] }
  return parsed.categories.sort((a, b) => a.order - b.order)
}

function parseFrontmatter(filepath: string): Record<string, any> {
  const content = readFileSync(filepath, 'utf-8')
  const match = content.match(/^---\n([\s\S]*?)\n---/)
  if (!match) return {}
  try { return yaml.load(match[1]) as Record<string, any> } catch { return {} }
}

export function generateSidebar() {
  const cats = loadCategories()
  const sidebar: Record<string, any> = {}

  for (const cat of cats) {
    const catDir = join(WIKI_ROOT, cat.slug)
    if (!existsSync(catDir)) continue

    const files = readdirSync(catDir)
      .filter(f => f.endsWith('.md') && f !== 'index.md')
      .map(f => {
        const fm = parseFrontmatter(join(catDir, f))
        return {
          text: fm.title || f.replace(/\.md$/, ''),
          link: `/${cat.slug}/${f.replace(/\.md$/, '')}`,
          order: fm.order ?? 999
        }
      })
      .sort((a, b) => a.order - b.order || a.text.localeCompare(b.text))

    sidebar[`/${cat.slug}/`] = [
      {
        text: `${cat.icon} ${cat.name}`,
        items: [
          { text: '分類總覽', link: `/${cat.slug}/` },
          ...files
        ]
      }
    ]
  }

  return sidebar
}

export function generateNav() {
  const cats = loadCategories()
  return cats.map(cat => ({
    text: `${cat.icon} ${cat.name}`,
    link: `/${cat.slug}/`
  }))
}
```

4. **建立 `.gitignore`**（若不存在）：
   ```
   node_modules/
   Docs/wiki/.vitepress/dist/
   Docs/wiki/.vitepress/cache/
   ```

5. **建立 `.github/workflows/deploy.yml`**：

```yaml
name: Deploy Wiki to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: npm ci
      - run: npm run docs:build
      - uses: actions/upload-pages-artifact@v3
        with:
          path: Docs/wiki/.vitepress/dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

6. **為每個分類建立 `index.md`**（綜覽頁）：

```markdown
---
title: 車輛調校
---

# 🔧 車輛調校

{_category.yml 的 short 欄位內容}

## 主題列表

<!-- 此清單由 wiki-site-builder 維護；亦可改為自訂 Vue 組件自動渲染 -->

- [差速器調校](./差速器.md)
- [阻尼調校](./阻尼.md)
- ...

## 新手從哪開始？

建議閱讀順序：
1. 先看 [調校基礎](./調校基礎.md)
2. 再看 [差速器](./差速器.md) 與 [阻尼](./阻尼.md)
3. 進階再讀 [齒比](./齒比.md)
```

7. **執行 `npm install`** 並詢問使用者要不要 `npm run docs:dev` 預覽。

### `sidebar` — 重新產生側邊欄

VitePress 啟動時會執行 `generateSidebar.ts`，所以通常不需要手動。但若：
- 新增了分類（改 `_category.yml`）
- 想檢查側邊欄結構是否正確
- 懷疑 frontmatter 解析失敗

執行：
```bash
npm run docs:build
```
或啟動 dev server 看即時結果。

### `deploy` — 部署到 GitHub Pages

**前提**：已 push 到 GitHub repo，且 repo Settings → Pages → Source 設為 "GitHub Actions"。

兩種部署方式：

**A. 自動（推薦）**：已設定 `.github/workflows/deploy.yml`，只要 push 到 main 就會自動部署。

**B. 手動**：
```bash
npm run docs:build
npx gh-pages -d Docs/wiki/.vitepress/dist
```

### `dev` — 本地開發

```bash
npm run docs:dev
```
預設 http://localhost:5173

---

## 首頁設計（Q2：方便綜覽大分類）

`Docs/wiki/index.md` 使用 VitePress 的 `layout: home` 配上 `features` 區塊呈現大分類卡片：

```markdown
---
layout: home

hero:
  name: Forza Horizon 攻略庫
  tagline: 跨來源精煉、持續更新的繁體中文攻略
  actions:
    - theme: brand
      text: 從頭開始
      link: /tuning/
    - theme: alt
      text: 全站搜尋
      link: /?search=true

features:
  - icon: 🔧
    title: 車輛調校
    details: 懸吊、差速器、阻尼、齒比、胎壓等可調參數的原理與實用數值
    link: /tuning/
  - icon: ⚙️
    title: 車輛改裝
    details: 配件升級與 PI 性價比思路
    link: /upgrades/
  - icon: 🏁
    title: 駕駛操作
    details: 走線、煞車、過彎、漂移
    link: /driving/
  - icon: 🚗
    title: 車輛介紹
    details: 單車分析、車種類型、車系比較
    link: /cars/
  - icon: 🎮
    title: 遊戲設定
    details: 控制器、方向盤、輔助選項
    link: /settings/
  - icon: 🏆
    title: 活動與賽事
    details: 季節、故事、EventLab、成就
    link: /events/
---
```

`features` 陣列應與 `_category.yml` 保持同步。建議寫一個小工具（或在 `generateSidebar.ts` 中擴充）讀 YAML 直接輸出 features，避免手動維護兩份。

---

## 常見任務

### 新增分類

1. 編輯 `Docs/wiki/_category.yml`，append 新分類
2. `mkdir Docs/wiki/{slug}`
3. 建 `Docs/wiki/{slug}/index.md`
4. `npm run docs:dev` 驗證側邊欄
5. 更新首頁 `features`

### 改站台標題、base path

編輯 `Docs/wiki/.vitepress/config.ts`

### 自訂排序

在 wiki 檔 frontmatter 加 `order: {數字}`，`generateSidebar.ts` 會依 order 排序（預設 999）。

### 讓 frontmatter 的 tags 變成可點擊的標籤頁

這需要自訂 Vue 組件掃全站 frontmatter。**初期不做**，累積到 20+ 篇再考慮。屆時：
1. 寫 `.vitepress/theme/components/TagCloud.vue`
2. 在某頁引用 `<TagCloud />`
3. 用 `@vue/content-loader` 或自己寫 glob 掃 frontmatter

---

## 不可違反

1. **`_sources/` 與 `_raw/` 不得發佈**：`srcExclude` 必須包含它們
2. **base path 要對**：GitHub Pages 是 `https://USER.github.io/REPO/`，`base` 必須設為 `/REPO/`
3. **不動 wiki 內容**：本 skill 只管建站與樣式，內容歸 `wiki-integrator` / `wiki-doc-writer` 管
4. **部署前本地先 build**：避免把 broken links 推上去

---

## 失敗模式

| 症狀 | 原因 | 處置 |
|------|------|------|
| 側邊欄空 | `_category.yml` 解析失敗 | 檢查 YAML 縮排；試 `node -e 'import("js-yaml").then(m => console.log(m.load(...)))'` |
| Dead links | wiki 檔互相引用路徑錯 | 設 `ignoreDeadLinks: true` 暫時放行，但要修 |
| GitHub Pages 404 | `base` 未設或錯 | 對齊 repo 名 |
| 中文檔名 URL 變亂碼 | 正常，GitHub Pages 會 URL-encode UTF-8 | 不影響功能，介意可改 slug 為英文 |
| `docs:build` 卡住 | 通常是某份 frontmatter 語法錯 | 看錯誤訊息指向的檔，修 YAML |

---

## 與其他 skill 的關係

- **消費**：`Docs/wiki/**/*.md` + `_category.yml`
- **不動**：`_sources/`、`_raw/`、wiki 檔內容
- **上游**：`wiki-integrator`、`wiki-doc-writer` 產出／更新內容
- **產出**：`Docs/wiki/.vitepress/dist/` 靜態網站、GitHub Pages 部署
