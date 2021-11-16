docker stop $(docker ps -qa) && docker rm $(docker ps -qa)
./bin/build_images.sh
./bin/upgrade_containers.sh