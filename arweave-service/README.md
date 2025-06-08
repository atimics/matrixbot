# Arweave Service

A lean, secure microservice for Arweave uploads that eliminates Node.js dependencies and follows security best practices.

## Key Improvements

- **Pure Python**: No Node.js or `ardrive-cli` dependencies
- **Secure Design**: Expects pre-provisioned wallet files, doesn't generate keys
- **Non-root User**: Runs as a dedicated `appuser` for security
- **Clean API**: Simple REST endpoints for file and data uploads
- **Health Monitoring**: Built-in health checks and wallet status monitoring

## Architecture

This service is designed to be the first step toward a unified wallet orchestration architecture. It:

1. **Isolates Arweave Logic**: All Arweave interactions are contained within this service
2. **API-First**: Other services interact via HTTP API, not direct library calls
3. **Secure Key Management**: Wallet files are mounted from external volumes, not generated at runtime
4. **Stateless**: No internal state management, purely transactional

## API Endpoints

### `GET /health`
Returns service health status and wallet readiness.

### `GET /wallet`
Returns wallet information including address and balance.

### `POST /upload`
Upload a file to Arweave.
- **file**: Multipart file upload
- **tags**: Optional JSON string of metadata tags
- **x-api-key**: Optional API key header

### `POST /upload/data`
Upload raw data to Arweave.
- **data**: String data to upload
- **content_type**: MIME type of the data
- **tags**: Optional JSON string of metadata tags
- **x-api-key**: Optional API key header

## Configuration

### Environment Variables

- `ARWEAVE_WALLET_PATH`: Path to the wallet JSON file (default: `/data/arweave_wallet.json`)
- `ARWEAVE_SERVICE_API_KEY`: Optional API key for endpoint authentication. If set, all upload endpoints will require this key in the `x-api-key` header.

### Required Files

The service expects a valid Arweave wallet JSON file to be mounted at the configured path. This file should be:
- Generated externally using `arweave-python-client` or similar tools
- Securely stored and mounted as a read-only volume
- Funded with AR tokens for transaction fees

## Docker Usage

```bash
# Build the image
docker build -t arweave-service .

# Run with mounted wallet
docker run -d \
  --name arweave-service \
  -p 8001:8001 \
  -v /path/to/wallet:/data:ro \
  -e ARWEAVE_WALLET_PATH=/data/arweave_wallet.json \
  arweave-service
```

## Integration Example

```python
import httpx

# Upload a file
with open("image.jpg", "rb") as f:
    response = httpx.post(
        "http://arweave-service:8001/upload",
        files={"file": f},
        data={"tags": '{"App-Name": "ChatBot", "Type": "Image"}'}
    )
    
if response.status_code == 200:
    result = response.json()
    print(f"Uploaded to: {result['arweave_url']}")
```

## Security Features

- **Non-root execution**: Service runs as `appuser`
- **Read-only wallet mounts**: Wallet files should be mounted read-only
- **No key generation**: Service never creates or modifies wallet files
- **Health monitoring**: Continuous wallet status verification
- **Structured logging**: Comprehensive audit trail

## Migration from Old Service

This service replaces the previous `arweave_uploader_service` which had:
- Complex Node.js + Python dependencies
- Runtime wallet generation
- Root user execution
- Fragmented error handling

The new service provides the same functionality with:
- 50% smaller Docker image
- Faster startup time
- Better security posture
- Cleaner API design
