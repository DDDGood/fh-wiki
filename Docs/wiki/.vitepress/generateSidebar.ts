import { readFileSync, readdirSync, existsSync } from 'node:fs'
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
  keywords?: string[]
  order: number
}

function loadCategories(): CategoryDef[] {
  const raw = readFileSync(CATEGORY_YML, 'utf-8')
  const parsed = yaml.load(raw) as { categories: CategoryDef[] }
  return parsed.categories.sort((a, b) => a.order - b.order)
}

function parseFrontmatter(filepath: string): Record<string, any> {
  try {
    const content = readFileSync(filepath, 'utf-8')
    const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/)
    if (!match) return {}
    return (yaml.load(match[1]) as Record<string, any>) || {}
  } catch {
    return {}
  }
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
          order: fm.order ?? 999,
          status: fm.status || 'stable'
        }
      })
      .sort((a, b) => a.order - b.order || a.text.localeCompare(b.text, 'zh-Hant'))
      .map(({ text, link, status }) => ({
        text: status === 'draft' ? `${text} (草稿)` : text,
        link
      }))

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

export function generateFeatures() {
  const cats = loadCategories()
  return cats.map(cat => ({
    icon: cat.icon,
    title: cat.name,
    details: cat.short,
    link: `/${cat.slug}/`
  }))
}
