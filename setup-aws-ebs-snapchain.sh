#!/bin/bash
# AWS EBS Setup for Snapchain
# This script helps you set up AWS EBS storage for Snapchain

echo "=== AWS EBS Setup for Snapchain ==="
echo

# Check if AWS CLI is installed and configured
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install it first:"
    echo "curl 'https://awscli.amazonaws.com/AWSCLIV2.pkg' -o 'AWSCLIV2.pkg'"
    echo "sudo installer -pkg AWSCLIV2.pkg -target /"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS credentials not configured. Please run 'aws configure' first."
    exit 1
fi

echo "✅ AWS CLI is configured"

# Get current AWS region and account info
AWS_REGION=$(aws configure get region)
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "📍 Using AWS Region: $AWS_REGION"
echo "🔑 AWS Account: $AWS_ACCOUNT"

echo
echo "🔍 Checking for existing EBS volumes tagged for Snapchain..."

# Check for existing Snapchain EBS volume
EXISTING_VOLUME=$(aws ec2 describe-volumes \
    --filters "Name=tag:Purpose,Values=Snapchain" "Name=state,Values=available,in-use" \
    --query 'Volumes[0].VolumeId' --output text 2>/dev/null)

if [[ "$EXISTING_VOLUME" != "None" && "$EXISTING_VOLUME" != "" ]]; then
    echo "✅ Found existing Snapchain EBS volume: $EXISTING_VOLUME"
    VOLUME_ID=$EXISTING_VOLUME
else
    echo "📦 Creating new EBS volume for Snapchain..."
    
    # Get the current instance's availability zone if running on EC2
    if curl -s --max-time 2 http://169.254.169.254/latest/meta-data/instance-id &> /dev/null; then
        INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
        AZ=$(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone)
        echo "🖥️  Running on EC2 instance: $INSTANCE_ID in AZ: $AZ"
    else
        echo "💻 Not running on EC2. You'll need to specify the AZ manually."
        read -p "Enter the Availability Zone for the EBS volume (e.g., us-east-1a): " AZ
    fi
    
    # Create EBS volume
    echo "Creating 1TB gp3 EBS volume in $AZ..."
    VOLUME_ID=$(aws ec2 create-volume \
        --size 1000 \
        --volume-type gp3 \
        --availability-zone $AZ \
        --tag-specifications 'ResourceType=volume,Tags=[{Key=Name,Value=Snapchain-Storage},{Key=Purpose,Value=Snapchain},{Key=Project,Value=RatiChat}]' \
        --query 'VolumeId' --output text)
    
    if [ $? -eq 0 ]; then
        echo "✅ EBS volume created: $VOLUME_ID"
        echo "⏳ Waiting for volume to become available..."
        aws ec2 wait volume-available --volume-ids $VOLUME_ID
        echo "✅ Volume is now available"
    else
        echo "❌ Failed to create EBS volume"
        exit 1
    fi
fi

# If running on EC2, attach the volume
if curl -s --max-time 2 http://169.254.169.254/latest/meta-data/instance-id &> /dev/null; then
    INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
    
    # Check if volume is already attached
    ATTACHMENT_STATE=$(aws ec2 describe-volumes --volume-ids $VOLUME_ID --query 'Volumes[0].Attachments[0].State' --output text 2>/dev/null)
    
    if [[ "$ATTACHMENT_STATE" != "attached" ]]; then
        echo "🔗 Attaching volume to current instance..."
        
        # Find available device name
        DEVICE="/dev/xvdf"
        aws ec2 attach-volume --volume-id $VOLUME_ID --instance-id $INSTANCE_ID --device $DEVICE
        
        echo "⏳ Waiting for volume to attach..."
        aws ec2 wait volume-in-use --volume-ids $VOLUME_ID
        echo "✅ Volume attached to $DEVICE"
        
        # Wait a moment for the device to appear
        sleep 5
        
        # Check if the device needs formatting
        if ! sudo file -s $DEVICE | grep -q "ext4"; then
            echo "💾 Formatting volume with ext4..."
            sudo mkfs.ext4 $DEVICE
            echo "✅ Volume formatted"
        else
            echo "✅ Volume already formatted"
        fi
        
        # Create mount point and mount
        echo "📁 Setting up mount point..."
        sudo mkdir -p /mnt/snapchain-data
        
        # Mount the volume
        sudo mount $DEVICE /mnt/snapchain-data
        
        # Add to fstab for persistent mounting
        DEVICE_UUID=$(sudo blkid -s UUID -o value $DEVICE)
        if ! grep -q "$DEVICE_UUID" /etc/fstab; then
            echo "UUID=$DEVICE_UUID /mnt/snapchain-data ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab
            echo "✅ Added to /etc/fstab for persistent mounting"
        fi
        
    else
        echo "✅ Volume is already attached"
        # Make sure it's mounted
        if ! mountpoint -q /mnt/snapchain-data; then
            sudo mkdir -p /mnt/snapchain-data
            sudo mount $DEVICE /mnt/snapchain-data 2>/dev/null || echo "⚠️  Volume may already be mounted elsewhere"
        fi
    fi
    
    # Set permissions
    sudo chown -R $USER:docker /mnt/snapchain-data 2>/dev/null || sudo chown -R $USER:$USER /mnt/snapchain-data
    sudo chmod 755 /mnt/snapchain-data
    
    echo "✅ EBS volume mounted at /mnt/snapchain-data"
    
