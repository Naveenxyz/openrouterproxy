# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependency list
COPY requirements.txt .

# Install any needed dependencies specified in requirements.txt
# --no-cache-dir reduces image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY main.py .

# Make port 8000 available to the world outside this container
# (The actual mapping happens in docker-compose.yml)
EXPOSE 8000

# Define environment variable defaults (can be overridden by docker-compose)
ENV HOST=0.0.0.0
ENV PORT=8000
ENV YOUR_SITE_URL="http://localhost:8000"
ENV YOUR_APP_NAME="OpenRouter Key Rotator"

# Check if OPENROUTER_API_KEYS is set at runtime (optional but good practice)
# Note: This check runs when the container starts, not during build.
# Uvicorn command will run next.
# CMD ["sh", "-c", "if [ -z \"$OPENROUTER_API_KEYS\" ]; then echo 'Error: OPENROUTER_API_KEYS is not set.'; exit 1; fi && uvicorn main:app --host $HOST --port $PORT"]

# Run main.py using uvicorn when the container launches
# Using 0.0.0.0 makes the server accessible from outside the container
# The Python script itself reads some ENV VARS (KEYS, SITE_URL, APP_NAME)
# Uvicorn uses HOST/PORT from ENV or defaults (set above or overridden).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Development Variant (Optional) ---
# If you want live reloading during development, uncomment the volume mount
# in docker-compose.yml and use this CMD instead:
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]