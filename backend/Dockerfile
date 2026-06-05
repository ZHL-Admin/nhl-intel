# Use Python 3.11 slim image for Cloud Run
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Cloud Run will set PORT env var)
ENV PORT=8080

# Run uvicorn server
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
