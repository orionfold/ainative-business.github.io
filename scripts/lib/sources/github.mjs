// GitHub repo metadata via gh CLI (already authenticated on the Spark) or
// unauthenticated public API as fallback. We only read public data.

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const exec = promisify(execFile);

function parseRepoUrl(url) {
  if (!url) return null;
  const m = url.match(/github\.com\/([^/]+)\/([^/?#]+)/);
  if (!m) return null;
  return { owner: m[1], repo: m[2].replace(/\.git$/, '') };
}

export async function fetchGitHubRepoMeta(url) {
  const parsed = parseRepoUrl(url);
  if (!parsed) return null;
  const { owner, repo } = parsed;

  // Try gh CLI first (handles rate limits via the user's token).
  try {
    const { stdout } = await exec('gh', [
      'api',
      `/repos/${owner}/${repo}`,
      '-q',
      '{stargazers_count, forks_count, pushed_at, updated_at, language, default_branch, archived, license: .license.spdx_id}',
    ], { timeout: 15000 });
    const meta = JSON.parse(stdout);
    return {
      url,
      stars: meta.stargazers_count ?? 0,
      forks: meta.forks_count ?? 0,
      last_commit: meta.pushed_at || meta.updated_at || null,
      language: meta.language || null,
      archived: !!meta.archived,
      license: meta.license || null,
      framework_hint: meta.language || null,
    };
  } catch {
    // Fall through to public API
  }

  try {
    const res = await fetch(`https://api.github.com/repos/${owner}/${repo}`, {
      headers: { Accept: 'application/vnd.github+json', 'User-Agent': 'frontier-scout/0.1' },
    });
    if (!res.ok) return null;
    const meta = await res.json();
    return {
      url,
      stars: meta.stargazers_count ?? 0,
      forks: meta.forks_count ?? 0,
      last_commit: meta.pushed_at || meta.updated_at || null,
      language: meta.language || null,
      archived: !!meta.archived,
      license: meta.license?.spdx_id || null,
      framework_hint: meta.language || null,
    };
  } catch {
    return null;
  }
}
