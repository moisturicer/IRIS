# deploy/

What belongs to the server, not to a laptop.

| Path | What it is |
|---|---|
| `caddy/Caddyfile` | Caddy's settings: HTTPS in front of IRIS (`docker-compose.prod.yml`) |
| `bootstrap_server.sh` | Gets a fresh Ubuntu 24.04 server ready for IRIS (IR-1014) |
| `tests/bootstrap_checks.sh` | CI's check of `bootstrap_server.sh`, run on a throwaway VM |

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

At launch, with no login at all: paste the whole file into **EC2 → Launch instance → Advanced details → User data**. It runs once, as root, at first boot. Its output goes to `/var/log/cloud-init-output.log`, one `IRIS bootstrap:` line per step:

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
