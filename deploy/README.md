# deploy/

What belongs to the server, not to a laptop.

| Path | What it is |
|---|---|
| `caddy/Caddyfile` | Caddy's settings: HTTPS in front of IRIS (`docker-compose.prod.yml`) |
| `bootstrap_server.sh` | Gets a fresh Ubuntu 24.04 server ready for IRIS (IR-1014) |
| `tests/bootstrap_checks.sh` | CI's check of `bootstrap_server.sh`, run on a throwaway VM |
| `aws/iris-demo.yaml` | CloudFormation template: the whole AWS server from one file, running `bootstrap_server.sh` at first boot (IR-1013) |
| `aws/iris-guards.yaml` | CloudFormation template: budget alert, auto-recover and a daily stop and start for one server (IR-1015) |
| `../scripts/deploy.sh` | Updates a running server to the latest `main` with one command, and checks it came back (IR-1018) |
| `tests/deploy_checks.sh` | CI's check of `deploy.sh`, against a fake `docker` |
| `tests/check_compose_prod.py` | CI's check of `docker-compose.prod.yml`: every long-running service comes back after a start, and every service's logs are rotated (10 MB × 3) |

## bootstrap_server.sh

**What it does**, each step reported on its own line as done or already done:

1. Installs Docker and Compose from Docker's apt repository, after checking Docker's signing key.
2. Adds the login user to the `docker` group, so `docker` works without `sudo` after their next login.
3. Creates a 4 GB swap file and lists it in `/etc/fstab`, so it survives reboots. The build needs it on an 8 GB server.
4. Clones `main` into the user's home, for example `/home/ubuntu/IRIS`.
5. If `/etc/iris/duckdns` exists, points the DuckDNS name at this server now and on every boot.

**What it never does:** start IRIS, or write a `.env` file. Secrets and vendor keys stay a separate step, done by a person.

