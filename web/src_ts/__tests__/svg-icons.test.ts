/**
 * Anti-regression test for all SVG icon files in web/static/icons/.
 *
 * Verifies:
 * - Every .svg file exists and is readable
 * - Contains valid XML with <svg> root
 * - Has required attributes: xmlns, viewBox, width, height
 * - Has at least one meaningful path/circle/rect element
 * - Has currentColor or explicit fill/stroke where appropriate
 */

import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'fs';
import { resolve } from 'path';

const ICONS_DIR = resolve(__dirname, '../../static/icons');

interface SvgInfo {
  filename: string;
  content: string;
  hasViewBox: boolean;
  hasXmlns: boolean;
  hasWidth: boolean;
  hasHeight: boolean;
  hasPath: boolean;
  hasCircle: boolean;
  hasRect: boolean;
  hasPolygon: boolean;
  hasLine: boolean;
  hasCurrentColor: boolean;
  hasExplicitFill: boolean;
  hasExplicitStroke: boolean;
  isWellFormed: boolean;
}

function analyzeSvg(filename: string, content: string): SvgInfo {
  const lower = content.toLowerCase();
  return {
    filename,
    content,
    hasViewBox: content.includes('viewBox='),
    hasXmlns: content.includes('xmlns='),
    hasWidth: content.includes('width='),
    hasHeight: content.includes('height='),
    hasPath: lower.includes('<path'),
    hasCircle: lower.includes('<circle'),
    hasRect: lower.includes('<rect'),
    hasPolygon: lower.includes('<polygon'),
    hasLine: lower.includes('<line'),
    hasCurrentColor: lower.includes('currentcolor'),
    hasExplicitFill: lower.includes('fill=') && !lower.includes('fill="none"') && !lower.includes('fill="currentcolor"'),
    hasExplicitStroke: lower.includes('stroke=') && !lower.includes('stroke="none"') && !lower.includes('stroke="currentcolor"'),
    isWellFormed: content.trimStart().startsWith('<svg') && content.trimEnd().endsWith('</svg>'),
  };
}

const SVG_FILES = readdirSync(ICONS_DIR).filter(f => f.endsWith('.svg'));

describe('SVG icon files', () => {
  it('all SVG files are present and readable', () => {
    expect(SVG_FILES.length).toBeGreaterThanOrEqual(9);
    SVG_FILES.forEach(f => {
      const content = readFileSync(resolve(ICONS_DIR, f), 'utf-8');
      expect(content.length).toBeGreaterThan(50);
    });
  });

  describe.each(SVG_FILES)('%s', (filename) => {
    const content = readFileSync(resolve(ICONS_DIR, filename), 'utf-8');
    const info = analyzeSvg(filename, content);

    it('has valid SVG structure', () => {
      expect(info.isWellFormed).toBe(true);
    });

    it('has xmlns attribute', () => {
      expect(info.hasXmlns).toBe(true);
    });

    it('has viewBox attribute', () => {
      expect(info.hasViewBox).toBe(true);
    });

    it('has width and height', () => {
      expect(info.hasWidth).toBe(true);
      expect(info.hasHeight).toBe(true);
    });

    it('has at least one visible element (path/circle/rect/polygon)', () => {
      const hasElement = info.hasPath || info.hasCircle || info.hasRect || info.hasPolygon;
      expect(hasElement).toBe(true);
    });

    it('uses currentColor or explicit color', () => {
      // Every SVG must have either currentColor for stroke/fill or an explicit color
      const hasColor = info.hasCurrentColor || info.hasExplicitFill || info.hasExplicitStroke;
      expect(hasColor).toBe(true);
    });
  });
});

describe('icon type-specific checks', () => {
  const contents: Record<string, string> = {};
  SVG_FILES.forEach(f => {
    contents[f] = readFileSync(resolve(ICONS_DIR, f), 'utf-8');
  });

  it('stop.svg has explicit red fill', () => {
    const svg = contents['stop.svg'];
    expect(svg).toContain('#ff3333');
    expect(svg).toContain('<circle');
  });

  it('bell.svg has explicit red stroke', () => {
    const svg = contents['bell.svg'];
    expect(svg).toContain('#ff3333');
    expect(svg).toContain('<path');
  });

  it('robot.svg has robot face (eyes + mouth)', () => {
    const svg = contents['robot.svg'].toLowerCase();
    // Robot has eye rectangles and mouth path
    expect(svg.match(/<rect/g)?.length).toBeGreaterThanOrEqual(3);
    expect(svg).toContain('q12 18 15 16');
  });

  it('send.svg is a paper plane (polygon + line)', () => {
    const svg = contents['send.svg'].toLowerCase();
    expect(svg).toContain('<polygon');
    expect(svg).toContain('<line');
  });

  it('mic.svg has microphone shape (path + rect + lines)', () => {
    const svg = contents['mic.svg'].toLowerCase();
    expect(svg.match(/<path/g)?.length).toBeGreaterThanOrEqual(2);
    expect(svg).toContain('<line');
  });

  it('attach.svg is a paperclip (single path)', () => {
    const svg = contents['attach.svg'].toLowerCase();
    const pathMatches = svg.match(/<path/g);
    expect(pathMatches?.length).toBe(1);
  });

  it('status icons are colored filled circles', () => {
    const statusFiles = SVG_FILES.filter(f => f.startsWith('status-'));
    expect(statusFiles.length).toBe(4);
    statusFiles.forEach(f => {
      const svg = contents[f].toLowerCase();
      // status SVG is just a circle with explicit fill color
      expect(svg).toContain('<circle');
      expect(svg).toContain('fill="#');
      expect(svg).not.toContain('stroke');
    });
  });

  it('capability icons have stroke-based design', () => {
    const capIcons = ['reasoning.svg', 'tools.svg', 'image.svg', 'video.svg', 'audio.svg'];
    capIcons.forEach(f => {
      const svg = contents[f]?.toLowerCase();
      if (!svg) return;
      // All capability icons use stroke + currentColor
      expect(svg).toContain('currentcolor');
      expect(svg).toContain('stroke-width');
    });
  });
});
