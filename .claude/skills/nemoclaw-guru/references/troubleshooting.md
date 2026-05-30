# NemoClaw on DGX Spark — Troubleshooting

Source: https://build.nvidia.com/spark/nemoclaw/troubleshooting
Captured: 2026-04-21 (one-time traversal)

Symptom → cause → fix, extracted verbatim from the official troubleshooting page, followed by DGX-Spark-specific notes.

---

## Install-time issues

### `nemoclaw: command not found` after install
- **Cause:** Shell PATH not updated.
- **Fix:** `source ~/.bashrc` (or `source ~/.zshrc` for zsh), or open a new terminal window.

### Installer fails with Node.js version error
- **Cause:** Node.js version below 20.
- **Fix:** Install Node.js 20+:
  ```bash
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
  ```
  Then re-run the installer.

### `npm install` fails with `EACCES` permission error
- **Cause:** npm global directory not writable.
- **Fix:**
  ```bash
  mkdir -p ~/.npm-global
  npm config set prefix ~/.npm-global
  export PATH=~/.npm-global/bin:$PATH
  ```
  Then re-run the installer. Add the `export` line to `~/.bashrc` to make it permanent.

### Docker permission denied
- **Cause:** User not in docker group.
- **Fix:**
  ```bash
  sudo usermod -aG docker $USER
  ```
  Then log out and back in (or run `newgrp docker` in the current session).

---

## Gateway / onboarding issues

### Gateway fails with cgroup / "Failed to start ContainerManager" errors
- **Cause:** Docker not configured for host cgroup namespace on DGX Spark.
- **Fix:** Apply the cgroup fix and restart Docker:
  ```bash
  sudo python3 -c "import json, os; path='/etc/docker/daemon.json'; d=json.load(open(path)) if os.path.exists(path) else {}; d['default-cgroupns-mode']='host'; json.dump(d, open(path,'w'), indent=2)"
  sudo systemctl restart docker
  ```
  Alternative: `sudo nemoclaw setup-spark` applies this fix automatically.

### Gateway fails with `port 8080 is held by container...`
- **Cause:** Another OpenShell gateway or container is using port 8080.
- **Fix:** Stop the conflicting container:
  ```bash
  openshell gateway destroy -g <old-gateway-name>
  # or
  docker stop <container-name> && docker rm <container-name>
  ```
  Then retry `nemoclaw onboard`.

### Sandbox creation fails
- **Cause:** Stale gateway state or DNS not propagated.
- **Fix:**
  ```bash
  openshell gateway destroy && openshell gateway start
  ```
  Then re-run the installer or `nemoclaw onboard`.

### CoreDNS crash loop
- **Cause:** Known issue on some DGX Spark configurations.
- **Fix:** From the NemoClaw repo directory:
  ```bash
  sudo ./scripts/fix-coredns.sh
  ```

### "No GPU detected" during onboard
- **Cause:** DGX Spark GB10 reports unified memory differently.
- **Fix:** Expected on DGX Spark. The wizard still works and uses Ollama for inference. Proceed.

---

## Runtime / inference issues

### Inference timeout or hangs
- **Cause:** Ollama not running or not reachable.
- **Fix:** Check Ollama: `curl http://localhost:11434`. If not running:
  ```bash
  ollama serve &
  ```
  If running but unreachable from sandbox, ensure Ollama listens on `0.0.0.0` (see *Step 2* in `instructions.md`). On DGX Spark the canonical fix is the systemd override that sets `OLLAMA_HOST=0.0.0.0`, not `ollama serve &`.

### Agent gives no response or is very slow
- **Cause:** Normal for 120B model running locally.
- **Fix:** Nemotron 3 Super 120B can take 30–90 seconds per response. Verify the inference route is healthy:
  ```bash
  nemoclaw my-assistant status
  ```

### Port 18789 already in use
- **Cause:** Another process is bound to the port.
- **Fix:**
  ```bash
  lsof -i :18789
  kill <PID>
  # If needed
  kill -9 <PID>
  ```

### Web UI port forward dies or dashboard unreachable
- **Cause:** Port forward not active.
- **Fix:**
  ```bash
  openshell forward stop 18789 my-assistant
  openshell forward start 18789 my-assistant --background
  ```

### Web UI shows `origin not allowed`
- **Cause:** Accessing via `localhost` instead of `127.0.0.1`.
- **Fix:** Use `http://127.0.0.1:18789/#token=...` in the browser. The gateway origin check requires `127.0.0.1` exactly.

---

## Telegram bridge issues

### Telegram bridge does not start
- **Cause:** Missing environment variables.
- **Fix:** Ensure `TELEGRAM_BOT_TOKEN` and `SANDBOX_NAME` are set on the host. `SANDBOX_NAME` must match the sandbox name from onboarding.

### Telegram bridge needs restart but `nemoclaw stop` does not work
- **Cause:** Known bug in `nemoclaw stop`.
- **Fix:** Find the PID from the `nemoclaw start` output, force-kill with `kill -9 <PID>`, then `nemoclaw start` again.

### Telegram bot receives messages but does not reply
- **Cause:** Telegram policy not added to sandbox.
- **Fix:**
  ```bash
  nemoclaw my-assistant policy-add
  # choose telegram, hit Y
  nemoclaw start
  ```

---

## DGX Spark Unified Memory (UMA) note

DGX Spark uses a Unified Memory Architecture (UMA), which enables dynamic memory sharing between GPU and CPU. Some applications have not yet fully adapted to UMA, so you may encounter memory issues even when within the memory capacity of DGX Spark. If that happens, manually flush the buffer cache:

```bash
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```

For the latest known issues, consult the DGX Spark User Guide.

---

## Diagnosis order of operations

When the user reports an unexplained failure, work from cheapest → deepest:

1. `nemoclaw --version` on PATH? If not → PATH/install issue (`source ~/.bashrc`).
2. `docker ps` works without sudo? If not → docker group issue.
3. `docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi` works? If not → NVIDIA runtime / daemon.json issue.
4. `curl http://0.0.0.0:11434` returns `Ollama is running`? If not → Ollama systemd issue.
5. `ollama list` shows `nemotron-3-super:120b`? If not → model not pulled.
6. `nemoclaw list` shows the expected sandbox? If not → onboard never completed / gateway failure.
7. `nemoclaw <name> status` shows healthy sandbox + inference? If not → sandbox/inference drift, try rebuild.
8. Sandbox: `curl -sf https://inference.local/v1/models` returns JSON? If not → inference route broken.
9. Still failing? Collect diagnostics with `nemoclaw debug --quick --output /tmp/nemoclaw-debug.tar.gz` (if available) and inspect `~/.nemoclaw/` state.

## Related resources (not fetched in this traversal)

- NemoClaw Documentation (docs.nvidia.com/nemoclaw/latest/reference/troubleshooting.html)
- DGX Spark User Guide — for UMA and hardware-specific known issues
- DGX Spark Forum
