# SmartCommute PH — Setup Guide (read this first!)

Follow this **exactly, in order**. After this you can run the whole app on your machine.
If you get stuck, check the **Troubleshooting** table at the bottom before messaging the group.

---

## What you need to install (one time)

| Tool | Version | Why |
|---|---|---|
| Python | **3.11, 3.12, or 3.13** (⚠ NOT 3.14) | runs the routing engine |
| Node.js | **18 or newer** (LTS is fine) | runs the web gateway |
| Git | any recent | gets the code |
| VS Code | optional | for editing |

> ⚠ **Do NOT use Python 3.14.** Our packages have no prebuilt files for it yet, so
> install will try to compile Rust code and fail with `link.exe not found`.
> This already happened to one of us. Use **3.13**.

---

## Step 1 — Install Python 3.13

1. Go to <https://www.python.org/downloads/> 
2. Scroll to the version list and download **Python 3.13.x — Windows installer (64-bit)**. Do **not** grab 3.14 from the big yellow button if that's what it offers.
3. Run the installer. On the FIRST screen:
   - ✅ **CHECK the box "Add python.exe to PATH"** (bottom of the window — do not skip this)
   - then click **Install Now**
4. Wait, then click **Close**.
5. Verify: open **PowerShell** (press `Win`, type `powershell`, Enter) and run:
   ```powershell
   py -3.13 --version
   ```
   You should see `Python 3.13.x`. If "not recognized", restart PowerShell (or your PC) and try again.

## Step 2 — Install Node.js

1. Go to <https://nodejs.org/>
2. Click the big green **LTS** button to download.
3. Run the installer → keep clicking **Next** with the defaults → **Install** → **Finish**.
4. Verify in PowerShell:
   ```powershell
   node --version
   ```
   Should print `v18.x`, `v20.x`, or `v22.x`.

## Step 3 — Install Git (skip if you have it)

1. Go to <https://git-scm.com/download/win> — the download starts automatically.
2. Run the installer → the defaults are fine → keep clicking **Next** → **Install**.
3. Verify:
   ```powershell
   git --version
   ```

## Step 4 — Get the code

⚠ Clone it somewhere simple like `C:\dev` — **NOT inside OneDrive / Documents** (OneDrive locks files during install and syncs thousands of junk files).

```powershell
mkdir C:\dev
cd C:\dev
git clone https://github.com/andrei13spot/smartcommuteph.git
cd smartcommuteph
git checkout dev
git pull origin dev
```

## Step 5 — Set up the Python engine (one time)

```powershell
cd C:\dev\smartcommuteph\backend
py -3.13 -m venv .venv
.\.venv\Scripts\activate
python --version
pip install -r requirements.txt
```

- After `activate`, your prompt shows **`(.venv)`** at the start — that's correct, it means the project's private Python is active. You do this `activate` step every time you open a new terminal.
- `python --version` must say **3.13.x**. If it says 3.14, you created the venv with the wrong Python — delete it (`Remove-Item -Recurse -Force .venv`) and redo this step.
- `pip install` takes a minute or two. It should end WITHOUT red errors.

**If PowerShell blocks `activate`** with a red "running scripts is disabled" error, run this once, close PowerShell, reopen, and try again:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Step 6 — Set up the Node gateway (one time)

```powershell
cd C:\dev\smartcommuteph\gateway
npm install
```

Should end with something like `added 68 packages`. Warnings are fine; errors are not.

---

## Running the app (every time)

You need **two PowerShell windows open at the same time**.

**Window 1 — the engine:**
```powershell
cd C:\dev\smartcommuteph\backend
.\.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```
Leave it running. It's working when you see `Uvicorn running on http://127.0.0.1:8000`.
(The window looks "stuck" — that's normal, it's a running server. `Ctrl+C` stops it.)

**Window 2 — the gateway:**
```powershell
cd C:\dev\smartcommuteph\gateway
node server.js
```
It's working when you see `smartcommute ph gateway on http://127.0.0.1:8080`.

**Then open your browser:**

| Page | URL |
|---|---|
| The app | <http://127.0.0.1:8080> |
| Researcher console | <http://127.0.0.1:8080/researcher.html> |
| Status dashboard | <http://127.0.0.1:8080/dashboard.html> |
| API docs | <http://127.0.0.1:8000/docs> |

Start window 1 **before** window 2's pages will show data. If maps/routes are empty and the dashboard says "Offline", the engine (window 1) isn't running.

---

## Troubleshooting

| Error you see | What it means | Fix |
|---|---|---|
| `Building wheel for pydantic-core ... link.exe not found` | you're on Python 3.14 | install 3.13 (Step 1), delete `.venv`, redo Step 5 |
| `uvicorn : not recognized` | venv not active, or install failed | run `.\.venv\Scripts\activate` first; if still broken redo Step 5 |
| `python : not recognized` | Python not on PATH | reinstall, CHECK the "Add to PATH" box |
| `running scripts is disabled` | PowerShell policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, reopen terminal |
| `Cannot find module 'express'` | forgot `npm install` | Step 6 |
| `EADDRINUSE` / `Errno 10048` | port already used | close the other terminal running it, or restart your PC |
| pages load but say "engine unreachable" | window 1 not running | start the engine first |
| `pip install` is super slow / file locked | project is inside OneDrive | move the clone to `C:\dev` (Step 4) |

## Git rules (short version)

- never work directly on `main` or `dev`
- before any task: `git checkout dev` → `git pull origin dev` → `git checkout -b <area>/<task>` (`fe/`, `be/`, `ml/`, `qa/`)
- push your branch, open a PR into `dev`, Dave signs off, then it merges

Full details in `DELEGATION.md`.
