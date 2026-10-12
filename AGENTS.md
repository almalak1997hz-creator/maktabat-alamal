# Repository Guidelines

## Project Structure & Module Organization

This repository contains a Windows-based bookstore inventory and point-of-sale application. The root `app.py` is the Flask web application; its Jinja templates are in `templates/`, styles and static assets in `static/`, and uploaded product images in `product_images/`. `launcher.py` starts the web app and, when available, a Cloudflare quick tunnel. `main.py` is the separate Tkinter desktop application. The `maktabat_alamal_web/` directory is a packaged web copy; check which copy a change targets before editing it. `maktabat_alamal.db`, `backups/`, and `invoices/` hold local business data and generated files. Avoid committing live or personal data.

## Build, Test, and Development Commands

Use Windows with Python installed. Run `install.bat` once to install dependencies from `requirements.txt` (Flask and Waitress). Run `start.bat` for the normal launcher flow. To run the web app directly for local development, use `python app.py` and open `http://127.0.0.1:5000`. Run the desktop edition with `python main.py`. No automated test suite or build step is currently configured; validate changes manually in the affected application.

## Coding Style & Naming Conventions

Follow the existing Python style: four-space indentation, `snake_case` for functions and variables, and uppercase names for module constants. Keep Flask routes and database operations in `app.py` consistent with existing patterns; use parameterized SQLite queries. Name Jinja templates by feature (for example, `inventory.html`) and keep page styling in the corresponding static CSS. Preserve UTF-8 for Arabic text and avoid reformatting unrelated legacy code.

## Testing Guidelines

There is no checked-in test framework or test directory. For web changes, start the app and exercise the affected route and form in a browser; for desktop changes, launch `main.py` and check the affected workflow. Use a disposable database copy when testing writes, since the root database may contain real inventory and sales.

## Commit & Pull Request Guidelines

Git history was unavailable in this checkout, so no established commit-message convention could be confirmed. Use short imperative commit subjects (for example, `Fix inventory search`). Pull requests should describe the user-visible change, identify the application copy affected, list manual verification steps, and include screenshots for visual changes. Call out database schema changes and backup or migration needs.

## Security & Configuration

Do not commit `.secret_key`, database files, customer data, or tunnel URLs. Change the initial `admin` / `1234` password before exposing the app; keep `.secret_key` private. Cloudflare quick-tunnel links are temporary and provide external access to the local server.
