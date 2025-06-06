#!/bin/bash

# Docker Setup Script for Dev Container
echo "Setting up Docker support in dev container..."

# Kill any existing Docker processes
sudo pkill -f dockerd || true
sudo pkill -f containerd || true
sleep 2

# Clean up any stale files
sudo rm -f /var/run/docker.sock
sudo rm -f /var/run/docker.pid
sudo rm -f /run/containerd/containerd.sock
sudo find /run /var/run -name 'docker*.pid' -delete 2>/dev/null || true
sudo find /run /var/run -name 'container*.pid' -delete 2>/dev/null || true

# Create necessary directories
sudo mkdir -p /var/lib/docker
sudo mkdir -p /var/lib/containerd
sudo mkdir -p /run/containerd

# Start dockerd directly (it will manage containerd)
echo "Starting Docker daemon..."
sudo dockerd \
    --host=unix:///var/run/docker.sock \
    --storage-driver=overlay2 \
    --log-level=info \
    >/tmp/dockerd.log 2>&1 &

# Wait for Docker to be ready
echo "Waiting for Docker to be ready..."
for i in {1..30}; do
    if sudo docker info >/dev/null 2>&1; then
        echo "Docker is ready!"
        
        # Fix socket permissions
        sudo chmod 666 /var/run/docker.sock
        
        # Test with regular user
        if docker info >/dev/null 2>&1; then
            echo "Docker permissions configured correctly!"
            docker --version
            docker compose --version
            echo "Docker setup completed successfully!"
            exit 0
        else
            echo "Docker is running but permissions need adjustment..."
            # Try adding user to docker group if not already
            if ! groups $USER | grep -q docker; then
                sudo usermod -aG docker $USER
                echo "Added user to docker group. You may need to restart your shell/container."
            fi
            # For immediate use, make socket world-writable (not recommended for production)
            sudo chmod 666 /var/run/docker.sock
            exit 0
        fi
    fi
    echo "Waiting for Docker... (attempt $i/30)"
    sleep 2
done

echo "Docker setup failed. Check logs:"
echo "dockerd log:"
sudo cat /tmp/dockerd.log | tail -50
exit 1
