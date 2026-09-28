# AI Bank Statement Parser Micro-SaaS — Production Cloud Deployment Guide

This guide provides step-by-step instructions for deploying your AI Bank Statement Parser application to the web using **GitHub**, **Supabase (PostgreSQL)**, **Stripe (Live Subscriptions)**, and cloud hosting (**Vercel**, **Render**, **Fly.io**, or **Docker**).

---

## Architecture Overview

```
                      +-----------------------------+
                      |      Custom Domain / DNS    |
                      +--------------+--------------+
                                     |
               +---------------------+---------------------+
               |                                           |
               v                                           v
    +----------------------+                    +----------------------+
    |  Frontend on Vercel  |                    |  Backend (FastAPI)   |
    |  React 18 / Vite / TS|--- (/api/* rewrites)--> Render / Fly.io /  |
    |  (Static Edge CDN)   |                    |  Cloud Run Container |
    +----------------------+                    +----------+-----------+
                                                           |
                                      +--------------------+--------------------+
                                      |                    |                    |
                                      v                    v                    v
                             +-----------------+  +-----------------+  +-----------------+
                             |    Supabase     |  |     Stripe      |  |  Gemini AI /    |
                             |   PostgreSQL    |  |  Checkout & WH  |  |  Multimodal OCR |
                             +-----------------+  +-----------------+  +-----------------+
```

---

## 1. Supabase (PostgreSQL Database) Setup