else
    echo "📋 Manual setup required:"
    echo "1. Attach volume $VOLUME_ID to your EC2 instance"
    echo "2. Format: sudo mkfs.ext4 /dev/xvdf"
    echo "3. Mount: sudo mkdir -p /mnt/snapchain-data && sudo mount /dev/xvdf /mnt/snapchain-data"
    echo "4. Set permissions: sudo chown -R \$USER:docker /mnt/snapchain-data"
fi

# Update docker-compose.yml to use the mounted volume
echo
echo "📝 Updating docker-compose.yml..."

# Backup original file
cp docker-compose.yml docker-compose.yml.backup

# Update the snapchain volumes section
sed -i '' 's|# - /mnt/snapchain-data/.rocks:/app/.rocks|- /mnt/snapchain-data/.rocks:/app/.rocks|g' docker-compose.yml
sed -i '' 's|# - /mnt/snapchain-data/.rocks.snapshot:/app/.rocks.snapshot|- /mnt/snapchain-data/.rocks.snapshot:/app/.rocks.snapshot|g' docker-compose.yml

# Comment out the docker volumes
sed -i '' 's|      - snapchain_data:/app/.rocks|      # - snapchain_data:/app/.rocks  # Using EBS instead|g' docker-compose.yml
sed -i '' 's|      - snapchain_snapshot:/app/.rocks.snapshot|      # - snapchain_snapshot:/app/.rocks.snapshot  # Using EBS instead|g' docker-compose.yml

echo "✅ docker-compose.yml updated to use EBS storage"

# Update .env file with AWS configuration
echo
echo "📝 Updating .env with AWS EBS configuration..."

if [ -f .env ]; then
    # Remove existing AWS EBS configuration
    sed -i '' '/^AWS_EBS_/d' .env
    
    # Add new configuration
    cat >> .env << EOF

# AWS EBS Configuration for Snapchain
AWS_EBS_VOLUME_ID=$VOLUME_ID
AWS_EBS_MOUNT_PATH=/mnt/snapchain-data
AWS_REGION=$AWS_REGION
EOF
    echo "✅ .env file updated with AWS EBS configuration"
else
    echo "⚠️  No .env file found. Please copy .env.example to .env"
fi

echo
echo "🎉 AWS EBS setup complete!"
echo
echo "📋 Summary:"
echo "- EBS Volume ID: $VOLUME_ID"
echo "- Mount Point: /mnt/snapchain-data"
echo "- Size: 1TB (1000 GB)"
echo "- Type: gp3"
echo "- Monthly Cost: ~$80-100"
echo
echo "📝 Next steps:"
echo "1. Uncomment the snapchain service in docker-compose.yml"
echo "2. Run: docker compose up -d --build"
echo
echo "🔧 Useful commands:"
echo "- Check mount: df -h /mnt/snapchain-data"
echo "- Check volume: aws ec2 describe-volumes --volume-ids $VOLUME_ID"
echo "- Monitor usage: du -sh /mnt/snapchain-data"

# Show current disk usage
echo
echo "💾 Current storage status:"
df -h /mnt/snapchain-data 2>/dev/null || echo "Mount not ready yet"
