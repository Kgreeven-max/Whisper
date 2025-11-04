#!/bin/bash
set -e

echo "=========================================="
echo "Meeting Transcriber - VPS Deployment"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}Error: This script should not be run as root${NC}"
   echo "Please run as a regular user with sudo privileges"
   exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Step 0: Check environment configuration
echo -e "${YELLOW}Step 0: Checking environment configuration...${NC}"

if [ ! -f .env ]; then
    echo -e "${RED}ERROR: .env file not found!${NC}"
    echo ""
    echo "You must create a .env file with secure passwords before deploying."
    echo ""
    echo "Quick setup:"
    echo "  1. Copy the example file:"
    echo -e "     ${BLUE}cp .env.example .env${NC}"
    echo ""
    echo "  2. Generate secure password:"
    echo -e "     ${BLUE}python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"${NC}"
    echo ""
    echo "  3. Generate secret key:"
    echo -e "     ${BLUE}python3 -c \"import secrets; print(secrets.token_hex(32))\"${NC}"
    echo ""
    echo "  4. Edit .env and replace POSTGRES_PASSWORD and SECRET_KEY:"
    echo -e "     ${BLUE}nano .env${NC}"
    echo ""
    echo "  5. Run this script again"
    echo ""
    exit 1
fi

# Check if passwords are still placeholder values
if grep -q "REPLACE_WITH_SECURE_PASSWORD" .env 2>/dev/null || grep -q "REPLACE_WITH_SECURE_SECRET_KEY" .env 2>/dev/null; then
    echo -e "${RED}ERROR: .env file contains placeholder values!${NC}"
    echo ""
    echo "You must replace the placeholder passwords with secure values."
    echo ""
    echo "Generate secure values:"
    echo -e "  ${BLUE}python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"${NC}"
    echo -e "  ${BLUE}python3 -c \"import secrets; print(secrets.token_hex(32))\"${NC}"
    echo ""
    echo "Then edit .env and replace the placeholders"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ Environment file configured${NC}"
echo ""

# Step 1: Check prerequisites
echo -e "${YELLOW}Step 1: Checking prerequisites...${NC}"

if ! command_exists docker; then
    echo -e "${RED}Docker is not installed. Installing Docker...${NC}"
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo -e "${GREEN}Docker installed successfully${NC}"
    echo -e "${YELLOW}Please log out and log back in, then run this script again${NC}"
    exit 0
fi

if ! command_exists docker-compose; then
    echo -e "${RED}Docker Compose is not installed. Installing...${NC}"
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}Docker Compose installed successfully${NC}"
fi

echo -e "${GREEN}Prerequisites check passed${NC}"
echo ""

# Step 2: Create directories
echo -e "${YELLOW}Step 2: Creating necessary directories...${NC}"
mkdir -p uploads data
chmod 755 uploads data
echo -e "${GREEN}Directories created${NC}"
echo ""

# Step 3: Build and start services
echo -e "${YELLOW}Step 3: Building and starting Docker services...${NC}"
echo "This may take several minutes on first run..."
docker-compose up -d --build

echo -e "${GREEN}Services started${NC}"
echo ""

# Step 4: Wait for services to be ready
echo -e "${YELLOW}Step 4: Waiting for services to initialize...${NC}"
echo "Checking Whisper service..."
for i in {1..30}; do
    if curl -s http://localhost:9000/ > /dev/null 2>&1; then
        echo -e "${GREEN}Whisper is ready${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

echo "Checking Ollama service..."
for i in {1..30}; do
    if curl -s http://localhost:11434/ > /dev/null 2>&1; then
        echo -e "${GREEN}Ollama is ready${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

echo "Checking Web service..."
for i in {1..30}; do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        echo -e "${GREEN}Web service is ready${NC}"
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

# Step 5: Pull LLM model
echo -e "${YELLOW}Step 5: Installing LLM model...${NC}"
echo "Which model would you like to use?"
echo "1) llama2 (7B - Recommended, balanced performance)"
echo "2) mistral (7B - Faster, good quality)"
echo "3) phi (2.7B - Very fast, lower quality)"
echo "4) Skip (install manually later)"
read -p "Enter choice [1-4]: " model_choice

case $model_choice in
    1)
        echo "Pulling llama2 model (this may take 5-10 minutes)..."
        docker exec meeting-ollama ollama pull llama2
        ;;
    2)
        echo "Pulling mistral model (this may take 5-10 minutes)..."
        docker exec meeting-ollama ollama pull mistral
        # Update app.py to use mistral
        sed -i "s/'model': 'llama2'/'model': 'mistral'/g" app.py
        docker-compose restart web
        ;;
    3)
        echo "Pulling phi model (this may take 2-5 minutes)..."
        docker exec meeting-ollama ollama pull phi
        # Update app.py to use phi
        sed -i "s/'model': 'llama2'/'model': 'phi'/g" app.py
        docker-compose restart web
        ;;
    4)
        echo -e "${YELLOW}Skipping model installation. You'll need to install manually:${NC}"
        echo "docker exec meeting-ollama ollama pull llama2"
        ;;
    *)
        echo -e "${YELLOW}Invalid choice. Skipping model installation.${NC}"
        ;;
