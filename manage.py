import sys
import subprocess
import urllib.request
import os

GIT_CMD = r"C:\Program Files\Git\cmd\git.exe"
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
HEALTH_URL = "https://smart-assistant-bot-1jv0.onrender.com/"


def run_git(args: list) -> subprocess.CompletedProcess:
    cmd = [GIT_CMD if os.path.exists(GIT_CMD) else "git", "-C", REPO_DIR] + args
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


def cmd_test():
    """Run unit tests autonomously."""
    print(">>> Running test suite...")
    res = subprocess.run([sys.executable, "-m", "unittest", "test_typing_indicator.py", "-v"],
                         cwd=REPO_DIR)
    if res.returncode == 0:
        print(">>> All tests passed successfully.")
    else:
        print(">>> Tests failed.")
    return res.returncode


def cmd_deploy(message: str):
    """Stage, commit, and push all changes directly to GitHub."""
    print(f">>> Staging all changes...")
    run_git(["add", "."])

    print(f">>> Committing with message: {message}")
    commit_res = run_git(["commit", "-m", message])
    print(commit_res.stdout.strip())
    if commit_res.stderr:
        print(commit_res.stderr.strip())

    print(">>> Pushing to GitHub main...")
    push_res = run_git(["push", "origin", "main"])
    print(push_res.stdout.strip())
    if push_res.stderr:
        print(push_res.stderr.strip())

    if push_res.returncode == 0:
        print(">>> Successfully deployed to GitHub! Render will auto-update in ~1 minute.")
    else:
        print(">>> Push failed. Check output above.")
    return push_res.returncode


def cmd_health():
    """Verify live cloud server status."""
    print(f">>> Checking Render cloud health at: {HEALTH_URL}")
    try:
        req = urllib.request.Request(HEALTH_URL, method="HEAD", headers={"User-Agent": "BotManager/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f">>> Cloud Status: {resp.status} OK (Server is ALIVE)")
            return 0
    except Exception as e:
        print(f">>> Cloud Status: Check failed - {e}")
        return 1


def cmd_status():
    """Display git status and cloud status."""
    print("=== GIT STATUS ===")
    st = run_git(["status", "-s"])
    print(st.stdout.strip() if st.stdout.strip() else "(Clean working tree)")
    print("\n=== CLOUD STATUS ===")
    cmd_health()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py manage.py [test | deploy <message> | health | status]")
        sys.exit(1)

    action = sys.argv[1].lower()
    if action == "test":
        sys.exit(cmd_test())
    elif action == "deploy":
        msg = sys.argv[2] if len(sys.argv) > 2 else "chore: autonomous automated update"
        sys.exit(cmd_deploy(msg))
    elif action == "health":
        sys.exit(cmd_health())
    elif action == "status":
        cmd_status()
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
