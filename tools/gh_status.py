#!/usr/bin/env python3
"""Show recent workflow runs and optionally print files from the repository.

  python tools/gh_status.py [--branch NAME] [--runs N] [path-in-repo ...]

The repository is public, so this works without any credential.  If Git Credential Manager has a
stored github.com credential, it is fetched with `git credential fill` (memory only, never printed
or saved) to get the higher API rate limit.  No token file is ever read.
"""
import argparse, base64, json, os, subprocess, urllib.request

REPO = "https://api.github.com/repos/daboodah-oss/iu-qb-report"


def stored_credential():
    """Password from the configured git credential helper, or None.  Never prompts."""
    try:
        if not subprocess.run(["git", "config", "--get", "credential.helper"], capture_output=True, text=True).stdout.strip():
            return None
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
        out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                             capture_output=True, text=True, env=env, timeout=20).stdout
        return next((l[9:] for l in out.splitlines() if l.startswith("password=")), None)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch"); ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("paths", nargs="*")
    a = ap.parse_args()
    cred = stored_credential()
    hdr = {"Accept": "application/vnd.github+json", "User-Agent": "iu-qb-report-status"}
    if cred: hdr["Authorization"] = "Bearer " + cred
    del cred

    def api(p):
        return json.load(urllib.request.urlopen(urllib.request.Request(REPO + p, headers=hdr), timeout=30))

    q = f"/actions/runs?per_page={a.runs}" + (f"&branch={a.branch}" if a.branch else "")
    for r in api(q)["workflow_runs"]:
        print(f"run {r['id']}  {r['head_branch']:<22} {r['event']:<17} {r['status']:<10} {r['conclusion'] or '-':<9} {r['created_at']}  {r['html_url']}")
    ref = f"?ref={a.branch}" if a.branch else ""
    for p in a.paths:
        try:
            d = api(f"/contents/{p}{ref}")
            if isinstance(d, list): print(p, "->", [x["name"] for x in d])
            else: print(f"==== {p}\n" + base64.b64decode(d["content"]).decode(errors="replace"))
        except Exception as e:
            print(p, "ERR", e)


if __name__ == "__main__":
    main()
