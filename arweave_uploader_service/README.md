# Arweave Uploader Service

A microservice for handling direct Arweave uploads with wallet management.

## Features

- Direct Arweave blockchain integration using the Arweave Python client
- Automatic wallet generation and management
- RESTful API for uploading files and data
- Wallet balance monitoring and address retrieval
- Transaction status checking
- Secure wallet storage with appropriate file permissions

## API Endpoints

### `POST /upload`
Upload a file to Arweave.

**Request:**
- `file`: The file to upload (multipart/form-data)
- `content_type`: MIME type of the file
- `tags`: Optional JSON string of Arweave tags

**Response:**
```json
{
  "status": "success",
  "tx_id": "ARWEAVE_TRANSACTION_ID",
  "arweave_url": "https://arweave.net/TRANSACTION_ID"
}
```

### `GET /wallet-info`
Get wallet information including address and balance.

**Response:**
```json
{
  "address": "WALLET_ADDRESS",
  "balance_winston": "BALANCE_IN_WINSTON",
  "balance_ar": "BALANCE_IN_AR_FORMATTED",
  "gateway_url": "https://arweave.net",
  "funding_instructions": "Please send AR tokens..."
}
```

### `GET /status/{tx_id}`
Check the status of an Arweave transaction.

### `GET /health`
Health check endpoint.

## Environment Variables

- `ARWEAVE_WALLET_FILE_PATH`: Path to store the wallet JWK file (default: `/data/arweave_wallet.json`)
- `ARWEAVE_GATEWAY_URL`: Arweave gateway URL (default: `https://arweave.net`)

## Wallet Management

On first startup, the service will:
1. Check if a wallet file exists at the configured path
2. If not found, generate a new Arweave wallet
3. Save the wallet JWK to the configured path with restrictive permissions
4. Log the wallet address for funding

**Important:** The wallet file contains the private key and must be securely backed up!

## Security Considerations

- The wallet file should have restrictive permissions (600)
- The service should run in an isolated Docker container
- API access should be limited to internal network traffic only
- Regular backups of the wallet file are recommended

## Funding

To enable uploads, send AR tokens to the wallet address displayed in the logs or retrieved via the `/wallet-info` endpoint. The amount needed depends on:
- Size of data being uploaded
- Current Arweave network pricing
- Frequency of uploads

Monitor the balance regularly via the API to ensure sufficient funds for ongoing operations.
