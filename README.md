# OpenRouter OpenAI-Compatible Proxy

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Framework-FastAPI-green.svg)](https://fastapi.tiangolo.com/)

A simple yet robust FastAPI proxy server designed to interface with the OpenRouter API while providing OpenAI-compatible endpoints. It intelligently rotates through multiple OpenRouter API keys, automatically retrying requests upon hitting rate limits, ensuring higher availability and load distribution for your applications.

## Features

*   **OpenAI Compatibility:** Exposes `/v1/chat/completions` and `/v1/models` endpoints, allowing seamless integration with tools and libraries designed for the OpenAI API.
*   **API Key Rotation:** Utilizes a list of OpenRouter API keys in a round-robin fashion for outgoing requests.
*   **Rate Limit Handling:** Automatically retries requests with the next available API key upon receiving a 429 (Rate Limit Exceeded) error from OpenRouter.
*   **Streaming Support:** Fully supports streaming responses for chat completions (`stream=True`).
*   **Authentication:** Optional bearer token authentication to secure the proxy endpoint.
*   **Configuration via Environment Variables:** Easily configure API keys, allowed tokens, and other settings.
*   **Asynchronous:** Built with FastAPI and `httpx` for efficient asynchronous request handling.
*   **Docker Support:** Includes `Dockerfile` and `docker-compose.yml` for easy containerized deployment.

## Why Use This Proxy?

*   **Load Balancing:** Distribute your OpenRouter API usage across multiple keys.
*   **Increased Rate Limits:** Effectively increase your application's overall rate limit by pooling keys.
*   **Improved Resilience:** Automatically handles temporary rate limits on individual keys, reducing request failures.
*   **Simplified Client Configuration:** Clients can point to a single proxy endpoint instead of managing multiple keys or complex retry logic.
*   **OpenAI Ecosystem Integration:** Use OpenRouter models with tools built for the OpenAI API standard.

## Setup and Installation

### Prerequisites

*   Python 3.8+
*   `pip` (Python package installer)
*   (Optional) Docker and Docker Compose

### Steps

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url> # Replace with your repository URL
    cd openrouterproxy # Or your repository directory name
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    # You might also need python-dotenv if not already included indirectly
    pip install python-dotenv
    ```

3.  **Configure Environment Variables:**
    Create a `.env` file in the project root directory and add the following variables:

    ```dotenv
    # Required: Comma-separated list of your OpenRouter API keys
    OPENROUTER_API_KEYS="sk-or-v1-abc...,sk-or-v1-xyz...,sk-or-v1-123..."

    # Optional: Comma-separated list of allowed bearer tokens for proxy authentication
    # If empty or not set, authentication is disabled.
    # ALLOWED_AUTH_TOKENS="your-secret-token-1,your-secret-token-2"

    # Optional: Recommended by OpenRouter for tracking usage
    # Replace with your actual site/app info if applicable
    YOUR_SITE_URL="http://localhost:8000" # URL where this proxy is hosted or the app using it
    YOUR_APP_NAME="My OpenRouter App"    # Name of your application

    # Optional: Host and Port for the proxy server
    # HOST="0.0.0.0" # Default is 127.0.0.1
    # PORT="8000"    # Default is 8000
    ```

    **Important:** Add `.env` to your `.gitignore` file to avoid committing your API keys!

## Running the Proxy

### Using Uvicorn (Directly)

```bash
uvicorn main:app --host ${HOST:-127.0.0.1} --port ${PORT:-8000} --reload
```

*   `--reload` is useful for development, automatically restarting the server on code changes. Remove it for production.
*   The command uses environment variables `HOST` and `PORT` if set, otherwise defaults to `127.0.0.1:8000`.

### Using Docker

1.  **Build the Docker image:**
    ```bash
    docker build -t openrouter-proxy .
    ```

2.  **Run the Docker container:**
    Make sure your `.env` file is present in the current directory.
    ```bash
    docker run --rm -p 8000:8000 --env-file .env openrouter-proxy
    ```
    *   This maps port 8000 on your host to port 8000 in the container. Adjust if needed.
    *   `--env-file .env` loads the environment variables from your `.env` file.

### Using Docker Compose

Ensure your `.env` file is present.

```bash
docker-compose up -d
```

*   This will build the image (if necessary) and run the container in detached mode based on the `docker-compose.yml` file.
*   To stop the service: `docker-compose down`

## Configuration Details

The proxy is configured using the following environment variables (typically set in a `.env` file):

*   `OPENROUTER_API_KEYS` (Required): A comma-separated string of your OpenRouter API keys.
*   `ALLOWED_AUTH_TOKENS` (Optional): A comma-separated string of bearer tokens. If set, clients must provide one of these tokens in the `Authorization: Bearer <token>` header to use the proxy. If not set or empty, authentication is disabled.
*   `YOUR_SITE_URL` (Optional, Recommended): The URL of your site or application using the proxy. Sent as the `Referer` header to OpenRouter. Defaults to `http://localhost:8000`.
*   `YOUR_APP_NAME` (Optional, Recommended): The name of your application. Sent as the `X-Title` header to OpenRouter. Defaults to `OpenRouter Key Rotator`.
*   `HOST` (Optional): The host address the proxy server binds to. Defaults to `127.0.0.1`. Use `0.0.0.0` to make it accessible externally (e.g., within Docker).
*   `PORT` (Optional): The port the proxy server listens on. Defaults to `8000`.

## Usage

Point your OpenAI-compatible client library or tool to the proxy's base URL (e.g., `http://localhost:8000/v1`).

### Example with `curl`

**Chat Completion (Non-Streaming):**

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-token-1" \ # Include if auth is enabled
  -d '{
    "model": "openai/gpt-3.5-turbo", # Or any model available via your OpenRouter keys
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

**Chat Completion (Streaming):**

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-token-1" \ # Include if auth is enabled
  -d '{
    "model": "openai/gpt-3.5-turbo",
    "messages": [
      {"role": "user", "content": "Tell me a short story."}
    ],
    "stream": true
  }'
```

**List Models:**

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer your-secret-token-1" # Include if auth is enabled
```

### Authentication

If `ALLOWED_AUTH_TOKENS` is set in your environment, clients **must** include a valid token in the `Authorization` header:

```
Authorization: Bearer <your-valid-token>
```

If the header is missing or the token is invalid, the proxy will return a `401 Unauthorized` or `403 Forbidden` error.

## API Endpoints

*   `POST /v1/chat/completions`: Proxies requests to the OpenRouter chat completions endpoint. Supports standard OpenAI API parameters, including `stream`.
*   `GET /v1/models`: Proxies requests to the OpenRouter models endpoint, returning a list of available models accessible via the configured keys.
*   `GET /`: Simple health check endpoint.

## License

This project is open-source. Please add your preferred license (e.g., MIT, Apache 2.0). If you don't have one, consider adding the MIT License:

```
MIT License

Copyright (c) [Year] [Your Name/Organization]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Replace `[Year]` and `[Your Name/Organization]`.
