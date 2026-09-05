FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir fastapi uvicorn python-dotenv telethon google-auth-oauthlib google-api-python-client

# Copy the service
COPY service.py .

EXPOSE 8000

CMD ["python", "service.py"]
