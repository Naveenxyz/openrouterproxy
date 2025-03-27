import os
import httpx
import asyncio
import logging
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse, JSONResponse
from typing import List, Optional, Set
import json
import dotenv

dotenv.load_dotenv()

# --- Configuration ---
# Load API keys from environment variable (comma-separated)
OPENROUTER_API_KEYS_STR = os.environ.get("OPENROUTER_API_KEYS", "")
if not OPENROUTER_API_KEYS_STR:
    print("❌ ERROR: OPENROUTER_API_KEYS environment variable not set or empty.")
    print("   Please set it to a comma-separated list of your OpenRouter API keys.")
    print("   Example: export OPENROUTER_API_KEYS='sk-or-v1-abc...,sk-or-v1-xyz...'")
    exit(1)

OPENROUTER_API_KEYS = [key.strip() for key in OPENROUTER_API_KEYS_STR.split(',')]
NUM_KEYS = len(OPENROUTER_API_KEYS)
print(f"✅ Loaded {NUM_KEYS} OpenRouter API keys.")

# Load allowed authentication tokens (comma-separated)
ALLOWED_AUTH_TOKENS_STR = os.environ.get("ALLOWED_AUTH_TOKENS", "")
if not ALLOWED_AUTH_TOKENS_STR:
    print("⚠️ WARNING: ALLOWED_AUTH_TOKENS environment variable not set or empty. Authentication disabled.")
    ALLOWED_AUTH_TOKENS: Set[str] = set() # Empty set means no auth required
else:
    ALLOWED_AUTH_TOKENS = {token.strip() for token in ALLOWED_AUTH_TOKENS_STR.split(',')}
    print(f"✅ Loaded {len(ALLOWED_AUTH_TOKENS)} allowed authentication tokens. Authentication enabled.")


# OpenRouter API endpoint
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_CHAT_ENDPOINT = f"{OPENROUTER_API_BASE}/chat/completions"
OPENROUTER_MODELS_ENDPOINT = f"{OPENROUTER_API_BASE}/models" # Added models endpoint

# Optional: Referer and X-Title headers (replace with your actual site/app)
# OpenRouter docs recommend setting these: https://openrouter.ai/docs#requests
YOUR_SITE_URL = os.environ.get("YOUR_SITE_URL", "http://localhost:8000") # Your app's URL
YOUR_APP_NAME = os.environ.get("YOUR_APP_NAME", "OpenRouter Key Rotator") # Your app's name

# Global index for round-robin key selection
current_key_index = 0
key_lock = asyncio.Lock() # Lock for safely updating the index

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- FastAPI App ---
app = FastAPI(
    title="OpenRouter OpenAI-Compatible Proxy",
    description="A proxy that rotates OpenRouter keys and retries on rate limits.",
)

# --- Shared HTTP Client ---
# Reuse the client for better performance
client = httpx.AsyncClient(timeout=600.0) # Increase timeout for long generations

@app.on_event("shutdown")
async def shutdown_event():
    """Close the httpx client on application shutdown."""
    await client.aclose()
    logger.info("HTTPX client closed.")

# --- Helper Functions ---
async def get_next_key_index() -> int:
    """Safely gets the next key index for round-robin rotation."""
    global current_key_index
    async with key_lock:
        idx = current_key_index
        current_key_index = (current_key_index + 1) % NUM_KEYS
        return idx

async def stream_response_generator(api_response: httpx.Response):
    """Async generator to stream chunks from the OpenRouter response."""
    try:
        async for chunk in api_response.aiter_bytes():
            yield chunk
    except Exception as e:
        logger.error(f"Error while streaming response: {e}")
    finally:
        await api_response.aclose() # Ensure the response is closed

# --- Authentication Dependency ---
async def verify_token(authorization: Optional[str] = Header(None)):
    """Dependency to verify the provided Bearer token."""
    # Only enforce auth if ALLOWED_AUTH_TOKENS is configured
    if not ALLOWED_AUTH_TOKENS:
        return # No auth required

    if authorization is None:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication scheme",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if token not in ALLOWED_AUTH_TOKENS:
            raise HTTPException(
                status_code=403, # Use 403 Forbidden for invalid token
                detail="Invalid authentication token",
            )
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # If token is valid, proceed
    return

