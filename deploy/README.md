# deploy/

What belongs to the server, not to a laptop.

| Path | What it is |
|---|---|
| `caddy/Caddyfile` | Caddy's settings: HTTPS in front of IRIS (`docker-compose.prod.yml`) |
| `bootstrap_server.sh` | Gets a fresh Ubuntu 24.04 server ready for IRIS (IR-1014) |
| `tests/bootstrap_checks.sh` | CI's check of `bootstrap_server.sh`, run on a throwaway VM |
| `aws/iris-demo.yaml` | CloudFormation template: the whole AWS server from one file, running `bootstrap_server.sh` at first boot (IR-1013) |

## bootstrap_server.sh

**What it does**, each step reported on its own line as done or already done:

1. Installs Docker and Compose from Docker's apt repository, after checking Docker's signing key.
2. Adds the login user to the `docker` group, so `docker` works without `sudo` after their next login.
3. Creates a 4 GB swap file and lists it in `/etc/fstab`, so it survives reboots. The build needs it on an 8 GB server.
4. Clones `main` into the user's home, for example `/home/ubuntu/IRIS`.
5. If `/etc/iris/duckdns` exists, points the DuckDNS name at this server now and on every boot.

**What it never does:** start IRIS, or write a `.env` file. Secrets and vendor keys stay a separate step, done by a person.

**Safe to run again.** A finished step is left alone, and a step a stopped run left halfway (a swap file never made swap, Docker installed but not running) is finished. It never updates an existing clone: use `git pull` for that.

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

`DUCKDNS_DOMAIN` is the subdomain alone, without `.duckdns.org`. Then run the script again. It refuses the file unless it is owned by root with mode 600, and fails at once on a token DuckDNS rejects, rather than after the next reboot. Each later run sends the address again, as every boot does.

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

and fill in `backend/.env` and `ai/.env` (domain, vendor keys, Gmail) before `docker compose -f docker-compose.prod.yml up -d --build`.

## aws/iris-demo.yaml

**Why:** the first server (2026-11-10) was clicked together in the EC2 console: instance, firewall, fixed IP. This template makes the same server in any AWS account from one file, and deleting it removes everything it made.

**What it creates:**

| Resource | What for |
|---|---|
| EC2 instance | Ubuntu 24.04 (the newest image AWS lists for the region), encrypted gp3 disk; runs `bootstrap_server.sh` at first boot |
| Security group | ports 80 and 443 open to anywhere (Caddy needs 80 for its certificate); 22 only if you give an SSH address |
| Elastic IP | the fixed address DuckDNS points at |
| IAM role | `AmazonSSMManagedInstanceCore` only, so Session Manager can open a shell without SSH or a key |

It holds no secret and starts nothing: the `.env` files are still written by a person, as in **Next** above.

### Create the stack

1. AWS console, in the region you want (for example Asia Pacific (Singapore)): **CloudFormation → Create stack → With new resources**.
2. **Upload a template file:** `deploy/aws/iris-demo.yaml` from your clone.
3. **Stack name:** for example `iris-demo`. Parameters:

   | Parameter | Default | Notes |
   |---|---|---|
   | `InstanceType` | `m7i-flex.large` | `t3.large` where that isn't offered. The smaller ones are only for trying the template: the build needs about 8 GB |
   | `DiskSizeGiB` | `64` | |
   | `SshSourceIp` | empty | your public IPv4 to allow SSH from it alone; empty keeps port 22 closed |
   | `KeyPairName` | empty | an existing key pair, for SSH; not needed for Session Manager |
   | `IrisRef` | `main` | which version of `bootstrap_server.sh` runs; it downloads it from GitHub at first boot |

4. Tick **"I acknowledge that AWS CloudFormation might create IAM resources"** (the Session Manager role), then **Submit**.
5. About three minutes later the stack says `CREATE_COMPLETE`. **Outputs** shows `PublicIp` and `InstanceId`. Point the DuckDNS name at `PublicIp` once, on duckdns.org.

The bootstrap keeps running for a few minutes after that. Check it as below.

### Connect without SSH

**EC2 → Instances →** the instance → **Connect → Session Manager → Connect.** It opens a browser shell as `ssm-user`. Switch to the user that owns the clone:

```bash
sudo -iu ubuntu
grep "IRIS bootstrap" /var/log/cloud-init-output.log    # ends with "finished"
```

Then carry on from **Next** above. A new instance can take a minute or two after boot to appear in Session Manager.

### Delete it

**CloudFormation →** the stack **→ Delete.** That deletes the instance, its disk, the Elastic IP, the security group and the role, so nothing keeps billing. Everything on the server's disk goes with it, the database included. Back up anything you need first.

**Cost while it runs:** the instance, its disk and the public IPv4 address. AWS charges for every public IPv4 address, attached or not, about US$3.60 a month.