**Safe to run again.** A finished step is left alone, and a step a stopped run left halfway (a swap file never made swap, Docker installed but not running) is finished. It never updates an existing clone: use [`scripts/deploy.sh`](#updating-the-server-scriptsdeploysh) for that.

### Run it

On a server you can already log in to:

```bash
curl -fsSLo bootstrap_server.sh https://raw.githubusercontent.com/moisturicer/IRIS/main/deploy/bootstrap_server.sh
less bootstrap_server.sh          # read it before running it as root
sudo bash bootstrap_server.sh
```

On AWS, the template below does this for you. Launching by hand instead, with no login at all: paste the whole file into **EC2 → Launch instance → Advanced details → User data**. It runs once, as root, at first boot. Its output goes to `/var/log/cloud-init-output.log`, one `IRIS bootstrap:` line per step:

```bash
grep "IRIS bootstrap" /var/log/cloud-init-output.log
```

**Settings,** all optional and none secret, set in front of the command, for example `sudo IRIS_USER=admin bash bootstrap_server.sh`:

| Setting | Default |
|---|---|
| `IRIS_USER` | whoever ran `sudo`, else `ubuntu` |
| `IRIS_DIR` | `<user's home>/IRIS` |
| `IRIS_SWAP_SIZE` | `4G` (a number then `M` or `G`) |

It always clones `main` of `https://github.com/moisturicer/IRIS.git`, which works only while that repository is public.

### DuckDNS (optional)

**Why:** without an Elastic IP, AWS gives the server a new address after every stop and start. This keeps the DuckDNS name following it. With an Elastic IP the address never changes, and this is only a convenience.

The token is a password, so it lives in a file only root can read, never in the repo, the command line or EC2 user data (the console shows user data to anyone with access to the instance). Create it once, on the server:

```bash
sudo install -d -m 700 /etc/iris
sudo install -m 600 /dev/null /etc/iris/duckdns
sudo nano /etc/iris/duckdns
```

```text
DUCKDNS_DOMAIN=iris-citu
DUCKDNS_TOKEN=<the token from duckdns.org>
```

`DUCKDNS_DOMAIN` is the subdomain alone, without `.duckdns.org`. Then run the script again: `sudo bash ~/IRIS/deploy/bootstrap_server.sh` (the clone's copy, on any server this script set up). It refuses the file unless it is owned by root with mode 600, and fails at once on a token DuckDNS rejects, rather than after the next reboot. Each later run sends the address again, as every boot does.

**Not at launch.** User data runs before anyone can create this file, and putting the token in user data would expose it. So a server started from user data has no DuckDNS until someone logs in once, creates the file and runs the script again. With an Elastic IP, skip DuckDNS's updater altogether: set the address once on duckdns.org.

**Check it after a reboot:**

```bash
systemctl status iris-duckdns.service    # last run: "now points at this server"
swapon --show                            # /swapfile, 4G
```

### Next

The script ends where the `.env` setup begins. Log out and back in (for the `docker` group), then:

```bash
cd ~/IRIS
python3 scripts/setup_env.py
```

and fill in `backend/.env` and `ai/.env` (domain, vendor keys, Gmail). Then start IRIS the first time with `bash scripts/deploy.sh`, which builds it and checks it came up (below).

## Updating the server: scripts/deploy.sh

**Why:** an update by hand is `git pull`, a rebuild, then checking each service yourself. A step skipped or a problem missed leaves the server half updated: a database update that failed, or a site that loads but can't sign anyone in (IR-200). This does all of it, the same way every time.

**Not yet run on a real server.** CI checks every step and failure against a fake Docker. The first real update on `iris-demo` is still to be recorded in `docs/testing/traceability/IR-1018.md`. Until then, watch that first run, and keep the manual steps in **After a scheduled start** below as the fallback.

```bash
sudo -iu ubuntu        # in a Session Manager shell; skip it over SSH as ubuntu
bash ~/IRIS/scripts/deploy.sh
```

It reports five steps, and the first that fails stops the run and names itself:

| Step | What it does | Stops when |
|---|---|---|
| 1. pull | Fast-forwards the clone to GitHub's `main` | the clone isn't on `main`, has uncommitted changes, or has commits GitHub doesn't. Nothing is changed |
| 2. check | Checks `.env`, `backend/.env` and `ai/.env` exist, the compose file is valid, and 5 GB is free | any is missing. Nothing is rebuilt |
| 3. rebuild | `docker compose -f docker-compose.prod.yml up -d --build` | the build fails, or `migrate` (the database update) fails: its log is shown |
| 4. health | Waits until every service is running, and healthy where it has a check, on three checks in a row, so a crash-looping one doesn't pass. After a rebuild it restarts `frontend` (IR-200). Then it fetches the home page and `/api/v1/colleges/` over HTTPS | a service isn't ready, or the site doesn't answer, within 10 minutes for the whole step. The logs of what failed are shown |
| 5. report | Prints `done, running <commit> (<title>)` | |

**Nothing new?** It says "already up to date", skips the rebuild and only runs the health check. That makes it the check to run after a scheduled start too: when the page answers but the API doesn't, it restarts `frontend` once by itself (IR-200). It remembers the last commit it deployed, in `.git/iris-deployed`, so a run after a failed one rebuilds, even with nothing new to pull.

**When it fails** after pulling new code, it prints the command to go back to the version that ran before:

```bash
git checkout --detach <commit> && docker compose -f docker-compose.prod.yml up -d --build
```

Going back never undoes a database migration. Run `git checkout main` before the next deploy, since it refuses any other branch. It never goes back by itself: a person decides.

**A change to `deploy.sh` itself** takes effect from the next run. The run that pulls it carries on with the copy it started with.

**Settings,** in front of the command, for example `IRIS_DEPLOY_TIMEOUT=900 bash ~/IRIS/scripts/deploy.sh`:

| Setting | Default |
|---|---|
| `IRIS_DEPLOY_TIMEOUT` | `600`: seconds step 4 may take in all |
| `IRIS_DEPLOY_POLL` | `5`: seconds between checks |
| `IRIS_DEPLOY_MIN_FREE_GB` | `5`: free disk a rebuild needs |

It doesn't back up the database first; do that yourself before an update that migrates.

## aws/iris-demo.yaml

**Why:** the first server (2026-11-10) was clicked together in the EC2 console: instance, firewall, fixed IP. This template makes the same server in any AWS account from one file, and deleting it removes everything it made.

**What it creates:**

| Resource | What for |
|---|---|
| EC2 instance | Ubuntu 24.04 (Canonical's current image for the region), encrypted gp3 disk; runs `bootstrap_server.sh` at first boot |
| Security group | ports 80 and 443 open to anywhere (Caddy needs 80 for its certificate); 22 only if you give an SSH address |
| Elastic IP | the fixed address DuckDNS points at |
| IAM role | `AmazonSSMManagedInstanceCore` only, so Session Manager can open a shell without SSH or a key |

It holds no secret and starts nothing: the `.env` files are still written by a person, as in **Next** above.

**Before you start:**
- **A default VPC.** The region needs its default VPC, which every AWS account has unless someone deleted it (**VPC → Your VPCs**, "Default VPC: Yes"). The template names no network of its own, so without one the stack fails at the security group and rolls back.
- **A public repository.** The server downloads the script from GitHub without signing in, so the repository must be public.

### Create the stack

1. AWS console, in the region you want (for example Asia Pacific (Singapore)): **CloudFormation → Create stack → With new resources**.
2. **Upload a template file:** `deploy/aws/iris-demo.yaml` from your clone.
3. **Stack name:** for example `iris-demo`. Parameters:

   | Parameter | Default | Notes |
   |---|---|---|
   | `InstanceType` | `m7i-flex.large` | `t3.large` where that isn't offered. The smaller ones are only for trying the template: the build needs about 8 GB |
   | `DiskSizeGiB` | `64` | |
   | `SshSourceIp` | empty | your public IPv4 to allow SSH from it alone; empty keeps port 22 closed |
   | `KeyPairName` | empty | an existing key pair, for SSH. Only useful with `SshSourceIp`; not needed for Session Manager |
   | `IrisRef` | `main` | which version of `bootstrap_server.sh` is downloaded and run at first boot. Only the script follows it: the code it clones is always `main`. Leave it as `main` unless you are testing a change to the script itself |

4. Tick **"I acknowledge that AWS CloudFormation might create IAM resources"** (the Session Manager role), then **Submit**.
5. About three minutes later the stack says `CREATE_COMPLETE`. **Outputs** shows `PublicIp` and `InstanceId`. Point the DuckDNS name at `PublicIp` once, on duckdns.org.

`CREATE_COMPLETE` means AWS made the resources, not that the bootstrap worked: it keeps running for a few minutes after that, and a failure there doesn't show in CloudFormation. Check it as below.

### Connect without SSH

**EC2 → Instances →** the instance → **Connect → Session Manager → Connect.** It opens a browser shell as `ssm-user`. Switch to the user that owns the clone:

```bash
sudo -iu ubuntu
grep "IRIS bootstrap" /var/log/cloud-init-output.log    # ends with "finished"
```

Then carry on from **Next** above. A new instance can take a minute or two after boot to appear in Session Manager.

### Session Manager on a server built by hand

A server this template made already has the role Session Manager needs. One launched by hand, like the first `iris-demo`, doesn't, until it's given one. This is a one-time step: free, no restart, no port opened.

1. **IAM → Roles → Create role.** Trusted entity **AWS service**, use case **EC2**, **Next**.
2. Tick **`AmazonSSMManagedInstanceCore`** and nothing else, **Next**. Name it, for example `iris-demo-ssm`, and **Create role**.
3. **EC2 → Instances →** the server **→ Actions → Security → Modify IAM role**, choose the role, **Update IAM role**.
4. About five minutes later, **Connect → Session Manager → Connect** works.

**If it still won't connect** ("unable to acquire credentials" in the agent's log): the agent started before the role existed and hasn't looked again. Over SSH, run `sudo snap restart amazon-ssm-agent`, then try again a minute later. That is what the first `iris-demo` needed.

If the server already has a role, add `AmazonSSMManagedInstanceCore` to that role instead (**IAM → Roles →** it **→ Add permissions**): a server holds one role at a time.

### Read the logs

In a Session Manager shell (or SSH):

```bash
sudo -iu ubuntu
cd ~/IRIS
docker compose -f docker-compose.prod.yml ps                       # which services are up
docker compose -f docker-compose.prod.yml logs --tail 100 backend  # one service's latest lines
docker compose -f docker-compose.prod.yml logs -f ai-gateway       # follow live; Ctrl+C stops
```

Other services: `celery-default`, `celery-extraction`, `celery-embedding`, `celery-beat`, `ai-runs-worker`, `migrate`, `frontend`, `caddy`. `--since 30m` limits it to the last half hour.

**Which log shows what:** `frontend` (nginx) logs every request, sign-ins included. `backend` logs only warnings and errors, so a quiet backend log is normal.

These logs live on the server only: nothing can be read while it is stopped, and they go with the disk. Sending them to CloudWatch, where they'd be searchable and survive a broken server, is deferred; the plan is kept on IR-1016's card.

### Delete it

**CloudFormation →** the stack **→ Delete.** That deletes the instance, its disk, the Elastic IP, the security group and the role, so nothing keeps billing. Everything on the server's disk goes with it, the database included. Back up anything you need first.

**Cost while it runs:** the instance, its disk and the public IPv4 address. AWS charges for every public IPv4 address, attached or not: US$0.005 an hour, about US$3.65 a month.

## aws/iris-guards.yaml

**Why:** the server costs about US$3 a day while it runs. Nothing warns before a bill grows, nothing shows when the host hardware fails, and the server runs all night when nobody uses it. This template adds all three to any instance, including one built by hand like `iris-demo`.

| Part | Parameters | Off when |
|---|---|---|
| Budget for the **whole account**: an email at 80% of the month's forecast and at 100% of actual spend. It warns; it stops nothing | `BudgetEmail`, `MonthlyBudgetUsd` (default 100) | `BudgetEmail` is empty |
| Auto-recover: when AWS's own hardware check fails two minutes running, the instance moves to healthy hardware with the same ID, disk and IP. t3 and m7i-flex already do this by default; the alarm makes it explicit and shows it in CloudWatch | `AutoRecover` (default `true`) | `false` |
| Daily stop and start, by EventBridge Scheduler, with a role that can stop and start this one instance only | `StopTime`, `StartTime` (for example `23:00`, `07:00`), `ScheduleTimeZone` (default `Asia/Manila`) | both times are empty (the default). One without the other is refused |

Vendor spending (OpenRouter, Voyage, LlamaParse) is not in this budget: each vendor account has its own cap, and `AI_ADMISSION_*` limits it.

**Costs:** nothing for the guards themselves (budgets, up to ten alarms and this many schedules are free). While stopped, the disk and the Elastic IP still bill, about US$0.30 a day.

### Create it

1. Find the server's instance ID: **EC2 → Instances**, or the `InstanceId` output of the `iris-demo` stack.
2. **CloudFormation → Create stack → With new resources**, in the server's region. Upload `deploy/aws/iris-guards.yaml`, and name it, for example `iris-guards`.
3. Fill in the parameters, tick the IAM acknowledgement (the scheduler's role), and **Submit**.

To change the times later: the stack → **Update → Use existing template**, then edit the parameters. **Delete** removes the budget, the alarm and the schedules, and leaves the server alone.

### After a scheduled start

Docker starts at boot, and every IRIS service comes back by itself because each one says `restart: unless-stopped` (CI checks this). Only `migrate` stays exited, which is right: it already ran. The Elastic IP keeps the address, so DuckDNS needs no change.

At boot Docker doesn't wait for the database the way `docker compose up` does, so the backend and the workers may restart a few times until it is ready. The site is back a few minutes after the start time.

**Check that you can sign in, not only that the page loads.** The frontend looks up the backend's internal address once, when it starts (IR-200). If the backend came up later at a new address, the page loads but sign-in fails. The fix is one command:

```bash
bash ~/IRIS/scripts/deploy.sh    # "already up to date", then the health check; restarts frontend if the API doesn't answer
```

Or by hand, which works with or without the script:

```bash
cd ~/IRIS
docker compose -f docker-compose.prod.yml ps                 # all "Up", migrate "Exited (0)"
docker compose -f docker-compose.prod.yml restart frontend   # if sign-in fails
```

**Encrypted disks:** the scheduled start works with the default EBS encryption key (`aws/ebs`), which both templates use. A disk encrypted with a key of your own would need that key to allow the scheduler's role, or the start fails and the instance goes back to stopped.
