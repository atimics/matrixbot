#!/bin/bash
# Storj DCS Setup for Snapchain
# This script helps you set up Storj DCS as decentralized storage for Snapchain

echo "=== Storj DCS Setup for Snapchain ==="
echo
echo "Storj DCS is a decentralized, S3-compatible storage service that's perfect for Snapchain:"
echo "✅ ~50% cheaper than AWS S3"
echo "✅ Zero-knowledge encryption by default"
echo "✅ Global edge network for better performance"
echo "✅ 99.95% availability SLA"
echo "✅ Easy S3-compatible integration"
echo

# Check if rclone is installed
if ! command -v rclone &> /dev/null; then
    echo "📦 Installing rclone..."
    curl https://rclone.org/install.sh | sudo bash
    echo "✅ rclone installed successfully"
else
    echo "✅ rclone is already installed"
fi

echo
echo "📋 Setup Steps:"
echo
echo "1. Sign up for Storj DCS:"
echo "   👉 Visit: https://storj.io"
echo "   👉 Create an account and verify your email"
echo
echo "2. Create a project and bucket:"
echo "   👉 Go to your Storj dashboard"
echo "   👉 Create a new project (e.g., 'snapchain-storage')"
echo "   👉 Create a bucket (e.g., 'snapchain-data')"
echo
echo "3. Generate S3-compatible credentials:"
echo "   👉 Go to Access Management"
echo "   👉 Create S3 credentials"
echo "   👉 Save your Access Key and Secret Key"
echo

read -p "Have you completed steps 1-3? (y/n): " setup_complete

if [[ $setup_complete != "y" && $setup_complete != "Y" ]]; then
    echo "Please complete the setup steps above and run this script again."
    exit 1
fi

echo
echo "4. Configure rclone for Storj:"
echo
read -p "Enter your Storj Access Key: " access_key
read -s -p "Enter your Storj Secret Key: " secret_key
echo
read -p "Enter your bucket name: " bucket_name

# Configure rclone
echo
echo "📝 Configuring rclone..."

# Create rclone config directory if it doesn't exist
mkdir -p ~/.config/rclone

# Create rclone config for Storj
cat > ~/.config/rclone/rclone.conf << EOF
[storj]
type = s3
provider = Storj
access_key_id = $access_key
secret_access_key = $secret_key
endpoint = https://gateway.storjshare.io
acl = private
EOF

echo "✅ rclone configured for Storj"

echo
echo "5. Creating mount point and testing connection..."

# Create mount point
sudo mkdir -p /mnt/snapchain-data

# Test the connection
echo "🔍 Testing Storj connection..."
if rclone lsd storj: &> /dev/null; then
    echo "✅ Connection to Storj successful!"
else
    echo "❌ Failed to connect to Storj. Please check your credentials."
    exit 1
fi

# Check if bucket exists
if rclone lsd storj: | grep -q "$bucket_name"; then
    echo "✅ Bucket '$bucket_name' found"
else
    echo "📦 Creating bucket '$bucket_name'..."
    rclone mkdir "storj:$bucket_name"
    echo "✅ Bucket created successfully"
fi

echo
echo "6. Mounting Storj bucket..."

# Create systemd service for persistent mounting
sudo tee /etc/systemd/system/storj-snapchain.service > /dev/null << EOF
[Unit]
Description=Mount Storj bucket for Snapchain
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
ExecStart=/usr/bin/rclone mount storj:$bucket_name /mnt/snapchain-data --daemon --allow-other --vfs-cache-mode writes --vfs-cache-max-size 10G
ExecStop=/bin/umount /mnt/snapchain-data
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable storj-snapchain.service
sudo systemctl start storj-snapchain.service

# Wait a moment for mount to complete
sleep 3

# Check if mount is successful
if mountpoint -q /mnt/snapchain-data; then
    echo "✅ Storj bucket mounted successfully at /mnt/snapchain-data"
else
    echo "⚠️  Mount may not be ready yet. Checking manually..."
    sudo rclone mount "storj:$bucket_name" /mnt/snapchain-data --daemon --allow-other --vfs-cache-mode writes &
    sleep 3
    if mountpoint -q /mnt/snapchain-data; then
        echo "✅ Manual mount successful"
    else
        echo "❌ Failed to mount. Please check the logs with: journalctl -u storj-snapchain.service"
    fi
fi

# Set proper permissions
sudo chown -R $USER:docker /mnt/snapchain-data 2>/dev/null || sudo chown -R $USER:$USER /mnt/snapchain-data

echo
echo "7. Updating .env file..."

# Add Storj configuration to .env if it exists
if [ -f .env ]; then
    # Remove existing Storj configuration
    sed -i '/^STORJ_/d' .env
    # Add new configuration
    cat >> .env << EOF

# Storj DCS Configuration
STORJ_ACCESS_KEY=$access_key
STORJ_SECRET_KEY=$secret_key
STORJ_ENDPOINT=https://gateway.storjshare.io
STORJ_BUCKET=$bucket_name
EOF
    echo "✅ .env file updated with Storj configuration"
else
    echo "⚠️  No .env file found. Copy .env.example to .env and add your Storj credentials."
fi

echo
echo "🎉 Storj DCS setup complete!"
echo
echo "📋 Summary:"
echo "- Storj bucket mounted at: /mnt/snapchain-data"
echo "- Bucket name: $bucket_name"
echo "- Auto-mount service: storj-snapchain.service"
echo
echo "📝 Next steps:"
echo "1. Uncomment the snapchain service in docker-compose.yml"
echo "2. Update the volumes in docker-compose.yml to use:"
echo "   - /mnt/snapchain-data/.rocks:/app/.rocks"
echo "   - /mnt/snapchain-data/.rocks.snapshot:/app/.rocks.snapshot"
echo "3. Run: docker compose up -d --build"
echo
echo "🔧 Useful commands:"
echo "- Check mount status: mountpoint /mnt/snapchain-data"
echo "- Check service status: sudo systemctl status storj-snapchain.service"
echo "- View service logs: journalctl -u storj-snapchain.service"
echo "- Restart service: sudo systemctl restart storj-snapchain.service"
echo
echo "💰 Cost estimate: ~$4-7/month for 1TB of Snapchain data on Storj"
