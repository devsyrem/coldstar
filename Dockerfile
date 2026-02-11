FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    ca-certificates \
    pkg-config \
    libssl-dev \
 && rm -rf /var/lib/apt/lists/*

# Rust toolchain
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

COPY . .

# Install Python deps
RUN pip install --no-cache-dir -r local_requirements.txt



CMD ["python", "main.py"]