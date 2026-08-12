FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required by Manim
RUN apt-get update && apt-get install -y \
  ffmpeg \
  libcairo2-dev \
  libpango1.0-dev \
  pkg-config \
  python3-dev \
  build-essential \
  && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Create required directories
RUN mkdir -p uploads outputs

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]