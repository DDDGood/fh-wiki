import { defineConfig } from 'vitepress'
import { generateSidebar, generateNav, generateFeatures } from './generateSidebar'

export default defineConfig({
  title: 'Forza Horizon 攻略庫',
  description: '繁體中文 Forza Horizon 攻略資料庫',
  lang: 'zh-TW',
  lastUpdated: true,
  cleanUrls: true,

  // GitHub Pages 部署對應 https://dddgood.github.io/fh-wiki/
  // 本地 dev 時 VitePress 會處理 base prefix，訪問 http://localhost:5173/fh-wiki/
  base: '/fh-wiki/',

  srcExclude: ['**/_raw/**', '**/_sources/**', '**/_category.yml'],

  ignoreDeadLinks: true,

  themeConfig: {
    nav: generateNav(),
    sidebar: generateSidebar(),

    outline: { level: [2, 3], label: '本頁大綱' },
    docFooter: { prev: '上一篇', next: '下一篇' },
    lastUpdatedText: '最後更新',
    darkModeSwitchLabel: '外觀',
    returnToTopLabel: '回到頂端',
    sidebarMenuLabel: '選單',

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
                displayDetails: '顯示細節',
                backButtonTitle: '返回',
                footer: { selectText: '選擇', navigateText: '切換', closeText: '關閉' }
              }
            }
          }
        }
      }
    },

    footer: {
      message: '攻略資料可追溯至 _sources/ 原始整理版',
      copyright: 'Forza Horizon 攻略庫'
    }
  }
})

// 把 features（首頁大分類卡片）輸出給 index.md frontmatter 用（暫未使用，保留給未來）
export const features = generateFeatures()
