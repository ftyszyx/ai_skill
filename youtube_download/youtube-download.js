import { cli, Strategy } from "@jackwener/opencli/registry";
import { spawn } from "node:child_process";
import { resolve } from "node:path";
const COMMON_PROXY_PORTS = [7890, 1080, 10809, 7891, 8118, 9090];
async function detectProxy() {
  for (const port of COMMON_PROXY_PORTS) {
    try {
      const resp = await fetch(`http://127.0.0.1:${port}`, { signal: AbortSignal.timeout(2e3) });
      return `http://127.0.0.1:${port}`;
    } catch {
      continue;
    }
  }
  return null;
}
function ytdlpDownload(url, outputDir, quality, proxy, extraArgs = []) {
  return new Promise((resolve2) => {
    const formatMap = {
      best: "bestvideo+bestaudio/best",
      "4k": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
      "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
      "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
      "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
      "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]"
    };
    const format = formatMap[quality] || formatMap.best;
    const args = [
      "--proxy",
      proxy,
      "-f",
      format,
      "--merge-output-format",
      "mkv",
      "-o",
      `${outputDir}/%(title)s.%(ext)s`,
      "--print",
      "%(title)s",
      "--print",
      "%(filesize_approx)s",
      ...extraArgs,
      url
    ];
    const proc = spawn("yt-dlp", args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    proc.stdout?.on("data", (d) => {
      stdout += d.toString();
    });
    proc.stderr?.on("data", (d) => {
      stderr += d.toString();
    });
    proc.on("close", (code) => {
      const lines = stdout.trim().split("\n").filter(Boolean);
      const title = lines[0] || "unknown";
      const sizeBytes = parseInt(lines[1] || "0", 10);
      const sizeStr = sizeBytes > 0 ? `${(sizeBytes / 1024 / 1024).toFixed(1)} MB` : "unknown";
      if (code === 0) {
        resolve2({ title, status: "downloaded", size: sizeStr, path: resolve2(outputDir, `${title}.mkv`) });
      } else {
        resolve2({ title: "download failed", status: "failed", size: stderr.slice(-200) || "unknown error", path: "" });
      }
    });
  });
}
cli({
  site: "aiskill",
  name: "youtube-download",
  description: "Download YouTube videos via yt-dlp with proxy auto-detection",
  strategy: Strategy.COOKIE,
  browser: true,
  domain: "www.youtube.com",
  args: [
    { name: "url", required: true, positional: true, help: "YouTube video URL or video ID" },
    { name: "output", default: ".", help: "Output directory" },
    { name: "quality", default: "best", help: "Video quality: best, 4k, 1440p, 1080p, 720p, 480p" },
    { name: "proxy", default: "auto", help: "Proxy URL (default: auto-detect from common ports)" }
  ],
  columns: ["title", "quality", "status", "size", "path"],
  func: async (page, kwargs) => {
    const url = String(kwargs.url).includes("youtube.com") || String(kwargs.url).includes("youtu.be") ? String(kwargs.url) : `https://www.youtube.com/watch?v=${kwargs.url}`;
    const outputDir = resolve(String(kwargs.output));
    const quality = String(kwargs.quality);
    let proxy;
    if (kwargs.proxy && String(kwargs.proxy) !== "auto") {
      proxy = String(kwargs.proxy);
    } else {
      const detected = await detectProxy();
      if (!detected) {
        return [{
          title: "No proxy found",
          quality,
          status: "failed",
          size: "No local proxy detected on common ports (7890, 1080, etc.). Specify one with --proxy.",
          path: "-"
        }];
      }
      proxy = detected;
    }
    let videoTitle = "";
    try {
      await page.goto(url);
      await page.wait(3);
      videoTitle = await page.evaluate(`(() => {
        const el = document.querySelector('h1.ytd-video-primary-info-renderer yt-formatted-string, h1 yt-formatted-string, #title h1');
        return el?.textContent?.trim() || '';
      })()`);
    } catch {
    }
    const result = await ytdlpDownload(url, outputDir, quality, proxy);
    return [{
      title: videoTitle || result.title,
      quality,
      status: result.status,
      size: result.size,
      path: result.path || "-"
    }];
  }
});
