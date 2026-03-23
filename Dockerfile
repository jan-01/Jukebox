# Dockerfile
FROM python:3.11-slim

# ---- create non-root user ----
ARG APP_USER=jukebox
ARG APP_UID=1000

# create user
RUN useradd --uid ${APP_UID} --create-home --shell /bin/bash ${APP_USER}

WORKDIR /app

# copy only requirements first to leverage cache
COPY backend/requirements.txt .

# install python deps; upgrade wheel+setuptools to avoid known HIGH CVEs in vendored packages
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade wheel setuptools

# copy app
COPY . .

# make sure files are owned by non-root user
RUN chown -R ${APP_USER}:${APP_USER} /app

# switch to non-root user
USER ${APP_USER}

ENV FLASK_APP=backend/app.py
ENV FLASK_RUN_HOST=0.0.0.0
EXPOSE 5000

# healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -f http://127.0.0.1:5000/ || exit 1

CMD ["python", "backend/app.py"]