# --- API Endpoint ---
@app.post("/v1/chat/completions")
async def chat_completions(request: Request, _=Depends(verify_token)): # Add dependency here
    """
    Handles chat completion requests, proxies them to OpenRouter,
    manages key rotation, and retries on rate limits.
    """
    try:
        request_data = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    is_streaming = request_data.get("stream", False)
    model_name = request_data.get("model", "unknown_model")

    start_key_index = await get_next_key_index()
    last_error_status = 500 # Default error if all keys fail
    last_error_detail = "All API keys failed."

    for i in range(NUM_KEYS):
        key_index = (start_key_index + i) % NUM_KEYS
        api_key = OPENROUTER_API_KEYS[key_index]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": YOUR_SITE_URL,  # Recommended by OpenRouter
            "X-Title": YOUR_APP_NAME,       # Recommended by OpenRouter
        }

        logger.info(f"Attempting request for model '{model_name}' with key index {key_index} (Stream: {is_streaming})")

        try:
            if is_streaming:
                # Make streaming request
                req = client.build_request(
                    "POST", OPENROUTER_CHAT_ENDPOINT, json=request_data, headers=headers
                )
                api_response = await client.send(req, stream=True)

                if api_response.status_code == 200:
                    logger.info(f"Streaming success with key index {key_index}.")
                    # Return StreamingResponse immediately
                    return StreamingResponse(
                        stream_response_generator(api_response),
                        media_type="text/event-stream", # OpenAI uses this
                        headers={k: v for k, v in api_response.headers.items() if k.lower() in ['content-type', 'content-encoding']} # Forward relevant headers
                    )
                elif api_response.status_code == 429:
                    error_detail = f"Rate limit exceeded for key index {key_index}."
                    try: # Try to read error detail if available
                        error_body = await api_response.aread()
                        error_detail += f" Response: {error_body.decode()}"
                    except Exception: pass # Ignore if reading fails
                    await api_response.aclose() # Close the response before retrying
                    logger.warning(error_detail)
                    last_error_status = 429
                    last_error_detail = error_detail
                    # Continue to the next key
                else:
                    # Handle other errors for streaming request
                    error_body = await api_response.aread()
                    error_detail = f"Error with key index {key_index}: Status {api_response.status_code}, Response: {error_body.decode()}"
                    await api_response.aclose()
                    logger.error(error_detail)
                    last_error_status = api_response.status_code
                    last_error_detail = error_detail
                    # Consider if you want to retry on all errors or just 429
                    # For now, we retry on any non-200 if more keys are available
                    if i == NUM_KEYS - 1: # Last key failed
                         raise HTTPException(status_code=last_error_status, detail=last_error_detail)
                    # Otherwise, continue to the next key (handled by the loop)

            else:
                # Make non-streaming request
                api_response = await client.post(
                    OPENROUTER_CHAT_ENDPOINT, json=request_data, headers=headers
                )

                if api_response.status_code == 200:
                    logger.info(f"Non-streaming success with key index {key_index}.")
                    # Return JSON response
                    return JSONResponse(content=api_response.json(), status_code=api_response.status_code)
                elif api_response.status_code == 429:
                    error_detail = f"Rate limit exceeded for key index {key_index}."
                    try:
                        error_detail += f" Response: {api_response.text}"
                    except Exception: pass
                    logger.warning(error_detail)
                    last_error_status = 429
                    last_error_detail = error_detail
                    # Continue to the next key
                else:
                    # Handle other errors for non-streaming request
                    error_detail = f"Error with key index {key_index}: Status {api_response.status_code}, Response: {api_response.text}"
                    logger.error(error_detail)
                    last_error_status = api_response.status_code
                    last_error_detail = error_detail
                    # Consider if you want to retry on all errors or just 429
                    if i == NUM_KEYS - 1: # Last key failed
                         raise HTTPException(status_code=last_error_status, detail=last_error_detail)
                    # Otherwise, continue to the next key (handled by the loop)

        except httpx.RequestError as e:
            # Network errors, timeouts etc.
            error_detail = f"HTTPX Request Error with key index {key_index}: {e.__class__.__name__} - {e}"
            logger.error(error_detail)
            last_error_status = 503 # Service Unavailable might be appropriate
            last_error_detail = error_detail
            # Decide if you want to retry on network errors. Let's retry for now.
            if i == NUM_KEYS - 1: # Last key attempt also failed with network error
                raise HTTPException(status_code=last_error_status, detail=last_error_detail)
            # Otherwise, continue loop to try next key

        except Exception as e:
            # Catch unexpected errors during request processing
            error_detail = f"Unexpected error processing request with key index {key_index}: {e.__class__.__name__} - {e}"
            logger.exception(error_detail) # Log full traceback
            last_error_status = 500
            last_error_detail = error_detail
            # It might be safer to stop retrying on unexpected errors
            # but for robustness in case it was key-specific, we'll try others.
            if i == NUM_KEYS - 1:
                raise HTTPException(status_code=last_error_status, detail=last_error_detail)
            # Otherwise, continue loop to try next key


    # If the loop completes without returning/raising, all keys failed.
    logger.error(f"All {NUM_KEYS} API keys failed for the request. Last error: {last_error_status} - {last_error_detail}")
    raise HTTPException(status_code=last_error_status, detail=last_error_detail)


@app.get("/v1/models")
async def get_models(_=Depends(verify_token)): # Add dependency here
    """
    Fetches the list of available models from OpenRouter.
    Uses the first configured API key.
    """
    api_key = OPENROUTER_API_KEYS[0] # Use the first key for this simple request
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": YOUR_SITE_URL,
        "X-Title": YOUR_APP_NAME,
    }

    logger.info("Fetching models list from OpenRouter...")
    try:
        response = await client.get(OPENROUTER_MODELS_ENDPOINT, headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        logger.info("Successfully fetched models list.")
        return JSONResponse(content=response.json(), status_code=response.status_code)

    except httpx.HTTPStatusError as e:
        error_detail = f"Error fetching models: Status {e.response.status_code}, Response: {e.response.text}"
        logger.error(error_detail)
        raise HTTPException(status_code=e.response.status_code, detail=error_detail)
    except httpx.RequestError as e:
        error_detail = f"HTTPX Request Error fetching models: {e.__class__.__name__} - {e}"
        logger.error(error_detail)
        raise HTTPException(status_code=503, detail=error_detail) # Service Unavailable
    except Exception as e:
        error_detail = f"Unexpected error fetching models: {e.__class__.__name__} - {e}"
        logger.exception(error_detail) # Log full traceback
        raise HTTPException(status_code=500, detail=error_detail)


@app.get("/")
async def read_root():
    return {"message": "OpenRouter Key Rotator Proxy is running. Use POST /v1/chat/completions and GET /v1/models."} # Updated message

# --- Main execution ---
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting OpenRouter Proxy Server...")
    # Get host and port from environment variables or use defaults
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)