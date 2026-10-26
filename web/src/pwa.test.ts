/**
 * O painel tem de continuar instalável na tela de início.
 *
 * É a única forma de o dono ter o sistema no iPhone dele: app nativo iOS exigiria macOS, Xcode e
 * conta de desenvolvedor Apple, e a instalação por cabo depende do mesmo Mac.
 *
 * A falha aqui é sempre silenciosa. Um caminho de ícone errado, uma vírgula a mais no JSON ou o
 * `apple-touch-icon` renomeado não quebram nada visível: o site abre normalmente e o navegador
 * simplesmente deixa de oferecer a instalação, ou o iPhone usa uma miniatura da página como ícone.
 * Ninguém percebe até tentar instalar de novo, meses depois.
 */

import { readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const PUBLIC = join(process.cwd(), 'public')
const manifesto = JSON.parse(readFileSync(join(PUBLIC, 'manifest.webmanifest'), 'utf8'))
const html = readFileSync(join(process.cwd(), 'index.html'), 'utf8')

describe('manifesto', () => {
  it('declara o que o navegador precisa para oferecer a instalação', () => {
    expect(manifesto.name).toBeTruthy()
    expect(manifesto.short_name).toBeTruthy()
    // sem "standalone" o atalho abre dentro do Safari, com barra de endereço — não parece aplicativo
    expect(manifesto.display).toBe('standalone')
    expect(manifesto.start_url).toBe('/')
  })

  it('usa a obsidiana da marca na abertura e na barra de status', () => {
    expect(manifesto.background_color).toBe('#0B0B0D')
    expect(manifesto.theme_color).toBe('#0B0B0D')
  })

  it('todo ícone declarado existe de fato', () => {
    expect(manifesto.icons.length).toBeGreaterThan(0)
    for (const icone of manifesto.icons) {
      const caminho = join(PUBLIC, icone.src.replace(/^\//, ''))
      expect(existsSync(caminho), `ícone declarado e ausente: ${icone.src}`).toBe(true)
    }
  })

  it('tem os dois tamanhos que o Android pede', () => {
    const tamanhos = new Set(manifesto.icons.map((i: { sizes: string }) => i.sizes))
    expect(tamanhos.has('192x192')).toBe(true)
    expect(tamanhos.has('512x512')).toBe(true)
  })
})

describe('iPhone', () => {
  it('aponta para o manifesto e para o ícone da tela de início', () => {
    expect(html).toContain('rel="manifest"')
    expect(html).toContain('rel="apple-touch-icon"')
  })

  it('o apple-touch-icon é PNG e existe', () => {
    // o iOS IGNORA SVG aqui: sem um PNG, ele usa uma miniatura da página como ícone
    const m = html.match(/rel="apple-touch-icon"\s+href="([^"]+)"/)
    expect(m, 'apple-touch-icon sem href').toBeTruthy()
    const href = m![1]
    expect(href.endsWith('.png')).toBe(true)
    expect(existsSync(join(PUBLIC, href.replace(/^\//, '')))).toBe(true)
  })

  it('abre em tela cheia, sem a barra do Safari', () => {
    expect(html).toContain('name="apple-mobile-web-app-capable" content="yes"')
    expect(html).toContain('name="mobile-web-app-capable" content="yes"')
  })

  it('a viewport cobre o recorte da tela', () => {
    // sem viewport-fit=cover o conteúdo não passa sob a faixa de status, e sobram tarjas brancas
    expect(html).toContain('viewport-fit=cover')
  })
})
