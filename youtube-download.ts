/**
 * YouTube video download — download videos using yt-dlp with proxy auto-detection.
 *
 * Usage:
 *   opencli aiskill youtube-download https://www.youtube.com/watch?v=XqKcYMLMV6E
 *   opencli aiskill youtube-download XqKcYMLMV6E --quality 1080p --output ./downloads
 *
 * Requirements:
 *   - yt-dlp must be installed: pip install yt-dlp
 *   - A local proxy (Clash/V2Ray/etc.) for YouTube access
 *
 * Workflow:
 *   1. Auto-detect local proxy by probing common ports (7890, 1080, 10809, etc.)
 *   2. Extract video metadata (title) via browser CDP
 *   3. Download video + audio via yt-dlp with proxy, merge into MKV/MP4
 */

import { cli, Strategy } from '@jackwener/opencli/registry';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { access } from 'node:fs/promises';
import { constants } from 'node:fs';

const COMMON_PROXY_PORTS = [7890, 1080, 10809, 7891, 8118, 9090];

async function detectProxy(): Promise<string | null> {
  for (const port of COMMON_PROXY_PORTS) {
    try {
      const resp = await fetch(`http://127.0.0.1:${port}`, { signal: AbortSignal.timeout(2000) });
      // Any response means the port is alive
      return `http://127.0.0.1:${port}`;
    } catch {
      // Connection refused or timeout — try next port
      continue;
    }
  }
  return null;
}

function ytdlpDownload(
  url: string,
  outputDir: string,
  quality: string,
  proxy: string,
  extraArgs: string[] = [],
): Promise<{ title: string; status: string; size: string; path: string }> {
  return new Promise((resolve) => {
    const formatMap: Record<string, string> = {
      best: 'bestvideo+bestaudio/best',
      '4k': 'bestvideo[height<=2160]+bestaudio/best[height<=2160]',
      '1440p': 'bestvideo[height<=1440]+bestaudio/best[height<=1440]',
      '1080p': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
      '720p': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
      '480p': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
    };
    const format = formatMap[quality] || formatMap.best;

    const args = [
      '--proxy', proxy,
      '-f', format,
      '--merge-output-format', 'mkv',
      '-o', `${outputDir}/%(title)s.%(ext)s`,
      '--print', '%(title)s',
      '--print', '%(filesize_approx)s',
      ...extraArgs,
      url,
    ];

    const proc = spawn('yt-dlp', args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    proc.stdout?.on('data', (d: Buffer) => { stdout += d.toString(); });
    proc.stderr?.on('data', (d: Buffer) => { stderr += d.toString(); });

    proc.on('close', (code) => {
      const lines = stdout.trim().split('\n').filter(Boolean);
      const title = lines[0] || 'unknown';
      const sizeBytes = parseInt(lines[1] || '0', 10);
      const sizeStr = sizeBytes > 0 ? `${(sizeBytes / 1024 / 1024).toFixed(1)} MB` : 'unknown';

      if (code === 0) {
        resolve({ title, status: 'downloaded', size: sizeStr, path: resolve(outputDir, `${title}.mkv`) });
      } else {
        resolve({ title: 'download failed', status: 'failed', size: stderr.slice(-200) || 'unknown error', path: '' });
      }
    });
  });
}

cli({
  site: 'aiskill',
  name: 'youtube-download',
  description: 'Download YouTube videos via yt-dlp with proxy auto-detection',
  strategy: Strategy.COOKIE,
  browser: true,
  domain: 'www.youtube.com',
  args: [
    { name: 'url', required: true, positional: true, help: 'YouTube video URL or video ID' },
    { name: 'output', default: '.', help: 'Output directory' },
    { name: 'quality', default: 'best', help: 'Video quality: best, 4k, 1440p, 1080p, 720p, 480p' },
    { name: 'proxy', default: 'auto', help: 'Proxy URL (default: auto-detect from common ports)' },
  ],
  columns: ['title', 'quality', 'status', 'size', 'path'],
  func: async (page, kwargs) => {
    const url = String(kwargs.url).includes('youtube.com') || String(kwargs.url).includes('youtu.be')
      ? String(kwargs.url)
      : `https://www.youtube.com/watch?v=${kwargs.url}`;
    const outputDir = resolve(String(kwargs.output));
    const quality = String(kwargs.quality);

    // Resolve proxy
    let proxy: string;
    if (kwargs.proxy && String(kwargs.proxy) !== 'auto') {
      proxy = String(kwargs.proxy);
    } else {
      const detected = await detectProxy();
      if (!detected) {
        return [{
          title: 'No proxy found',
          quality,
          status: 'failed',
          size: 'No local proxy detected on common ports (7890, 1080, etc.). Specify one with --proxy.',
          path: '-',
        }];
      }
      proxy = detected;
    }

    // Navigate to video page to get metadata via browser
    let videoTitle = '';
    try {
      await page.goto(url);
      await page.wait(3);
      videoTitle = await page.evaluate(`(() => {
        const el = document.querySelector('h1.ytd-video-primary-info-renderer yt-formatted-string, h1 yt-formatted-string, #title h1');
        return el?.textContent?.trim() || '';
      })()`);
    } catch {
      // Browser navigation failed, will still try yt-dlp
    }

    const result = await ytdlpDownload(url, outputDir, quality, proxy);
    return [{
      title: videoTitle || result.title,
      quality,
      status: result.status,
      size: result.size,
      path: result.path || '-',
    }];
  },
});
