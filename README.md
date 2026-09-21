# Mitsubishi Electric — Demand Forecasting Console

A self-contained, static HTML dashboard showing the FY2025 unit sales and
revenue forecasts (company-wide, by category, and by SKU for the 948
highest-volume items), backtested model accuracy, and customer/industry
breakdowns. No server or build step required — it's a single HTML file
with the forecast data and all logic embedded directly in it.

## Hosting this on GitHub Pages

1. **Create a new repository** on GitHub (or use this one, if you've
   forked/cloned it already).
2. **Add `index.html`** to the root of the repository — it's already
   named `index.html` in this folder, which is what GitHub Pages looks
   for by default.
   ```
   git add index.html README.md
   git commit -m "Add forecasting dashboard"
   git push
   ```
3. **Enable GitHub Pages**:
   - Go to your repository on GitHub → **Settings** → **Pages** (left
     sidebar, under "Code and automation").
   - Under **Build and deployment** → **Source**, choose **Deploy from
     a branch**.
   - Under **Branch**, choose `main` (or whichever branch you pushed
     to) and folder `/ (root)`, then **Save**.
   - GitHub will show a message like "Your site is live at
     `https://<your-username>.github.io/<repo-name>/`" — it usually
     takes 1–2 minutes to go live after the first push.
4. **Every time you update `index.html`** (a new quarter's forecast,
   say) and push it to the same branch, the live site updates
   automatically within a minute or two — no extra steps needed.

## Updating the forecast data

The dashboard's data (actuals, forecasts, backtest results) is embedded
directly in `index.html` as a JSON blob. To refresh it with a new
quarter's data:

1. Re-run the Python pipeline (see the separate pipeline package) on
   updated sales data to produce a new `dashboard_data.json`.
2. Re-run `build_dashboard.py` from that same pipeline, which injects
   the new `dashboard_data.json` and the dashboard's `app.js` into a
   fresh `index.html`.
3. Replace `index.html` in this repository with the newly built one,
   commit, and push — GitHub Pages picks up the change automatically.

## Notes

- This is a **static site**: any edits a visitor makes in the dashboard
  (the FY2025 target field, inventory parameters) are saved in *their
  own browser's local storage only* — they are not shared between
  visitors and are not saved back to this repository. If you need
  shared/multi-user editing, that requires a real backend, which is a
  separate project.
- The page loads Chart.js from a public CDN (cdnjs.cloudflare.com) for
  the charts — an internet connection is required to view the charts,
  even though the page itself is static.
- No API keys, secrets, or credentials are used anywhere in this file —
  it's safe to make the repository public.

## Files

| File | Purpose |
|---|---|
| `index.html` | The full dashboard — self-contained HTML/CSS/JS with the forecast data embedded. This is the only file GitHub Pages needs to serve the site. |
| `README.md` | This file. |
