FROM python:3.12-slim AS base
ARG VERSION=1.0
RUN <<EOT
apt-get update
apt-get install -y curl
EOT
COPY <<-"EOF2" /app/config.txt
	key=value
EOF2
RUN pip install \
    requests
CMD ["python", "-m", "app"]