1. Sign in to [Supabase](https://supabase.com) and click **New project**.
2. Set a database password and select a region close to your target users.
3. Once the database is provisioned, go to **Project Settings -> Database**:
   - Under **Connection string**, select **URI** and choose **Mode: Session** or **Transaction (Pgbouncer, port 6543)**.
   - Example connection string:
     ```
     postgresql://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?pgbouncer=true
     ```
4. Apply the initial schema:
   - Go to the **SQL Editor** in your Supabase dashboard.
   - Click **New Query**, copy the contents of [`supabase/migrations/20260928_initial_schema.sql`](supabase/migrations/20260928_initial_schema.sql), and click **Run**.
   - All 6 tables (`tenants`, `users`, `subscriptions`, `quota_usages`, `statements`, `processed_stripe_events`) and their indexes will be created.

---

## 2. Stripe Production Setup

1. Sign in to your [Stripe Dashboard](https://dashboard.stripe.com) and switch from Test Mode to Live Mode (or use Test Mode for staging).
2. Go to **Developers -> API keys**:
   - Copy **Secret key** (`sk_live_...` or `sk_test_...`) -> Set as `STRIPE_SECRET_KEY`.
   - Copy **Publishable key** (`pk_live_...` or `pk_test_...`) -> Set as `STRIPE_PUBLISHABLE_KEY`.
3. Configure the Webhook Endpoint:
   - In Stripe Dashboard, navigate to **Developers -> Webhooks -> Add destination**.
   - Endpoint URL: `https://<YOUR-BACKEND-DOMAIN>/api/billing/webhook`
   - Select events to listen to:
     - `checkout.session.completed`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
   - Click **Add endpoint**, then click **Reveal signing secret** (`whsec_...`).
   - Copy this secret -> Set as `STRIPE_WEBHOOK_SECRET`.
4. Enable the Customer Portal:
   - Navigate to **Settings -> Billing -> Customer portal**.
   - Enable customer subscription cancellations, plan switching, and payment method updates. Click **Save changes**.

---

## 3. GitHub Repository Setup

Your code is pre-configured with a `.gitignore` and GitHub Actions CI workflow in `.github/workflows/ci.yml`.

Run these commands in PowerShell from the project root:
```powershell
# 1. Initialize git and stage files
git init
git add .
git commit -m "feat: initial production release of AI Bank Statement Parser Micro-SaaS"

# 2. Create the remote repository on GitHub using the GitHub CLI
gh repo create bank-statement-parser-saas --public --source=. --push
```

---

## 4. Hosting Options

### Option A: Unified Container on Render (Recommended — Simplest)

Deploying a single unified container serves both the API and the React frontend from the same origin, with zero CORS complexity:

1. Sign in to [Render](https://render.com).
2. Click **New + -> Blueprint**.
3. Connect your GitHub repository `bank-statement-parser-saas`.
4. Render will detect [`render.yaml`](render.yaml) automatically, provisioning:
   - `ai-bank-statement-parser` Docker web service.
   - `bank-statement-db` managed PostgreSQL database.
5. In the Render Dashboard, add your environment variables:
   - `BILLING_MODE`: `live`
   - `STRIPE_SECRET_KEY`: `sk_live_...`
   - `STRIPE_PUBLISHABLE_KEY`: `pk_live_...`
   - `STRIPE_WEBHOOK_SECRET`: `whsec_...`
   - `DATABASE_URL`: Your Supabase connection string (or use Render's managed database).
6. Click **Apply**. Your app is live at `https://ai-bank-statement-parser.onrender.com`!

---

### Option B: Frontend on Vercel + Backend on Render/Fly.io

If you prefer hosting the React frontend on Vercel's global Edge CDN:

1. **Deploy the Backend first** on Render, Railway, or Fly.io (following Option A or C). Note your backend URL (e.g. `https://api.yourdomain.com`).
2. **Deploy the Frontend on Vercel**:
   - Go to [Vercel](https://vercel.com) and click **Add New -> Project**.
   - Import your GitHub repository.
   - Set **Root Directory** to `frontend`.
   - Build Command: `npm run build`
   - Output Directory: `dist`
   - Environment Variables:
     - Set `VITE_API_URL` (if overriding direct origin) or use `vercel.json` rewrites.
3. Deploy! Vercel will distribute the static assets across global edge locations.

---

### Option C: Fly.io Deployment

1. Install Fly CLI: `powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"`
2. Authenticate: `fly auth login`
3. Launch and set secrets:
   ```powershell
   fly launch --no-deploy
   fly secrets set DATABASE_URL="postgresql://..." SECRET_KEY="..." STRIPE_SECRET_KEY="..." STRIPE_WEBHOOK_SECRET="..." BILLING_MODE="live"
   fly deploy
   ```

---

## 5. Production Environment Variables Reference

| Variable | Description | Example / Default |
|---|---|---|
| `PROJECT_NAME` | Application display name | `AI Bank Statement Parser` |
| `API_V1_STR` | API prefix route | `/api` |
| `SECRET_KEY` | JWT signing secret key (min 32 chars) | Random 64-char hex string |
| `DATABASE_URL` | Supabase / PostgreSQL connection URI | `postgresql://postgres:...@...supabase.co:6543/postgres` |
| `BILLING_MODE` | Billing adapter mode (`live` or `mock`) | `live` |
| `STRIPE_SECRET_KEY` | Stripe secret API key | `sk_live_...` |
| `STRIPE_PUBLISHABLE_KEY` | Stripe publishable API key | `pk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret | `whsec_...` |
| `UPLOAD_DIR` | Directory for temporary statement files | `storage/uploads` |
| `FREE_PAGE_LIMIT` | Monthly quota for Free tier | `5` |
| `STARTER_PAGE_LIMIT`| Monthly quota for Starter tier ($19/mo) | `50` |
| `PRO_PAGE_LIMIT` | Monthly quota for Pro tier ($49/mo) | `500` |
| `GEMINI_API_KEY` | Optional: Gemini API key for fallback | `AIzaSy...` |

---

## 6. Verification & Health Monitoring

Once deployed, verify your live system by checking the health endpoint:
```bash
curl https://<YOUR-PRODUCTION-DOMAIN>/api/health
```
Expected response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "checks": {
    "database": "operational",
    "file_storage": "operational",
    "parsing_pipeline": "operational",
    "billing_adapter": "operational"
  }
}
```
