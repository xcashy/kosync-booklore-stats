# KoSync Booklore Stats Proxy

A KoSync proxy server that sits between KoSync-compatible reading apps and Booklore to track reading sessions for the Booklore Reading Stats feature.

Works with any app that supports the KoSync protocol, including KOReader and Readest

**Important:** The reading app must be configured to sync progress automatically. Ideally on every page turn (Readest does this by default)

## Architecture

```
KoSync Client → Proxy (Flask) → Booklore KoSync Server
                    ↓
               MySQL (Sessions)
```

## Features

- **Transparent Proxy**: Forwards all KoSync requests to Booklore
- **Reading Session Tracking**: Automatically captures reading sessions
- **Inactivity Timeout**: Ends sessions after configurable minutes of inactivity
- **Progress Tracking**: Stores start/end positions and progress
- **Graceful Shutdown**: On container stop (`docker stop`), the proxy catches `SIGTERM` and flushes all active sessions to the database before exiting. No reading data is lost during restarts or updates.

## Session Tracking

When a user updates progress or retrieves it via the proxy:
1. Proxy forwards request to Booklore
2. On success, a reading session is created/updated
3. Session tracks start progress, end progress, duration
4. After `SESSION_TIMEOUT_MINUTES` of inactivity, session is saved to database
5. Next activity on same book restarts a new session

## Installation

Example `docker-compose.yml`:

```yaml
services:
  kosync-booklore-stats:
      image: xcashy/kosync-booklore-stats:latest
      container_name: kosync-booklore-stats
      ports:
        - "5000:5000"
      environment:
        TZ: ${TZ}
        BOOKLORE_KOSYNC_URL: http://booklore:${BOOKLORE_PORT}/api/koreader
        SESSION_TIMEOUT_MINUTES: 10
        SESSION_MIN_DURATION_SECONDS: 10
        DB_HOST: mariadb
        DB_PORT: 3306
        DB_USER: ${DB_USER}
        DB_PASSWORD: ${DB_PASSWORD}
        DB_NAME: ${MYSQL_DATABASE}
      depends_on:
        booklore:
          condition: service_healthy
        mariadb:
          condition: service_healthy
      restart: unless-stopped

  booklore:
    image: booklore/booklore:latest
    # Alternative: Use GitHub Container Registry
    # image: ghcr.io/booklore-app/booklore:latest
    container_name: booklore
    environment:
      - USER_ID=${APP_USER_ID}
      - GROUP_ID=${APP_GROUP_ID}
      - TZ=${TZ}
      - DATABASE_URL=${DATABASE_URL}
      - DATABASE_USERNAME=${DB_USER}
      - DATABASE_PASSWORD=${DB_PASSWORD}
      - BOOKLORE_PORT=${BOOKLORE_PORT}
    depends_on:
      mariadb:
        condition: service_healthy
    ports:
      - "${BOOKLORE_PORT}:${BOOKLORE_PORT}"
    volumes:
      - ./data:/app/data
      - ./books:/books
      - ./bookdrop:/bookdrop
    healthcheck:
      test: wget -q -O - http://localhost:${BOOKLORE_PORT}/api/v1/healthcheck
      interval: 60s
      retries: 5
      start_period: 60s
      timeout: 10s
    restart: unless-stopped

  mariadb:
    image: lscr.io/linuxserver/mariadb:11.4.5
    container_name: mariadb
    environment:
      - PUID=${DB_USER_ID}
      - PGID=${DB_GROUP_ID}
      - TZ=${TZ}
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}
      - MYSQL_DATABASE=${MYSQL_DATABASE}
      - MYSQL_USER=${DB_USER}
      - MYSQL_PASSWORD=${DB_PASSWORD}
    volumes:
      - ./mariadb/config:/config
    restart: unless-stopped
    healthcheck:
      test: [ "CMD", "mariadb-admin", "ping", "-h", "localhost" ]
      interval: 5s
      timeout: 5s
      retries: 10
```

## Usage

In your reading app (KOReader, Readest, etc.), configure the KoSync server URL to point to the proxy instead of Booklore directly:

```
http://<proxy-host>:5000
```

Example: If your proxy runs at `192.168.1.100:5000`, use that as the KoSync server URL instead of `http://192.168.1.100:6060/api/koreader`.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `BOOKLORE_KOSYNC_URL` | Booklore KOReader API Path | `http://booklore:6060/api/koreader` |
| `SESSION_TIMEOUT_MINUTES` | Minutes until inactive session is closed | `10` |
| `SESSION_MIN_DURATION_SECONDS` | Minimum session duration to be saved | `10` |
| `PROGRESS_DECIMAL_PLACES` | Decimal places for progress percentage | `1` |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `DB_HOST` | Database host | `mariadb` |
| `DB_PORT` | Database port | `3306` |
| `DB_USER` | Database user | `booklore` |
| `DB_PASSWORD` | Database password | `password` |
| `DB_NAME` | Database name | `booklore` |
| `TZ` | Timezone for log timestamps | - | 