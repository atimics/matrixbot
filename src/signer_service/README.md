# Farcaster Signer Service

A secure, isolated microservice for signing Farcaster messages using the enterprise-grade "Signer Pod" pattern.

## Architecture Overview

This service provides secure key management and message signing for Farcaster operations, following security best practices:

1. **Isolated Environment**: Runs in its own container with minimal dependencies
2. **Secure Key Storage**: Encrypts private keys at rest using master keys from cloud HSM/KMS
3. **Memory-Only Operations**: Private keys are only decrypted into memory during signing
4. **Minimal API Surface**: Exposes only essential signing endpoints
5. **Production-Ready**: Supports AWS KMS, Azure Key Vault, and local development

## Key Features

- **Ed25519 Key Generation**: Generates Farcaster-compatible signing keys
- **Encrypted Storage**: Stores keys encrypted using industry-standard encryption
- **Cloud HSM Integration**: Supports AWS KMS and Azure Key Vault for enterprise security
- **Automatic Key Loading**: Loads existing keys on startup or generates new ones
- **Health Monitoring**: Provides health check and status endpoints
- **Message Signing**: Signs CastAdd and ReactionAdd protobuf messages

## Setup Guide

### 1. Environment Configuration

Copy the example environment configuration and fill in your values:

```bash
# For development - generate a master key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Add to your .env file:
SIGNER_MASTER_KEY=your_generated_key_here
FARCASTER_BOT_FID=your_farcaster_bot_fid
```

### 2. First-Time Setup

On first startup, the service will:

1. Check for existing keys in `/secure_storage`
2. If none found and `AUTO_GENERATE_KEY=true`, generate a new Ed25519 key pair
3. Encrypt the private key using the master key
4. Store the encrypted key persistently
5. Log the **public key** that needs to be registered on-chain

### 3. On-Chain Registration (REQUIRED)

After the service generates a new key, you **MUST** register the public key on the Farcaster Key Registry:

```
⚠️  IMPORTANT: You must use your account's Owner Key to authorize the new signer key
    on the Farcaster Key Registry contract. Without this step, signed messages will be rejected.
```

### 4. Production Security

For production deployments, use cloud key management:

#### AWS KMS Setup:
```bash
# Environment variables:
USE_CLOUD_HSM=true
AWS_REGION=us-east-1
AWS_SIGNER_MASTER_KEY_ARN=arn:aws:secretsmanager:region:account:secret:name

# IAM Policy (attach to the service's role):
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:signer-master-key-*"
    }
  ]
}
```

#### Azure Key Vault Setup:
```bash
# Environment variables:
USE_CLOUD_HSM=true
AZURE_KEY_VAULT_URL=https://your-vault.vault.azure.net/
AZURE_SIGNER_MASTER_KEY_NAME=signer-master-key

# Azure permissions: Grant the service's managed identity "Key Vault Secrets User" role
```

## API Endpoints

### Health & Status

- `GET /health` - Service health check
- `GET /v1/status` - Detailed signer status (key loaded, FID, public key)

### Signing Operations

- `POST /v1/sign-cast` - Sign a cast message
- `POST /v1/sign-reaction` - Sign a reaction message

### Administration

- `POST /v1/admin/generate-key` - Generate a new signing key (requires force=true to overwrite)

## Security Best Practices

### Development Environment

1. **Strong Master Key**: Use `Fernet.generate_key()` to generate a cryptographically secure master key
2. **Secure Storage**: Ensure the Docker volume has proper permissions (700)
3. **Network Isolation**: Restrict access to the signer service to only the farcaster-api-service

### Production Environment

1. **Cloud HSM/KMS**: Use AWS KMS or Azure Key Vault for master key storage
2. **IAM Roles**: Use minimal IAM permissions (only `secretsmanager:GetSecretValue` or equivalent)
3. **Network Security**: Deploy in a private subnet with no internet access
4. **Monitoring**: Enable CloudWatch/Azure Monitor for security events
5. **Key Rotation**: Implement a key rotation strategy
6. **Backup**: Ensure encrypted key files are backed up securely

## Message Flow

```
1. farcaster-api-service receives cast/reaction request
2. farcaster-api-service calls signer-service to sign the message data
3. signer-service loads encrypted key, decrypts to memory
4. signer-service creates protobuf message and signs with Ed25519 key
5. signer-service returns signed message bytes
6. farcaster-api-service submits signed message to Snapchain node
7. Snapchain gossips the message to the Farcaster network
```

## Troubleshooting

### Key Generation Issues

```bash
# Check signer service logs:
docker logs ratichat_signer_service

# Common issues:
# - Missing FARCASTER_BOT_FID environment variable
# - Invalid master key format
# - Permissions issues with /secure_storage volume
```

### Signing Failures

```bash
# Verify key is loaded:
curl http://localhost:8002/v1/status

# Check if public key is registered on-chain
# Verify protobuf libraries are available
```

### AWS/Azure Connection Issues

```bash
# Test AWS credentials:
aws sts get-caller-identity

# Test Azure credentials:
az account show

# Verify IAM/RBAC permissions for secret access
```

## Development

### Running Locally

```bash
cd signer_service
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Testing

```bash
# Test health endpoint:
curl http://localhost:8002/health

# Test status endpoint:
curl http://localhost:8002/v1/status

# Test cast signing:
curl -X POST http://localhost:8002/v1/sign-cast \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from RatiChat!"}'
```

## Security Considerations

1. **Key Material**: Private keys never leave the signer service container
2. **Network Access**: Signer service should not have internet access in production
3. **Logging**: Sensitive information is never logged
4. **Memory Protection**: Keys are cleared from memory when possible
5. **Container Security**: Runs as non-root user with minimal privileges

This signer service provides enterprise-grade security for Farcaster message signing while maintaining simplicity and reliability.
