# ============================================================
# Stage 1: Build React frontend
# ============================================================
FROM node:20-alpine AS frontend

WORKDIR /build
COPY web/package.json web/package-lock.json* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install
COPY web/ .
RUN npm run build


# ============================================================
# Stage 2: Python application + built frontend
# ============================================================
FROM python:3.10-slim-bookworm

# Build arg: set to "false" to skip Playwright/Chromium (~800MB savings)
ARG INSTALL_PLAYWRIGHT=true

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libxml2-dev \
    libxslt1-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browser (optional, for legacy CanLII deep scraping)
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
        playwright install --with-deps chromium; \
    fi

# Copy application source
COPY api/ api/
COPY scraper/ scraper/
COPY utils/ utils/
COPY database/ database/
COPY main.py main_playwright.py main_multi.py ./
COPY config.json ./

# Copy built frontend from Stage 1
COPY --from=frontend /build/dist/ web/dist/

# Copy startup script
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"]
