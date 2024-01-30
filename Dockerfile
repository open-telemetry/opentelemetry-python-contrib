# Use Ubuntu 20.04 LTS as the base image
FROM ubuntu:20.04

# Avoid warnings by switching to noninteractive
ENV DEBIAN_FRONTEND=noninteractive

# This will make apt-get install without question
ARG DEBIAN_FRONTEND=noninteractive

# Install Python, pip, Git, and other utilities
RUN apt-get update \
    && apt-get install -y --no-install-recommends software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends python3.8 python3.8-distutils \
    && apt-get install -y --no-install-recommends python3-pip python3.8-venv \
    # Added Git installation here
    && apt-get install -y --no-install-recommends git \
    && python3.8 -m pip install --upgrade pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN python3.8 -m pip install -r dev-requirements.txt
# If you have a separate requirements.txt, uncomment the line below
# RUN python3.8 -m pip install -r requirements.txt

# Make port 80 available to the world outside this container
EXPOSE 80

# Define the command to run the app (e.g., using pytest)
CMD ["python3.8", "pytest"]
