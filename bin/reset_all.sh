# Remove all containers
docker stop $(docker ps -q)
docker rm $(docker ps -qa)

# Remove volumes
docker volume rm $(docker volume ls -q)

# Remove
sudo rm /etc/NetworkManager/system-connections/*

# Restart containers
./bin/upgrade_containers.sh

sudo reboot
