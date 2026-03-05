FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libindi-dev \
    indi-bin \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python test dependencies
RUN pip install --no-cache-dir pytest pyyaml

# Set working directory
WORKDIR /workspace

# Copy project
COPY . .

# Expose INDI server port
EXPOSE 7624

# Default command
CMD ["/bin/bash"]
