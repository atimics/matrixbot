#!/bin/bash
# Setup External Storage for Snapchain
# This script helps you configure external storage for the 1TB snapchain data

echo "=== Snapchain External Storage Setup ==="
echo

# Check available disk space
echo "Current disk space:"
df -h
echo

echo "Snapchain requires approximately 1TB of storage."
echo "Here are your options:"
echo
echo "1. Use AWS EBS Volume (traditional cloud storage)"
echo "2. Use Decentralized Storage (IPFS/Filecoin/Arweave)"
echo "3. Use Storj DCS (Decentralized Cloud Storage)"
echo "4. Use External USB/SSD Drive (local)"
echo "5. Use Network Attached Storage (NAS)"
echo "6. Use a Remote Snapchain Node (no local storage needed)"
echo

read -p "Select an option (1-6): " choice

case $choice in
    1)
        echo "=== AWS EBS Setup ==="
        echo "1. Create an EBS volume with at least 1TB"
        echo "2. Attach it to your EC2 instance"
        echo "3. Mount it to /mnt/snapchain-data"
        echo
        echo "Example commands:"
        echo "sudo mkfs.ext4 /dev/xvdf"
        echo "sudo mkdir -p /mnt/snapchain-data"
        echo "sudo mount /dev/xvdf /mnt/snapchain-data"
        echo "sudo chown -R \$USER:docker /mnt/snapchain-data"
        echo
        echo "Then update docker-compose.yml volumes to:"
        echo "  - /mnt/snapchain-data/.rocks:/app/.rocks"
        echo "  - /mnt/snapchain-data/.rocks.snapshot:/app/.rocks.snapshot"
        ;;
    2)
        echo "=== Decentralized Storage (IPFS/Filecoin/Arweave) ==="
        echo "⚠️  These options are experimental for blockchain node data:"
        echo
        echo "IPFS + Filecoin:"
        echo "- Good for: Large files, content-addressed storage"
        echo "- Challenges: Complex setup, retrieval times, cost predictability"
        echo "- Best for: Archival storage, not real-time blockchain operations"
        echo
        echo "Arweave:"
        echo "- Good for: Permanent storage (pay once, store forever)"
        echo "- Challenges: Limited to 256MB per transaction, expensive for 1TB"
        echo "- Best for: Critical data that must never be lost"
        echo
        echo "Recommendation: Use Storj DCS (option 3) for better blockchain compatibility"
        ;;
    3)
        echo "=== Storj DCS (Decentralized Cloud Storage) Setup ==="
        echo "Storj DCS is S3-compatible decentralized storage - perfect for Snapchain!"
        echo
        echo "Advantages:"
        echo "✅ S3-compatible API (easy integration)"
        echo "✅ ~50% cheaper than AWS S3" 
        echo "✅ Zero-knowledge encryption"
        echo "✅ Global edge network"
        echo "✅ 99.95% availability SLA"
        echo
        echo "Setup Steps:"
        echo "1. Sign up at https://storj.io"
        echo "2. Create a project and bucket"
        echo "3. Generate S3-compatible credentials"
        echo "4. Install rclone for mounting:"
        echo
        echo "# Install rclone"
        echo "curl https://rclone.org/install.sh | sudo bash"
        echo
        echo "# Configure rclone for Storj"
        echo "rclone config"
        echo "# Choose: Amazon S3 compatible storage provider"
        echo "# Provider: Storj"
        echo "# Access Key ID: [your-storj-access-key]"
        echo "# Secret Access Key: [your-storj-secret-key]"
        echo "# Endpoint: https://gateway.storjshare.io"
        echo
        echo "# Mount Storj bucket as filesystem"
        echo "sudo mkdir -p /mnt/snapchain-data"
        echo "rclone mount storj:your-bucket-name /mnt/snapchain-data --daemon --allow-other --vfs-cache-mode writes"
        echo
        echo "# Set permissions"
        echo "sudo chown -R \$USER:docker /mnt/snapchain-data"
        echo
        echo "Then update docker-compose.yml volumes to:"
        echo "  - /mnt/snapchain-data/.rocks:/app/.rocks"
        echo "  - /mnt/snapchain-data/.rocks.snapshot:/app/.rocks.snapshot"
        echo
        echo "💡 Tip: For production, consider using Storj's native Gateway-MT for better performance"
        ;;
    4)
        echo "=== External Drive Setup ==="
        echo "1. Connect your external drive"
        echo "2. Find the device: lsblk"
        echo "3. Mount it to /mnt/snapchain-data"
        echo
        echo "Example commands:"
        echo "sudo mkdir -p /mnt/snapchain-data"
        echo "sudo mount /dev/sdX1 /mnt/snapchain-data  # Replace sdX1 with your device"
        echo "sudo chown -R \$USER:docker /mnt/snapchain-data"
        ;;
    5)
        echo "=== NAS Setup ==="
        echo "1. Configure your NAS to export an NFS share"
        echo "2. Mount the NFS share to /mnt/snapchain-data"
        echo
        echo "Example commands:"
        echo "sudo mkdir -p /mnt/snapchain-data"
        echo "sudo mount -t nfs your-nas-ip:/path/to/share /mnt/snapchain-data"
        ;;
    6)
        echo "=== Remote Snapchain Node Setup ==="
        echo "This is the easiest option - no local storage needed!"
        echo
        echo "Add these to your .env file:"
        echo "SNAPCHAIN_GRPC_HOST=your-remote-host.com"
        echo "SNAPCHAIN_GRPC_PORT=3383"
        echo
        echo "Keep the snapchain service commented out in docker-compose.yml"
        echo "Your farcaster_api_service will connect to the remote node instead."
        ;;
    *)
        echo "Invalid option"
        exit 1
        ;;
esac

echo
echo "=== Next Steps ==="
echo "1. If you chose option 1, 3, 4, or 5: uncomment the snapchain service in docker-compose.yml"
echo "2. If you chose option 6: create a .env file with the remote host settings"
echo "3. Run: docker compose up -d --build"