esac
echo ""

# Step 6: Setup systemd service (optional)
echo -e "${YELLOW}Step 6: Setting up auto-start on boot (optional)${NC}"
read -p "Enable auto-start on boot? [y/N]: " enable_autostart

if [[ $enable_autostart =~ ^[Yy]$ ]]; then
    # Update working directory in service file
    INSTALL_DIR=$(pwd)
    sed "s|WorkingDirectory=/opt/meeting-transcriber|WorkingDirectory=$INSTALL_DIR|g" meeting-transcriber.service > /tmp/meeting-transcriber.service

    sudo cp /tmp/meeting-transcriber.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable meeting-transcriber
    echo -e "${GREEN}Auto-start enabled${NC}"
else
    echo -e "${YELLOW}Skipping auto-start setup${NC}"
fi
echo ""

# Step 7: Nginx setup (optional)
echo -e "${YELLOW}Step 7: Nginx reverse proxy setup (optional)${NC}"
read -p "Set up Nginx reverse proxy? [y/N]: " setup_nginx

if [[ $setup_nginx =~ ^[Yy]$ ]]; then
    if ! command_exists nginx; then
        echo "Installing Nginx..."
        sudo apt update
        sudo apt install -y nginx
    fi

    read -p "Enter your domain name (or IP address): " domain_name

    # Update nginx config with domain
    sed "s/your-domain.com/$domain_name/g" nginx.conf > /tmp/meeting-transcriber-nginx.conf

    sudo cp /tmp/meeting-transcriber-nginx.conf /etc/nginx/sites-available/meeting-transcriber
    sudo ln -sf /etc/nginx/sites-available/meeting-transcriber /etc/nginx/sites-enabled/

    # Test nginx config
    if sudo nginx -t; then
        sudo systemctl reload nginx
        echo -e "${GREEN}Nginx configured successfully${NC}"

        # Ask about SSL
        read -p "Set up SSL with Let's Encrypt? [y/N]: " setup_ssl
        if [[ $setup_ssl =~ ^[Yy]$ ]]; then
            if ! command_exists certbot; then
                echo "Installing Certbot..."
                sudo apt install -y certbot python3-certbot-nginx
            fi

            sudo certbot --nginx -d $domain_name
            echo -e "${GREEN}SSL configured${NC}"
        fi
    else
        echo -e "${RED}Nginx configuration test failed. Please check the config.${NC}"
    fi
else
    echo -e "${YELLOW}Skipping Nginx setup${NC}"
fi
echo ""

# Step 8: Firewall setup
echo -e "${YELLOW}Step 8: Firewall configuration${NC}"
if command_exists ufw; then
    read -p "Configure firewall? [y/N]: " setup_firewall

    if [[ $setup_firewall =~ ^[Yy]$ ]]; then
        sudo ufw allow 22/tcp    # SSH
        sudo ufw allow 80/tcp    # HTTP
        sudo ufw allow 443/tcp   # HTTPS

        if [[ ! $setup_nginx =~ ^[Yy]$ ]]; then
            sudo ufw allow 8080/tcp  # Direct access if no nginx
        fi

        echo -e "${YELLOW}Firewall rules added. To enable UFW, run: sudo ufw enable${NC}"
    fi
else
    echo -e "${YELLOW}UFW not installed. Skipping firewall setup.${NC}"
fi
echo ""

# Final summary
echo -e "${GREEN}=========================================="
echo "Deployment Complete!"
echo "==========================================${NC}"
echo ""
echo "Services Status:"
docker-compose ps
echo ""
echo -e "${GREEN}Access your application at:${NC}"
if [[ $setup_nginx =~ ^[Yy]$ ]]; then
    echo "  http://$domain_name"
    if [[ $setup_ssl =~ ^[Yy]$ ]]; then
        echo "  https://$domain_name"
    fi
else
    echo "  http://$(hostname -I | awk '{print $1}'):8080"
fi
echo ""
echo -e "${YELLOW}Useful commands:${NC}"
echo "  View logs:           docker-compose logs -f"
echo "  Stop services:       docker-compose down"
echo "  Restart services:    docker-compose restart"
echo "  View status:         docker-compose ps"
echo "  Install LLM model:   docker exec meeting-ollama ollama pull llama2"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Upload your first meeting recording"
echo "  2. Check the logs to monitor processing"
echo "  3. Review the README.md for more configuration options"
echo ""
echo -e "${GREEN}Happy transcribing!${NC}"
