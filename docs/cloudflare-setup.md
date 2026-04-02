# Cloudflare DNS, SSL & DDoS Setup for OpenMTSN

This guide configures a custom domain with automated SSL, edge caching, and DDoS protection using Cloudflare's free tier.

---

## Prerequisites

- A registered domain (e.g., `openmtsn.org`)
- A Cloudflare account (free)
- Your server's public IP (from `terraform output public_ip`)

---

## Step 1: Add Domain to Cloudflare

1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Click **Add a Site** → enter your domain → select **Free Plan**
3. Cloudflare will scan existing DNS records

## Step 2: Update Nameservers

At your domain registrar, replace the existing nameservers with the two Cloudflare nameservers shown (e.g., `aria.ns.cloudflare.com`, `bruce.ns.cloudflare.com`).

> Propagation takes up to 24 hours, but usually completes within 1 hour.

## Step 3: Configure DNS Records

In Cloudflare DNS settings, add:

| Type  | Name               | Content              | Proxy  | TTL   |
|-------|--------------------|----------------------|--------|-------|
| A     | `@`                | `<SERVER_PUBLIC_IP>` | ✅ Yes | Auto  |
| A     | `api`              | `<SERVER_PUBLIC_IP>` | ✅ Yes | Auto  |
| CNAME | `www`              | `openmtsn.org`       | ✅ Yes | Auto  |

- **`openmtsn.org`** → Dashboard (port 80)
- **`api.openmtsn.org`** → FastAPI Control Plane (port 8000)

## Step 4: Enable SSL/TLS

Navigate to **SSL/TLS** → **Overview**:

1. Set encryption mode to **Full (Strict)**
2. Under **Edge Certificates** → enable:
   - ✅ Always Use HTTPS
   - ✅ Automatic HTTPS Rewrites
   - ✅ TLS 1.3
3. Under **Origin Server** → create an **Origin Certificate** (if using self-signed on the server)

## Step 5: DDoS Protection (Automatic)

Cloudflare's free tier includes:
- **L3/L4 DDoS mitigation** — always-on, automatic
- **L7 DDoS mitigation** — enabled by default for proxied records
- **Rate limiting** — 1 free rule: set to 100 requests/min per IP on `/telemetry`

To add a rate limit rule:
1. Go to **Security** → **WAF** → **Rate limiting rules**
2. Create rule:
   - **If**: URI Path contains `/telemetry`
   - **Then**: Block for 60 seconds
   - **Rate**: 100 requests per minute per IP

## Step 6: Caching & Performance

1. **Caching** → **Configuration** → set Browser Cache TTL to **4 hours**
2. **Speed** → **Optimization** → enable:
   - ✅ Auto Minify (JS, CSS, HTML)
   - ✅ Brotli compression
3. **Caching** → **Cache Rules** → bypass cache for `/api/*` and `/ws/*` paths

## Step 7: Verify

```bash
# Should resolve to Cloudflare edge
dig openmtsn.org

# Should show valid SSL
curl -I https://openmtsn.org

# API should respond through Cloudflare proxy
curl https://api.openmtsn.org/health
```

---

## Optional: Cloudflare Tunnel (Zero-Trust Alternative)

For deployments behind a NAT or firewall, use [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/) to expose the server without opening ports:

```bash
# Install cloudflared on the server
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# Authenticate and create tunnel
cloudflared tunnel login
cloudflared tunnel create openmtsn
cloudflared tunnel route dns openmtsn openmtsn.org

# Run tunnel (maps localhost services to the domain)
cloudflared tunnel --url http://localhost:80 run openmtsn
```
