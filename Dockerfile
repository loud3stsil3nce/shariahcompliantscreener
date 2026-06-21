FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

# Copy source code
COPY . .

# Expose Streamlit's default port
EXPOSE 8001

# Run the web dashboard on startup
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8001"]